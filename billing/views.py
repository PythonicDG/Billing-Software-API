from rest_framework import viewsets, permissions, status, filters
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.authentication import TokenAuthentication
from rest_framework.pagination import PageNumberPagination
from core.authentication import QueryParameterTokenAuthentication
from django.db import transaction
from django.http import HttpResponse
from .models import Invoice, InvoiceItem
from .serializers import InvoiceSerializer, InvoiceItemSerializer, PaymentSerializer
from products.models import Product
from accounts.permissions import IsOwner
from django.db.models import F
import io

class GlobalLedgerPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100

class InvoiceViewSet(viewsets.ModelViewSet):
    queryset = Invoice.objects.all().order_by('-created_at')
    serializer_class = InvoiceSerializer
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [TokenAuthentication, QueryParameterTokenAuthentication]
    
    filterset_fields = ['payment_status', 'payment_method', 'customer']
    search_fields = ['invoice_number', 'customer__name', 'customer__phone']

    def get_permissions(self):
        if self.action == 'destroy':
            return [IsOwner()]
        return super().get_permissions()

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @action(detail=False, methods=['GET'])
    def all_transactions(self, request):
        invoices = Invoice.objects.all().order_by('-created_at')
        
        paginator = GlobalLedgerPagination()
        page = paginator.paginate_queryset(invoices, request)
        
        invoices_to_process = page if page is not None else invoices
        
        bills_data = []
        for inv in invoices_to_process:
            outstanding = inv.outstanding_balance
            payments_data = []
            for p in inv.payments.all():
                payments_data.append({
                    'amount': float(p.amount),
                    'mode': p.mode,
                    'payment_date': p.payment_date.isoformat(),
                    'notes': p.notes or ''
                })

            bills_data.append({
                'id': str(inv.id),
                'customer_name': inv.customer.name if inv.customer else 'Guest',
                'customer_phone': inv.customer.phone if inv.customer else '',
                'invoice_number': inv.invoice_number,
                'date': inv.created_at.isoformat(),
                'total': float(inv.total_amount),
                'paid': float(inv.amount_paid),
                'outstanding': float(outstanding),
                'payment_method': inv.payment_method,
                'payments': payments_data
            })
            
        response_data = {
            'bills': bills_data,
        }
        
        if page is not None:
            return Response({
                'count': paginator.page.paginator.count,
                'next': paginator.get_next_link(),
                'previous': paginator.get_previous_link(),
                'bills': bills_data,
            })

        return Response(response_data)

    @action(detail=False, methods=['GET'])
    def download_transactions_pdf(self, request):
        """
        Export and download PDF of all transactions filtered by Day-wise, Date-to-Date (range), Month-wise, or All Time.
        Includes Date, Bill Number, Customer, Total, Paid, Due, and Payment Status.
        """
        from django.template.loader import render_to_string
        from xhtml2pdf import pisa
        from django.utils import timezone
        from datetime import datetime
        from core.models import CompanySettings
        from django.conf import settings
        import os

        company = CompanySettings.get_settings()
        filter_type = request.query_params.get('filter_type', 'all')
        date_str = request.query_params.get('date')
        start_date_str = request.query_params.get('start_date')
        end_date_str = request.query_params.get('end_date')
        month = request.query_params.get('month')
        year = request.query_params.get('year')
        payment_status = request.query_params.get('payment_status', 'ALL')

        invoices = Invoice.objects.all().select_related('customer').order_by('created_at')

        period_label = "All Time (Complete History)"

        if filter_type == 'day' and date_str:
            try:
                d = datetime.strptime(date_str, '%Y-%m-%d').date()
                invoices = invoices.filter(created_at__date=d)
                period_label = f"Single Day ({d.strftime('%d %b %Y')})"
            except ValueError:
                pass
        elif filter_type == 'range' and start_date_str and end_date_str:
            try:
                start_d = datetime.strptime(start_date_str, '%Y-%m-%d').date()
                end_d = datetime.strptime(end_date_str, '%Y-%m-%d').date()
                invoices = invoices.filter(created_at__date__gte=start_d, created_at__date__lte=end_d)
                period_label = f"{start_d.strftime('%d %b %Y')} to {end_d.strftime('%d %b %Y')}"
            except ValueError:
                pass
        elif filter_type == 'month' and month and year:
            try:
                m = int(month)
                y = int(year)
                invoices = invoices.filter(created_at__year=y, created_at__month=m)
                month_name = datetime(y, m, 1).strftime('%B %Y')
                period_label = f"Month: {month_name}"
            except (ValueError, TypeError):
                pass

        status_label = "All Statuses (Paid, Partial, Unpaid)"
        if payment_status == 'UNPAID_PARTIAL':
            invoices = invoices.filter(payment_status__in=['UNPAID', 'PARTIAL'])
            status_label = "Unpaid & Partial Only"
        elif payment_status and payment_status != 'ALL':
            invoices = invoices.filter(payment_status=payment_status)
            status_label = dict(Invoice.PAYMENT_STATUS_CHOICES).get(payment_status, payment_status)

        total_billed = sum(inv.grand_total for inv in invoices)
        total_paid = sum(inv.amount_paid for inv in invoices)
        total_due = sum(inv.due_amount for inv in invoices)
        total_count = invoices.count()

        context = {
            'company': company,
            'invoices': invoices,
            'period_label': period_label,
            'status_label': status_label,
            'filter_type': filter_type,
            'now': timezone.localtime(timezone.now()),
            'total_billed': total_billed,
            'total_paid': total_paid,
            'total_due': total_due,
            'total_count': total_count,
        }

        html = render_to_string('billing/all_transactions_pdf.html', context)
        buffer = io.BytesIO()

        def link_callback(uri, rel):
            if uri.startswith(settings.MEDIA_URL):
                path = os.path.join(settings.MEDIA_ROOT, uri.replace(settings.MEDIA_URL, "", 1))
            elif settings.MEDIA_URL in uri:
                path = os.path.join(settings.MEDIA_ROOT, uri.split(settings.MEDIA_URL)[-1])
            elif uri.startswith(settings.STATIC_URL):
                path = os.path.join(settings.STATIC_ROOT, uri.replace(settings.STATIC_URL, "", 1))
            elif settings.STATIC_URL in uri:
                path = os.path.join(settings.STATIC_ROOT, uri.split(settings.STATIC_URL)[-1])
            else:
                return uri
            return str(path)

        pisa_status = pisa.CreatePDF(html, dest=buffer, link_callback=link_callback)
        if pisa_status.err:
            return Response({'error': 'PDF generation failed'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        pdf = buffer.getvalue()
        buffer.close()

        timestamp_str = timezone.localtime(timezone.now()).strftime('%Y%m%d_%H%M%S')
        filename = f"transactions_{filter_type}_{timestamp_str}.pdf"

        response = HttpResponse(content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        response.write(pdf)
        return response

    @action(detail=False, methods=['POST'], permission_classes=[permissions.IsAuthenticated])
    def preview(self, request):
        """
        Preview invoice calculations and check stock without saving to database.
        Accepts the same JSON as create.
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # Pull data but DONT save
        data = serializer.validated_data
        items_data = data.get('items', [])
        
        # The serializer has already calculated basic validation.
        # Let's return the preview of what would be created.
        preview_data = serializer.to_representation(Invoice(**data))
        # Note: Invoice number won't be generated since we didn't save.
        preview_data['invoice_number'] = "PREVIEW-ONLY"
        
        return Response(preview_data)

    @action(detail=True, methods=['GET'])
    def download_pdf(self, request, pk=None):
        """
        Produce a professional Jinja-templated PDF using xhtml2pdf.
        This version avoids the pycairo dependency by using svglib 1.5.1.
        """
        from django.template.loader import render_to_string
        from xhtml2pdf import pisa
        from django.utils import timezone
        from core.models import CompanySettings
        from django.conf import settings
        import os
        
        invoice = self.get_object()
        company = CompanySettings.get_settings()
        
        # Context for the template
        context = {
            'invoice': invoice,
            'company': company,
            'now': timezone.now(),
        }

        # Render HTML to string
        html = render_to_string('billing/invoice_pdf.html', context)
        
        # Create a file-like buffer to receive PDF data.
        buffer = io.BytesIO()

        def link_callback(uri, rel):
            # Handle both absolute URLs and relative paths
            if uri.startswith(settings.MEDIA_URL):
                path = os.path.join(settings.MEDIA_ROOT, uri.replace(settings.MEDIA_URL, "", 1))
            elif settings.MEDIA_URL in uri:
                path = os.path.join(settings.MEDIA_ROOT, uri.split(settings.MEDIA_URL)[-1])
            elif uri.startswith(settings.STATIC_URL):
                path = os.path.join(settings.STATIC_ROOT, uri.replace(settings.STATIC_URL, "", 1))
            elif settings.STATIC_URL in uri:
                path = os.path.join(settings.STATIC_ROOT, uri.split(settings.STATIC_URL)[-1])
            else:
                return uri
            
            # Ensure path is a string and return it
            return str(path)

        # Create the PDF object
        pisa_status = pisa.CreatePDF(html, dest=buffer, link_callback=link_callback)
        
        # Check for errors
        if pisa_status.err:
            return Response({'error': 'PDF generation failed'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # Get the value of the BytesIO buffer and write it to the response.
        pdf = buffer.getvalue()
        buffer.close()
        
        response = HttpResponse(content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{invoice.invoice_number}.pdf"'
        response.write(pdf)
        
        return response

    @action(detail=True, methods=['GET'])
    def print_html(self, request, pk=None):
        """
        Produce a printable HTML page of the invoice.
        Useful for direct printing via the browser (Ctrl+P).
        """
        from django.shortcuts import render
        from django.utils import timezone
        
        invoice = self.get_object()
        context = {
            'invoice': invoice,
            'now': timezone.now(),
            'is_printable': True # Can be used to hide/show buttons or standard site layout
        }
        return render(request, 'billing/invoice_print.html', context)

    @action(detail=True, methods=['GET'])
    def thermal_receipt_pdf(self, request, pk=None):
        """
        Produce a PDF optimized for 80mm thermal printers.
        """
        from django.template.loader import render_to_string
        from xhtml2pdf import pisa
        from django.utils import timezone
        from core.models import CompanySettings
        from django.conf import settings
        import os
        
        invoice = self.get_object()
        company = CompanySettings.get_settings()
        
        context = {
            'invoice': invoice,
            'company': company,
            'now': timezone.now(),
        }

        html = render_to_string('billing/thermal_receipt_pdf.html', context)
        buffer = io.BytesIO()

        def link_callback(uri, rel):
            # Handle both absolute URLs and relative paths
            if uri.startswith(settings.MEDIA_URL):
                path = os.path.join(settings.MEDIA_ROOT, uri.replace(settings.MEDIA_URL, "", 1))
            elif settings.MEDIA_URL in uri:
                path = os.path.join(settings.MEDIA_ROOT, uri.split(settings.MEDIA_URL)[-1])
            elif uri.startswith(settings.STATIC_URL):
                path = os.path.join(settings.STATIC_ROOT, uri.replace(settings.STATIC_URL, "", 1))
            elif settings.STATIC_URL in uri:
                path = os.path.join(settings.STATIC_ROOT, uri.split(settings.STATIC_URL)[-1])
            else:
                return uri
            
            # Ensure path is a string and return it
            return str(path)

        pisa_status = pisa.CreatePDF(html, dest=buffer, link_callback=link_callback)
        
        if pisa_status.err:
            return Response({'error': 'PDF generation failed'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        pdf = buffer.getvalue()
        buffer.close()
        
        response = HttpResponse(content_type='application/pdf')
        response['Content-Disposition'] = f'inline; filename="receipt_{invoice.invoice_number}.pdf"'
        response.write(pdf)
        
        return response

    @action(detail=True, methods=['POST'], permission_classes=[permissions.IsAuthenticated])
    def payments(self, request, pk=None):
        """
        Record a payment against this invoice.
        """
        invoice = self.get_object()
        # Ensure we pass invoice to validated data context or read it
        data = request.data.copy()
        data['invoice'] = invoice.id
        
        serializer = PaymentSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        
        amount = serializer.validated_data['amount']
        
        if amount <= 0:
            return Response(
                {'amount': ['Payment amount must be greater than zero.']},
                status=status.HTTP_400_BAD_REQUEST
            )
            
        with transaction.atomic():
            payment = serializer.save()
            
            # Update amount_paid on invoice
            invoice.amount_paid += amount
            invoice.save()
            
        return Response(PaymentSerializer(payment).data, status=status.HTTP_201_CREATED)

    @transaction.atomic
    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        
        # Restore stock for each item in the invoice
        for item in instance.items.all():
            if item.product:
                effective_quantity = item.quantity * 10 if item.unit == 'CENT' else item.quantity
                Product.objects.filter(id=item.product.id).update(
                    stock_quantity=F('stock_quantity') + effective_quantity
                )
                
        return super().destroy(request, *args, **kwargs)

class InvoiceItemViewSet(viewsets.ReadOnlyModelViewSet):
    """Mostly for historical lookup or reporting."""
    queryset = InvoiceItem.objects.all().order_by('-invoice__created_at')
    serializer_class = InvoiceItemSerializer
    permission_classes = [permissions.IsAuthenticated]
    filterset_fields = ['invoice', 'product']
