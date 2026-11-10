from django.contrib import admin
from django.db.models import F
from core.admin_softdelete import SoftDeleteAdminMixin
from customers.models import Customer
from products.models import Product
from .models import Invoice, InvoiceItem


class InvoiceItemInline(admin.TabularInline):
    model = InvoiceItem
    extra = 1
    readonly_fields = ("id", "total_price")

    def get_queryset(self, request):
        # Show items of deleted bills too.
        return InvoiceItem.all_objects.get_queryset()

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'product':
            kwargs['queryset'] = Product.all_objects.all()
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(Invoice)
class InvoiceAdmin(SoftDeleteAdminMixin, admin.ModelAdmin):
    list_display = ("invoice_number", "customer", "grand_total", "amount_paid", "payment_status", "created_at")
    list_filter = ("payment_status", "payment_method", "created_at")
    search_fields = ("invoice_number", "customer__name", "customer__phone")
    inlines = [InvoiceItemInline]
    readonly_fields = ("id", "invoice_number", "created_at", "updated_at")

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'customer':
            kwargs['queryset'] = Customer.all_objects.all()
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def on_restore(self, request, invoice):
        # Deleting the bill gave its stock back; restoring it takes the stock again.
        for item in InvoiceItem.all_objects.filter(invoice=invoice, product__isnull=False):
            Product.all_objects.filter(id=item.product_id).update(
                stock_quantity=F('stock_quantity') - item.stock_quantity)
        # The bill's customer must be visible again too.
        if invoice.customer_id:
            customer = Customer.all_objects.get(pk=invoice.customer_id)
            if customer.is_deleted:
                customer.restore()

@admin.register(InvoiceItem)
class InvoiceItemAdmin(admin.ModelAdmin):
    list_display = ("invoice", "product_name_snapshot", "quantity", "unit", "unit_price", "total_price")
    list_filter = ("unit",)
    search_fields = ("invoice__invoice_number", "product_name_snapshot", "sku_snapshot")

    def get_queryset(self, request):
        return InvoiceItem.all_objects.get_queryset()
