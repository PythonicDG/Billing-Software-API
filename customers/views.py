from rest_framework import viewsets, permissions, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import Customer
from .serializers import CustomerSerializer

class CustomerViewSet(viewsets.ModelViewSet):
    queryset = Customer.objects.all().order_by('-created_at')
    serializer_class = CustomerSerializer
    filter_backends = [filters.SearchFilter]
    permission_classes = [permissions.IsAuthenticated]
    search_fields = ['name', 'phone']
    ordering_fields = ['created_at', 'name']

    @action(detail=True, methods=['GET'])
    def ledger(self, request, pk=None):
        customer = self.get_object()
        invoices = customer.invoices.all().order_by('-created_at')
        
        bills_data = []
        total_outstanding = 0
        
        for inv in invoices:
            outstanding = inv.outstanding_balance
            total_outstanding += outstanding
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
            
        return Response({
            'customer_name': customer.name,
            'customer_phone': customer.phone,
            'bills': bills_data,
            'total_outstanding': float(total_outstanding)
        })
