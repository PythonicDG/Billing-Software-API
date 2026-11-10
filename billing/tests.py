from decimal import Decimal
from django.test import TestCase
from rest_framework import serializers
from rest_framework.test import APIRequestFactory, force_authenticate
from accounts.models import User
from products.models import Product
from .serializers import InvoiceSerializer
from .views import InvoiceViewSet


class CaseBillingTests(TestCase):
    def setUp(self):
        self.product = Product.objects.create(
            name='Test case', selling_price=Decimal('100.50'),
            purchase_price=Decimal('50'), mrp=Decimal('120'),
            no_of_case=3, cent_in_per_cs=Decimal('2.3'),
        )

    def serializer(self, quantity=2, unit='CASE', instance=None):
        return InvoiceSerializer(instance, data={
            'grand_total': '462.30', 'sub_total': '462.30',
            'items': [{'product': str(self.product.id), 'quantity': quantity,
                       'unit': unit, 'unit_price': '231.15'}],
        })

    def create_invoice(self):
        serializer = self.serializer()
        serializer.is_valid(raise_exception=True)
        return serializer.save()

    def test_create_and_update_case_stock(self):
        invoice = self.create_invoice()
        item = invoice.items.get()
        self.assertEqual(item.pieces_per_case, 23)
        self.assertEqual(item.total_price, Decimal('462.30'))
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 23)
        serializer = self.serializer(quantity=3, instance=invoice)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 0)

    def test_insufficient_stock_rolls_back_edit(self):
        invoice = self.create_invoice()
        serializer = self.serializer(quantity=4, instance=invoice)
        serializer.is_valid(raise_exception=True)
        with self.assertRaises(serializers.ValidationError):
            serializer.save()
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 23)
        self.assertEqual(invoice.items.get().quantity, 2)

    def test_delete_restores_original_case_size_after_inventory_change(self):
        invoice = self.create_invoice()
        Product.objects.filter(pk=self.product.pk).update(cent_in_per_cs=Decimal('5'))
        owner = User.objects.create_user(username='case-owner', email='case@test.com',
                                        password='test', role=User.OWNER)
        request = APIRequestFactory().delete('/')
        force_authenticate(request, user=owner)
        response = InvoiceViewSet.as_view({'delete': 'destroy'})(request, pk=invoice.pk)
        self.assertEqual(response.status_code, 204)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 69)

    def test_invalid_case_size_and_zero_quantity_rejected(self):
        for cents in ('0', '2.35'):
            Product.objects.filter(pk=self.product.pk).update(cent_in_per_cs=Decimal(cents))
            self.assertFalse(self.serializer().is_valid())
        self.assertFalse(self.serializer(quantity=0).is_valid())

    def test_existing_units_keep_stock_conversion(self):
        for unit, pieces in [('PIECE', 2), ('CENT', 20)]:
            serializer = self.serializer(unit=unit)
            serializer.is_valid(raise_exception=True)
            invoice = serializer.save()
            self.assertEqual(invoice.items.get().stock_quantity, pieces)

    def test_preview_case_without_deducting_stock(self):
        user = User.objects.create_user(username='preview-user', email='preview@test.com',
                                       password='test', role=User.OWNER)
        request = APIRequestFactory().post('/', {
            'grand_total': '462.30', 'sub_total': '462.30',
            'items': [{'product': str(self.product.pk), 'quantity': 2,
                       'unit': 'CASE', 'unit_price': '231.15'}],
        }, format='json')
        force_authenticate(request, user=user)
        response = InvoiceViewSet.as_view({'post': 'preview'})(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['items'][0]['unit'], 'CASE')
        self.assertEqual(response.data['items'][0]['total_price'], '462.30')
        self.assertEqual(response.data['items'][0]['pieces_per_case'], 23)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 69)

    def test_reports_use_case_size_for_purchase_cost(self):
        from reports.views import DashboardSummaryView, SalesAnalyticsView, OperationsFinanceView
        self.create_invoice()
        owner = User.objects.create_user(username='report-owner', email='report@test.com',
                                        password='test', role=User.OWNER)
        for view in (DashboardSummaryView, SalesAnalyticsView, OperationsFinanceView):
            request = APIRequestFactory().get('/')
            force_authenticate(request, user=owner)
            response = view.as_view()(request)
            self.assertEqual(response.status_code, 200)
            if view == DashboardSummaryView:
                self.assertAlmostEqual(response.data['today_profit'], 232.30)
            elif view == SalesAnalyticsView:
                self.assertAlmostEqual(response.data['product_profitability'][0]['profit'], 232.30)

    def test_pdf_case_quantity_uses_saved_size_and_product_display_mode(self):
        invoice = self.create_invoice()
        item = invoice.items.get()
        self.assertEqual(item.pdf_quantity, '2 (2.3 cent/case)')
        Product.objects.filter(pk=self.product.pk).update(cent_in_per_cs=Decimal('5'))
        self.assertEqual(invoice.items.get().pdf_quantity, '2 (2.3 cent/case)')
        self.product.entry_mode = 'piece'
        self.product.save(update_fields=['entry_mode'])
        self.assertEqual(invoice.items.get().pdf_quantity, '2 (23 pcs/case)')
        self.product.delete()
        self.assertEqual(invoice.items.get().pdf_quantity, '2 (23 pcs/case)')

    def test_pdf_quantity_leaves_non_case_items_plain(self):
        from .models import InvoiceItem
        for unit in ('PIECE', 'CENT', 'CASE'):
            self.assertEqual(InvoiceItem(unit=unit, quantity=3).pdf_quantity, '3')

    def test_pdf_renders_case_contents_long_name_and_large_prices(self):
        import io
        from django.template.loader import render_to_string
        from pypdf import PdfReader
        from xhtml2pdf import pisa
        from core.models import CompanySettings
        from .models import InvoiceItem

        invoice = self.create_invoice()
        name = 'Premium Celebration Fireworks Assortment With Extra Long Product Name'
        InvoiceItem.objects.filter(invoice=invoice).update(
            product_name_snapshot=name, unit_price=Decimal('9999999999.99'),
            total_price=Decimal('9999999999.99'),
        )
        html = render_to_string('billing/invoice_pdf.html', {
            'invoice': invoice, 'company': CompanySettings.get_settings(),
        })
        output = io.BytesIO()
        result = pisa.CreatePDF(html, dest=output)
        self.assertEqual(result.err, 0)
        reader = PdfReader(output)
        self.assertEqual(len(reader.pages), 1)
        text = reader.pages[0].extract_text()
        self.assertIn('2 (2.3 cent/case)', text)
        self.assertIn('9999999999.99', text)
        self.assertIn(name, ' '.join(text.split()))


