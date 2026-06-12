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
        
        invoice = self.get_object()
        
        # Context for the template
        context = {
            'invoice': invoice,
            'now': timezone.now(),
        }

        # Render HTML to string
        html = render_to_string('billing/invoice_pdf.html', context)
        
        # Create a file-like buffer to receive PDF data.
        buffer = io.BytesIO()

        # Create the PDF object
        # Note: We use the default pisa.CreatePDF which works with the pinned svglib
        pisa_status = pisa.CreatePDF(html, dest=buffer)
        
        # Check for errors
        if pisa_status.err:
            return Response({'error': 'PDF generation failed'}, status=status.HTTP_500_INTERNAL_SERVER_VALUE)

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
        
        invoice = self.get_object()
        context = {
            'invoice': invoice,
            'now': timezone.now(),
        }

        html = render_to_string('billing/thermal_receipt_pdf.html', context)
        buffer = io.BytesIO()
        pisa_status = pisa.CreatePDF(html, dest=buffer)
        
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
