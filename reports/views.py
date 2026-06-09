from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import permissions, status
from django.utils import timezone
from django.db.models import Sum, F, Count, Q
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
        now = timezone.now()
        
        # Calculate date thresholds
        if range_val == 'weekly':
            from_date = (now - timedelta(days=7)).date()
            date_filter = Q(created_at__date__gte=from_date)
            payment_date_filter = Q(payment_date__date__gte=from_date)
            item_filter = Q(invoice__created_at__date__gte=from_date)
            sales_label = "WEEKLY SALES"
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
            cash_label = "ANNUAL CASH"
            upi_label = "ANNUAL UPI"
            bills_label = "BILLS (YEAR)"
            top_label = "TOP PRODUCTS (YEAR)"
        elif range_val == 'all_time':
            date_filter = Q()
            payment_date_filter = Q()
            item_filter = Q()
            sales_label = "ALL-TIME SALES"
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
            cash_label = "TODAY'S CASH"
            upi_label = "TODAY'S UPI"
            bills_label = "BILLS TODAY"
            top_label = "TOP PRODUCTS TODAY"

        # Filter invoices for range
        range_invoices = Invoice.objects.filter(date_filter).prefetch_related('payments')
        range_sales = range_invoices.aggregate(
            total=Sum('grand_total')
        )['total'] or 0

        range_bill_count = range_invoices.count()

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
        })


class DailySalesView(APIView):
    """
    GET /api/reports/daily-sales/?date=YYYY-MM-DD
    Returns all invoices for the given date with payment breakdown.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        date_str = request.query_params.get('date')
        if date_str:
            try:
                report_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            except ValueError:
                return Response(
                    {'error': 'Invalid date format. Use YYYY-MM-DD.'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        else:
            report_date = timezone.now().date()

        invoices = Invoice.objects.filter(
            created_at__date=report_date
        ).select_related('customer').prefetch_related('payments', 'items').order_by('-created_at')

        # Per-invoice data
        invoices_data = []
        total_sales = 0
        total_cash = 0
        total_upi = 0

        for inv in invoices:
            total_sales += float(inv.grand_total)

            # Payment breakdown
            payments_data = []
            inv_cash = 0
            inv_upi = 0
            payments_sum = 0.0
            for p in inv.payments.all():
                amount = float(p.amount)
                payments_sum += amount
                if p.mode == 'CASH':
                    inv_cash += amount
                elif p.mode == 'UPI':
                    inv_upi += amount
                payments_data.append({
                    'amount': amount,
                    'mode': p.mode,
                    'payment_date': p.payment_date.isoformat(),
                    'notes': p.notes or '',
                })

            # Add initial payment made at invoice creation
            initial_paid = float(inv.amount_paid) - payments_sum
            if initial_paid > 0:
                if inv.payment_method == 'UPI':
                    inv_upi += initial_paid
                else:
                    inv_cash += initial_paid

            total_cash += inv_cash
            total_upi += inv_upi

            invoices_data.append({
                'id': str(inv.id),
                'invoice_number': inv.invoice_number,
                'date': inv.created_at.isoformat(),
                'customer_name': inv.customer.name if inv.customer else 'Walk-In',
                'customer_phone': inv.customer.phone if inv.customer else '',
                'total': float(inv.grand_total),
                'paid': float(inv.amount_paid),
                'outstanding': float(inv.outstanding_balance),
                'payment_status': inv.payment_status,
                'cash_amount': inv_cash,
                'upi_amount': inv_upi,
                'payments': payments_data,
                'items': [
                    {
                        'product_name': item.product_name_snapshot,
                        'quantity': item.quantity,
                        'unit': item.unit,
                        'unit_price': float(item.unit_price),
                        'total_price': float(item.total_price),
                    }
                    for item in inv.items.all()
                ],
            })

        return Response({
            'date': str(report_date),
            'total_sales': total_sales,
            'total_cash': total_cash,
            'total_upi': total_upi,
            'bill_count': len(invoices_data),
            'invoices': invoices_data,
        })


class OutstandingCustomersView(APIView):
    """
    GET /api/reports/outstanding/
    Returns all customers with outstanding balance > 0, sorted descending.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        # Annotate each customer with their outstanding balance and unpaid bill count
        customers = Customer.objects.annotate(
            calc_outstanding=Sum(
                F('invoices__grand_total') - F('invoices__amount_paid'),
                filter=Q(invoices__payment_status__in=['UNPAID', 'PARTIAL'])
            ),
            unpaid_bill_count=Count(
                'invoices',
                filter=Q(invoices__payment_status__in=['UNPAID', 'PARTIAL'])
            )
        ).filter(
            calc_outstanding__gt=0
        ).order_by('-calc_outstanding')

        customers_data = [
            {
                'id': str(c.id),
                'name': c.name,
                'phone': c.phone,
                'outstanding_balance': float(c.calc_outstanding or 0),
                'unpaid_bill_count': c.unpaid_bill_count or 0,
            }
            for c in customers
        ]

        total_outstanding = sum(c['outstanding_balance'] for c in customers_data)

        return Response({
            'total_outstanding': total_outstanding,
            'customer_count': len(customers_data),
            'customers': customers_data,
        })