class AuditLogTests(TestCase):
    def setUp(self):
        from rest_framework.test import APIClient
        self.owner = User.objects.create_user(
            username='owner', email='owner@example.com', password='x', role=User.OWNER)
        self.staff = User.objects.create_user(
            username='staff', email='staff@example.com', password='x', role=User.STAFF)
        self.product = Product.objects.create(
            name='Rocket', selling_price=Decimal('10'), purchase_price=Decimal('5'),
            mrp=Decimal('12'), stock_quantity=10)
        self.client = APIClient()
        self.client.force_authenticate(self.owner)

    def make_bill(self):
        response = self.client.post('/api/billing/invoices/', {
            'grand_total': '20.00', 'sub_total': '20.00', 'paid_amount': '20.00',
            'items': [{'product': str(self.product.id), 'quantity': 2, 'unit': 'PIECE', 'unit_price': '10.00'}],
        }, format='json')
        self.assertEqual(response.status_code, 201, response.content)
        return response.data['id']

    def test_delete_paid_bill_is_logged_with_user_and_reason(self):
        from core.models import AuditLog
        bill_id = self.make_bill()
        response = self.client.delete(f'/api/billing/invoices/{bill_id}/', {'reason': 'duplicate bill'}, format='json')
        self.assertEqual(response.status_code, 204)
        entry = AuditLog.objects.get(action=AuditLog.DELETE)
        self.assertEqual(entry.user, self.owner)
        self.assertIn('owner@example.com', entry.user_label)
        self.assertEqual(entry.reason, 'duplicate bill')
        self.assertEqual(entry.details['before']['payment_status'], 'PAID')
        self.assertEqual(entry.details['before']['items'][0]['quantity'], 2)

    def test_edit_logs_before_and_after(self):
        from core.models import AuditLog
        bill_id = self.make_bill()
        response = self.client.patch(f'/api/billing/invoices/{bill_id}/', {'sub_total': '25.00'}, format='json')
        self.assertEqual(response.status_code, 200, response.content)
        entry = AuditLog.objects.get(action=AuditLog.UPDATE)
        self.assertEqual(entry.details['changes']['sub_total'], {'from': '20.00', 'to': '25.00'})

    def test_audit_entries_are_immutable(self):
        from core.models import AuditLog
        self.make_bill()
        entry = AuditLog.objects.get()
        with self.assertRaises(PermissionError):
            entry.delete()
        entry.summary = 'tampered'
        with self.assertRaises(PermissionError):
            entry.save()

    def test_only_owner_can_read_logs(self):
        from rest_framework.test import APIClient
        self.make_bill()
        self.assertEqual(self.client.get('/api/core/audit-logs/').status_code, 200)
        staff_client = APIClient()
        staff_client.force_authenticate(self.staff)
        self.assertEqual(staff_client.get('/api/core/audit-logs/').status_code, 403)


