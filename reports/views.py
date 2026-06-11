from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import permissions, status
from django.utils import timezone
from django.db.models import Sum, F, Count, Q, ExpressionWrapper, FloatField, Case, When, Value
from datetime import datetime, timedelta

from billing.models import Invoice, InvoiceItem, Payment
from products.models import Product
from customers.models import Customer


class DashboardSummaryView(APIView):
    """
    GET /api/dashboard/summary/
    Returns today's sales stats, outstanding balance, low stock alerts,
    and top 5 products sold today.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        range_val = request.query_params.get('range', 'today').lower()
        now = timezone.localtime(timezone.now())
        
        # Default labels
        sales_label = "SALES"
        profit_label = "EST. PROFIT"
        cash_label = "CASH"
        upi_label = "UPI"
        bills_label = "BILLS"
        top_label = "TOP PRODUCTS"

        # Calculate date thresholds
        if range_val == 'weekly':
            from_date = (now - timedelta(days=7)).date()
            date_filter = Q(created_at__date__gte=from_date)
            payment_date_filter = Q(payment_date__date__gte=from_date)
            item_filter = Q(invoice__created_at__date__gte=from_date)
            sales_label = "WEEKLY SALES"
            profit_label = "EST. PROFIT (WEEK)"
            cash_label = "WEEKLY CASH"
            upi_label = "WEEKLY UPI"
            bills_label = "BILLS (WEEK)"
            top_label = "TOP PRODUCTS (WEEK)"
        elif range_val == 'monthly':
            from_date = (now - timedelta(days=30)).date()
            date_filter = Q(created_at__date__gte=from_date)
            payment_date_filter = Q(payment_date__date__gte=from_date)
            item_filter = Q(invoice__created_at__date__gte=from_date)
            sales_label = "MONTHLY SALES"
            profit_label = "EST. PROFIT (MONTH)"
            cash_label = "MONTHLY CASH"
            upi_label = "MONTHLY UPI"
            bills_label = "BILLS (MONTH)"
            top_label = "TOP PRODUCTS (MONTH)"
        elif range_val == 'yearly':
            from_date = (now - timedelta(days=365)).date()
            date_filter = Q(created_at__date__gte=from_date)
            payment_date_filter = Q(payment_date__date__gte=from_date)
            item_filter = Q(invoice__created_at__date__gte=from_date)
            sales_label = "ANNUAL SALES"
            profit_label = "EST. PROFIT (YEAR)"
            cash_label = "ANNUAL CASH"
            upi_label = "ANNUAL UPI"
            bills_label = "BILLS (YEAR)"
            top_label = "TOP PRODUCTS (YEAR)"
        elif range_val == 'all_time':
            date_filter = Q()
            payment_date_filter = Q()
            item_filter = Q()
            sales_label = "ALL-TIME SALES"
            profit_label = "ALL-TIME PROFIT"
            cash_label = "ALL-TIME CASH"
            upi_label = "ALL-TIME UPI"
            bills_label = "ALL-TIME BILLS"
            top_label = "TOP PRODUCTS (ALL TIME)"
        else: # today
            today = now.date()
            date_filter = Q(created_at__date=today)
            payment_date_filter = Q(payment_date__date=today)
            item_filter = Q(invoice__created_at__date=today)
            sales_label = "TODAY'S SALES"
            profit_label = "EST. PROFIT TODAY"
            cash_label = "TODAY'S CASH"
            upi_label = "TODAY'S UPI"
            bills_label = "BILLS TODAY"
            top_label = "TOP PRODUCTS TODAY"

        # Filter invoices for range
        range_invoices = Invoice.objects.filter(date_filter).prefetch_related('payments', 'items', 'items__product')
        range_sales = range_invoices.aggregate(
            total=Sum('grand_total')
        )['total'] or 0

        range_bill_count = range_invoices.count()

        # Calculate Gross Profit
        # Profit = Total Sales - Cost of Goods Sold (COGS)
        # COGS = Sum(item.quantity * item.product.purchase_price * (10 if unit==CENT else 1))
        
        # We can calculate this more efficiently using aggregation
        range_profit_data = range_invoices.values('id').annotate(
            invoice_profit=Sum(
                F('items__total_price') - (
                    F('items__product__purchase_price') * 
                    F('items__quantity') * 
                    ExpressionWrapper(
                        Case(
                            When(items__unit='CENT', then=Value(10)),
                            default=Value(1),
                            output_field=FloatField(),
                        ),
                        output_field=FloatField()
                    )
                ),
                output_field=FloatField()
            )
        ).aggregate(total_profit=Sum('invoice_profit'))
        
        range_profit = range_profit_data['total_profit'] or 0

        # Cash/UPI from Payment records made in range
        payment_agg = Payment.objects.filter(
            payment_date_filter
        ).values('mode').annotate(total=Sum('amount'))

        range_cash = 0
        range_upi = 0
        for entry in payment_agg:
            if entry['mode'] == 'CASH':
                range_cash = float(entry['total'] or 0)
            elif entry['mode'] == 'UPI':
                range_upi = float(entry['total'] or 0)

        # Count initial payments made at invoice creation in the range (includes fully paid and partial payments)
        for inv in range_invoices:
            payments_sum = sum(p.amount for p in inv.payments.all())
            initial_paid = float(inv.amount_paid) - float(payments_sum)
            if initial_paid > 0:
                if inv.payment_method == 'UPI':
                    range_upi += initial_paid
                else:
                    # Treat CASH, CARD, ONLINE, etc. under cash or cash-equivalent for simplicity
                    range_cash += initial_paid

        # Total outstanding across all unpaid/partial invoices (all-time)
        total_outstanding = Invoice.objects.filter(
            payment_status__in=['UNPAID', 'PARTIAL']
        ).aggregate(
            total=Sum(F('grand_total') - F('amount_paid'))
        )['total'] or 0

        # Low stock products - compute using Python property to avoid unit mismatch in SQL
        all_products = Product.objects.filter(is_active=True).values(
            'id', 'name', 'brand', 'stock_quantity', 'min_stock_level'
        )
        low_stock_products = []
        all_stock_products = []
        for p in all_products:
            stock_in_cent = p['stock_quantity'] / 10.0
            min_level = p['min_stock_level']
            is_low = stock_in_cent <= min_level
            p['total_stock_in_cent'] = round(stock_in_cent, 1)
            p['is_low_stock'] = is_low
            all_stock_products.append(p)
            if is_low:
                low_stock_products.append(p)

        # Top 5 products sold in range
        top_products = InvoiceItem.objects.filter(
            item_filter
        ).values('product_name_snapshot').annotate(
            total_quantity=Sum('quantity')
        ).order_by('-total_quantity')[:5]
        top_products_list = [
            {
                'product_name': item['product_name_snapshot'],
                'total_quantity': item['total_quantity'],
            }
            for item in top_products
        ]

        return Response({
            'today_sales': float(range_sales),
            'today_profit': float(range_profit),
            'today_cash': float(range_cash),
            'today_upi': float(range_upi),
            'today_bill_count': range_bill_count,
            'total_outstanding': float(total_outstanding),
            'low_stock_products': low_stock_products,
            'all_stock_products': all_stock_products,
            'top_products_today': top_products_list,
            'sales_label': sales_label,
            'cash_label': cash_label,
            'upi_label': upi_label,
            'bills_label': bills_label,
            'top_label': top_label,
            'profit_label': profit_label,
        })



