from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from rest_framework import viewsets, permissions, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.authentication import TokenAuthentication
from rest_framework.pagination import PageNumberPagination
from core.authentication import QueryParameterTokenAuthentication
from .models import Customer
from .serializers import CustomerSerializer
from django.db import transaction, models
from core.audit import AuditedViewSetMixin, log_action
from core.models import AuditLog

class LedgerPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100

class CustomerViewSet(AuditedViewSetMixin, viewsets.ModelViewSet):
    queryset = Customer.objects.all().order_by('-created_at')
    serializer_class = CustomerSerializer
    filter_backends = [filters.SearchFilter]
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [TokenAuthentication, QueryParameterTokenAuthentication]
    search_fields = ['name', 'phone']
    ordering_fields = ['created_at', 'name']

    audit_entity_type = 'Customer'
    audit_fields = ['name', 'phone', 'email', 'address']

    def audit_label(self, instance):
        return f"{instance.name} ({instance.phone})"

    def destroy(self, request, *args, **kwargs):
        customer = self.get_object()
        if customer.invoices.exists():
            return Response(
                {'error': 'This customer has invoices and cannot be deleted.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=['GET'])
    def ledger(self, request, pk=None):
        customer = self.get_object()
        invoices = customer.invoices.all().order_by('-created_at')
        
        paginator = LedgerPagination()
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
                'invoice_number': inv.invoice_number,
                'date': inv.created_at.isoformat(),
                'total': float(inv.total_amount),
                'paid': float(inv.amount_paid),
                'outstanding': float(outstanding),
                'payment_method': inv.payment_method,
                'payments': payments_data
            })
            
        data = {
            'customer_name': customer.name,
            'customer_phone': customer.phone,
            'bills': bills_data,
            'total_outstanding': float(customer.outstanding_balance)
        }
        
        if page is not None:
            return Response({
                'count': paginator.page.paginator.count,
                'next': paginator.get_next_link(),
                'previous': paginator.get_previous_link(),
                'customer_name': customer.name,
                'customer_phone': customer.phone,
                'bills': bills_data,
                'total_outstanding': float(customer.outstanding_balance)
            })

        return Response(data)

    @action(detail=True, methods=['POST'])
    def record_bulk_payment(self, request, pk=None):
        customer = self.get_object()
        amount = request.data.get('amount')
        mode = request.data.get('mode', 'CASH')
        notes = request.data.get('notes', '')

        # Money maths is done in Decimal (rounded to paise) to avoid float drift.
        try:
            amount = Decimal(str(amount).strip()).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        except (InvalidOperation, ValueError, TypeError):
            return Response({'error': 'Invalid amount'}, status=status.HTTP_400_BAD_REQUEST)

        if not amount.is_finite() or amount <= 0:
            return Response({'error': 'Invalid amount'}, status=status.HTTP_400_BAD_REQUEST)

        from billing.models import Invoice, Payment

        mode = str(mode).strip().upper() if mode is not None else 'CASH'
        valid_modes = [m for m, _ in Payment.PAYMENT_MODE_CHOICES]
        if mode not in valid_modes:
            return Response(
                {'error': f"Invalid mode. Must be one of: {', '.join(valid_modes)}"},
                status=status.HTTP_400_BAD_REQUEST
            )

        with transaction.atomic():
            # Get outstanding invoices for this customer, oldest first
            invoices = customer.invoices.filter(amount_paid__lt=models.F('grand_total')).order_by('created_at')
            
            remaining_payment = amount
            applied = []
            for invoice in invoices:
                if remaining_payment <= 0:
                    break
                
                outstanding = Decimal(invoice.grand_total) - Decimal(invoice.amount_paid)
                payment_to_apply = min(remaining_payment, outstanding)
                
                Payment.objects.create(
                    invoice=invoice,
                    amount=payment_to_apply,
                    mode=mode,
                    notes=f"{notes} (Bulk payment)".strip()
                )
                
                invoice.amount_paid = Decimal(invoice.amount_paid) + payment_to_apply
                invoice.save()
                applied.append({'invoice': invoice.invoice_number, 'amount': str(payment_to_apply)})
                
                remaining_payment -= payment_to_apply

            if applied:
                log_action(
                    request, AuditLog.PAYMENT, 'Customer', customer.id,
                    f"{customer.name} ({customer.phone})",
                    f"Recorded {mode} bulk payment of {amount - remaining_payment} for {customer.name}",
                    details={'amount': str(amount - remaining_payment), 'mode': mode,
                             'notes': notes or '', 'applied_to': applied},
                )
            
            # If there's still remaining_payment, it could be "advance payment"
            # In this simple system, we'll just return the remaining amount.

        return Response({
            'status': 'success', 
            'applied_amount': float(amount - remaining_payment),
            'remaining_advance': float(remaining_payment)
        })

    @action(detail=True, methods=['GET'])
    def download_statement(self, request, pk=None):
        from django.template.loader import render_to_string
        from xhtml2pdf import pisa
        from django.utils import timezone
        import io
        from django.http import HttpResponse

        customer = self.get_object()
        invoices = customer.invoices.all().order_by('created_at')
        
        # Context for the template
        context = {
            'customer': customer,
            'invoices': invoices,
            'now': timezone.now(),
            'total_billed': sum(inv.grand_total for inv in invoices),
            'total_paid': sum(inv.amount_paid for inv in invoices),
            'total_outstanding': customer.outstanding_balance
        }

        # Render HTML to string
        html = render_to_string('billing/customer_statement_pdf.html', context)
        
        # Create a file-like buffer to receive PDF data.
        buffer = io.BytesIO()
        pisa_status = pisa.CreatePDF(html, dest=buffer)
        
        if pisa_status.err:
            return Response({'error': 'PDF generation failed'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        pdf = buffer.getvalue()
        buffer.close()
        
        response = HttpResponse(content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="statement_{customer.name}.pdf"'
        response.write(pdf)
        
        return response