class ActivityLogCoverageTests(TestCase):
    """Create / edit / delete of customers, products, categories and settings are logged."""

    def setUp(self):
        from rest_framework.test import APIClient
        self.owner = User.objects.create_user(
            username='owner', email='owner@example.com', password='x', role=User.OWNER)
        self.client = APIClient(REMOTE_ADDR='10.1.2.3')
        self.client.force_authenticate(self.owner)

    def entries(self, entity_type):
        from core.models import AuditLog
        return list(AuditLog.objects.filter(entity_type=entity_type).order_by('id'))

    def test_customer_create_edit_delete(self):
        r = self.client.post('/api/customers/', {'name': 'Ravi', 'phone': '9000000001'}, format='json')
        self.assertEqual(r.status_code, 201, r.content)
        cid = r.data['id']
        self.client.patch(f'/api/customers/{cid}/', {'name': 'Ravi K'}, format='json')
        self.client.patch(f'/api/customers/{cid}/', {'name': 'Ravi K'}, format='json')  # no change -> no entry
        self.assertEqual(self.client.delete(f'/api/customers/{cid}/').status_code, 204)

        created, edited, deleted = self.entries('Customer')
        self.assertEqual([created.action, edited.action, deleted.action], ['CREATE', 'UPDATE', 'DELETE'])
        self.assertEqual(created.ip_address, '10.1.2.3')
        self.assertEqual(created.user, self.owner)
        self.assertEqual(edited.details, {'changes': {'name': {'from': 'Ravi', 'to': 'Ravi K'}}})
        self.assertEqual(deleted.details['data']['phone'], '9000000001')

    def test_forwarded_ip_is_used(self):
        self.client.post('/api/customers/', {'name': 'A', 'phone': '9000000002'}, format='json',
                         HTTP_X_FORWARDED_FOR='49.36.1.1, 10.0.0.1')
        self.assertEqual(self.entries('Customer')[0].ip_address, '49.36.1.1')

    def test_failed_delete_is_not_logged(self):
        r = self.client.post('/api/customers/', {'name': 'B', 'phone': '9000000003'}, format='json')
        cid = r.data['id']
        product = Product.objects.create(name='P', selling_price=Decimal('10'), stock_quantity=10)
        self.client.post('/api/billing/invoices/', {
            'customer': cid, 'grand_total': '10.00', 'sub_total': '10.00', 'paid_amount': '0',
            'items': [{'product': str(product.id), 'quantity': 1, 'unit': 'PIECE', 'unit_price': '10.00'}],
        }, format='json')
        self.assertEqual(self.client.delete(f'/api/customers/{cid}/').status_code, 400)
        self.assertEqual([e.action for e in self.entries('Customer')], ['CREATE'])

    def test_product_and_category_logged(self):
        r = self.client.post('/api/products/', {'name': 'Rocket', 'selling_price': '10.00'}, format='json')
        self.assertEqual(r.status_code, 201, r.content)
        pid = r.data['data']['id']
        self.client.patch(f'/api/products/{pid}/', {'selling_price': '12.00'}, format='json')
        self.client.delete(f'/api/products/{pid}/')
        self.assertEqual([e.action for e in self.entries('Product')], ['CREATE', 'UPDATE', 'DELETE'])
        self.assertEqual(self.entries('Product')[1].details['changes']['selling_price'],
                         {'from': '10.00', 'to': '12.00'})

        r = self.client.post('/api/products/categories/', {'name': 'Sky'}, format='json')
        self.client.delete(f"/api/products/categories/{r.data['id']}/")
        self.assertEqual([e.action for e in self.entries('Category')], ['CREATE', 'DELETE'])

    def test_settings_and_pin_logged_without_secrets(self):
        self.client.patch('/api/core/settings/update_settings/', {'phone': '1112223334'}, format='json')
        self.client.post('/api/core/dashboard-pin/set_pin/', {'pin': '4321'}, format='json')
        self.client.post('/api/core/dashboard-pin/remove_pin/', {}, format='json')
        self.assertEqual(self.entries('Settings')[0].details['changes']['phone']['to'], '1112223334')
        pin = self.entries('Dashboard PIN')
        self.assertEqual([e.action for e in pin], ['CREATE', 'DELETE'])
        self.assertNotIn('4321', str([e.details for e in pin]) + str([e.summary for e in pin]))

    def test_log_list_is_paginated(self):
        self.client.post('/api/customers/', {'name': 'C', 'phone': '9000000004'}, format='json')
        r = self.client.get('/api/core/audit-logs/')
        self.assertEqual(r.data['count'], 1)
        self.assertEqual(r.data['results'][0]['ip_address'], '10.1.2.3')