class StockSummaryView(APIView):
    """
    GET /api/reports/stock-summary/
    Returns all active products with stock info and value calculations.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        products = Product.objects.filter(is_active=True).order_by('name')

        products_data = []
        total_stock_value = 0
        low_stock_count = 0

        for p in products:
            stock_value = float(p.purchase_price) * p.stock_quantity
            total_stock_value += stock_value
            is_low = p.is_low_stock
            if is_low:
                low_stock_count += 1

            products_data.append({
                'id': str(p.id),
                'name': p.name,
                'brand': p.brand or '',
                'sku': p.sku or '',
                'stock_quantity': p.stock_quantity,
                'min_stock_level': p.min_stock_level,
                'purchase_price': float(p.purchase_price),
                'selling_price': float(p.selling_price),
                'stock_value': stock_value,
                'is_low_stock': is_low,
            })

        return Response({
            'total_products': len(products_data),
            'low_stock_count': low_stock_count,
            'total_stock_value': total_stock_value,
            'products': products_data,
        })


class CustomerSalesView(APIView):
    """
    GET /api/reports/customer-sales/?customer_id=X&from=YYYY-MM-DD&to=YYYY-MM-DD
    Returns all invoices for a customer within a date range.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        customer_id = request.query_params.get('customer_id')
        from_date = request.query_params.get('from')
        to_date = request.query_params.get('to')

        if not customer_id:
            return Response(
                {'error': 'customer_id is required.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            customer = Customer.objects.get(id=customer_id)
        except Customer.DoesNotExist:
            return Response(
                {'error': 'Customer not found.'},
                status=status.HTTP_404_NOT_FOUND
            )

        invoices = customer.invoices.all().order_by('-created_at')

        if from_date:
            try:
                from_dt = datetime.strptime(from_date, '%Y-%m-%d').date()
                invoices = invoices.filter(created_at__date__gte=from_dt)
            except ValueError:
                return Response(
                    {'error': 'Invalid from date format. Use YYYY-MM-DD.'},
                    status=status.HTTP_400_BAD_REQUEST
                )

        if to_date:
            try:
                to_dt = datetime.strptime(to_date, '%Y-%m-%d').date()
                invoices = invoices.filter(created_at__date__lte=to_dt)
            except ValueError:
                return Response(
                    {'error': 'Invalid to date format. Use YYYY-MM-DD.'},
                    status=status.HTTP_400_BAD_REQUEST
                )

        invoices = invoices.prefetch_related('payments', 'items')

        total_billed = 0
        total_paid = 0
        total_outstanding = 0
        invoices_data = []

        for inv in invoices:
            billed = float(inv.grand_total)
            paid = float(inv.amount_paid)
            outstanding = float(inv.outstanding_balance)
            total_billed += billed
            total_paid += paid
            total_outstanding += outstanding

            payments_data = [
                {
                    'amount': float(p.amount),
                    'mode': p.mode,
                    'payment_date': p.payment_date.isoformat(),
                    'notes': p.notes or '',
                }
                for p in inv.payments.all()
            ]

            invoices_data.append({
                'id': str(inv.id),
                'invoice_number': inv.invoice_number,
                'date': inv.created_at.isoformat(),
                'total': billed,
                'paid': paid,
                'outstanding': outstanding,
                'payment_status': inv.payment_status,
                'payments': payments_data,
                'items': [
                    {
                        'product_name': item.product_name_snapshot,
                        'quantity': item.quantity,
                        'unit': item.unit,
                        'unit_price': float(item.unit_price),
                        'total_price': float(item.total_price),
                    }
                    for item in inv.items.all()
                ],
            })

        return Response({
            'customer_name': customer.name,
            'customer_phone': customer.phone,
            'from_date': from_date or '',
            'to_date': to_date or '',
            'total_billed': total_billed,
            'total_paid': total_paid,
            'total_outstanding': total_outstanding,
            'invoice_count': len(invoices_data),
            'invoices': invoices_data,
        })