class SoftDeleteTests(TestCase):
    """Deleting from the app hides rows; only the admin removes them for good."""

    def setUp(self):
        from rest_framework.test import APIClient
        self.owner = User.objects.create_superuser(
            username='owner', email='owner@example.com', password='x', role=User.OWNER)
        self.product = Product.objects.create(
            name='Rocket', selling_price=Decimal('10'), purchase_price=Decimal('5'), stock_quantity=10)
        self.client = APIClient()
        self.client.force_authenticate(self.owner)

    def make_bill(self, qty=2, paid='0', **extra):
        r = self.client.post('/api/billing/invoices/', {
            'grand_total': f'{qty * 10}.00', 'sub_total': f'{qty * 10}.00', 'paid_amount': paid,
            'items': [{'product': str(self.product.id), 'quantity': qty, 'unit': 'PIECE', 'unit_price': '10.00'}],
            **extra,
        }, format='json')
        self.assertEqual(r.status_code, 201, r.content)
        return r.data

    def test_bill_delete_is_soft_and_restores_stock(self):
        from billing.models import Invoice, InvoiceItem, Payment
        bill = self.make_bill(qty=3, paid='30.00')
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 7)

        self.assertEqual(self.client.delete(f"/api/billing/invoices/{bill['id']}/").status_code, 204)

        row = Invoice.all_objects.get(pk=bill['id'])          # still in the database
        self.assertTrue(row.is_deleted)
        self.assertEqual(row.deleted_by, self.owner)
        self.assertFalse(Invoice.objects.filter(pk=bill['id']).exists())
        self.assertEqual(self.client.get(f"/api/billing/invoices/{bill['id']}/").status_code, 404)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 10)
        # Its items/payments no longer count in reports.
        self.assertEqual(InvoiceItem.objects.filter(invoice_id=bill['id']).count(), 0)
        self.assertEqual(InvoiceItem.all_objects.filter(invoice_id=bill['id']).count(), 1)
        self.assertEqual(Payment.objects.count(), 0)

    def test_deleted_bill_number_is_not_reused(self):
        first = self.make_bill()
        self.client.delete(f"/api/billing/invoices/{first['id']}/")
        second = self.make_bill()
        self.assertNotEqual(first['invoice_number'], second['invoice_number'])

    def test_product_delete_is_soft_and_keeps_stock(self):
        self.assertEqual(self.client.delete(f'/api/products/{self.product.id}/').status_code, 204)
        self.assertFalse(Product.objects.filter(pk=self.product.pk).exists())
        row = Product.all_objects.get(pk=self.product.pk)
        self.assertTrue(row.is_deleted)
        row.save()                                 # save of a deleted product must not reset stock
        row.refresh_from_db()
        self.assertEqual(row.stock_quantity, 10)
        # Can't be sold any more.
        r = self.client.post('/api/billing/invoices/', {
            'grand_total': '10.00', 'sub_total': '10.00',
            'items': [{'product': str(self.product.id), 'quantity': 1, 'unit': 'PIECE', 'unit_price': '10.00'}],
        }, format='json')
        self.assertEqual(r.status_code, 400)

    def test_old_bill_with_deleted_product_can_still_be_edited(self):
        bill = self.make_bill()
        self.client.delete(f'/api/products/{self.product.id}/')
        r = self.client.patch(f"/api/billing/invoices/{bill['id']}/", {
            'items': [{'product': str(self.product.id), 'quantity': 1, 'unit': 'PIECE', 'unit_price': '10.00'}],
        }, format='json')
        self.assertEqual(r.status_code, 200, r.content)

    def test_customer_soft_delete_and_phone_reuse(self):
        from customers.models import Customer
        r = self.client.post('/api/customers/', {'name': 'Ravi', 'phone': '9000000001'}, format='json')
        cid = r.data['id']
        self.assertEqual(self.client.delete(f'/api/customers/{cid}/').status_code, 204)
        self.assertTrue(Customer.all_objects.get(pk=cid).is_deleted)

        # Adding the same phone by hand gives a clear error, not a crash.
        r = self.client.post('/api/customers/', {'name': 'X', 'phone': '9000000001'}, format='json')
        self.assertEqual(r.status_code, 400)
        self.assertIn('deleted customer', str(r.data['phone']))

        # Billing that phone again brings the customer back.
        self.make_bill(customer_phone='9000000001', customer_name='Ravi')
        self.assertFalse(Customer.all_objects.get(pk=cid).is_deleted)

    def test_admin_restore_and_permanent_delete(self):
        from django.urls import reverse
        from billing.models import Invoice, InvoiceItem
        bill = self.make_bill(qty=4)
        self.client.delete(f"/api/billing/invoices/{bill['id']}/")
        self.client.force_login(self.owner)

        changelist = reverse('admin:billing_invoice_changelist')
        self.assertContains(self.client.get(changelist + '?deleted=yes'), bill['invoice_number'])

        self.client.post(changelist, {'action': 'restore_selected', '_selected_action': [bill['id']]})
        self.assertFalse(Invoice.all_objects.get(pk=bill['id']).is_deleted)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 6)       # stock taken again

        self.client.post(reverse('admin:billing_invoice_delete', args=[bill['id']]), {'post': 'yes'})
        self.assertFalse(Invoice.all_objects.filter(pk=bill['id']).exists())   # gone for good
        self.assertEqual(InvoiceItem.all_objects.filter(invoice_id=bill['id']).count(), 0)

    def test_existing_rows_are_active(self):
        # Rows created the normal way (like all existing data after migrating) are not deleted.
        from billing.models import Invoice, InvoiceItem
        self.make_bill()
        self.assertEqual(Invoice.objects.count(), Invoice.all_objects.count())
        self.assertFalse(Product.all_objects.get(pk=self.product.pk).is_deleted)
