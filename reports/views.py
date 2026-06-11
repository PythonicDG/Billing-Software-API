from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import permissions, status
from django.utils import timezone
from django.db.models import Sum, F, Count, Q, ExpressionWrapper, FloatField, Case, When, Value
from django.template.loader import render_to_string
from django.http import HttpResponse
from datetime import datetime, timedelta
from xhtml2pdf import pisa
import io

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


class CustomerInsightsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        insight_type = request.query_params.get('type', 'outstanding')
        download = request.query_params.get('download', 'false') == 'true'

        if insight_type == 'outstanding':
            customers = Customer.objects.all()
            data = []
            for c in customers:
                balance = c.outstanding_balance
                if balance > 0:
                    last_inv = c.invoices.order_by('-created_at').first()
                    days_overdue = (timezone.now() - last_inv.created_at).days if last_inv else 0
                    data.append({
                        'name': c.name,
                        'phone': c.phone,
                        'outstanding': balance,
                        'days_overdue': days_overdue
                    })
            
            data = sorted(data, key=lambda x: x['outstanding'], reverse=True)

            if download:
                context = {'customers': data, 'now': timezone.now()}
                html = render_to_string('reports/outstanding_list_pdf.html', context)
                buffer = io.BytesIO()
                pisa_status = pisa.CreatePDF(html, dest=buffer)
                if pisa_status.err:
                    return Response({'error': 'PDF generation failed'}, status=500)
                pdf = buffer.getvalue()
                buffer.close()
                response = HttpResponse(pdf, content_type='application/pdf')
                response['Content-Disposition'] = 'attachment; filename="outstanding_report.pdf"'
                return response

            return Response(data)

        elif insight_type == 'top_customers':
            customers = Customer.objects.annotate(
                total_business=Sum('invoices__grand_total'),
                visit_frequency=Count('invoices')
            ).order_by('-total_business')[:20]
            
            data = [{
                'name': c.name,
                'phone': c.phone,
                'total_business': float(c.total_business or 0),
                'visit_frequency': c.visit_frequency
            } for c in customers]
            return Response(data)

        return Response({"error": "Invalid type"}, status=400)


class SalesAnalyticsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        days = int(request.query_params.get('days', 30))
        from_date = (timezone.now() - timedelta(days=days)).date()

        sales_data = Invoice.objects.filter(created_at__date__gte=from_date).values('created_at__date').annotate(
            revenue=Sum('grand_total')
        ).order_by('created_at__date')
        
        # Correctly calculate payment split including initial invoice payments
        invoices = Invoice.objects.filter(created_at__date__gte=from_date).prefetch_related('payments')
        
        cash_total = 0
        upi_total = 0
        
        # Calculate from Payment objects
        payments = Payment.objects.filter(payment_date__date__gte=from_date)
        for p in payments:
            if p.mode == 'CASH':
                cash_total += float(p.amount)
            elif p.mode == 'UPI':
                upi_total += float(p.amount)
                
        # Calculate initial payments (amount_paid - sum of payments for that invoice)
        for inv in invoices:
            total_payments = inv.payments.aggregate(Sum('amount'))['amount__sum'] or 0
            initial_paid = float(inv.amount_paid) - float(total_payments)
            if initial_paid > 0:
                if inv.payment_method == 'UPI':
                    upi_total += initial_paid
                else:
                    cash_total += initial_paid

        payment_split = [
            {'mode': 'CASH', 'total': cash_total},
            {'mode': 'UPI', 'total': upi_total}
        ]
        
        product_data = InvoiceItem.objects.filter(invoice__created_at__date__gte=from_date).values('product_name_snapshot').annotate(
            units_sold=Sum('quantity')
        ).order_by('-units_sold')[:20]

        category_data = InvoiceItem.objects.filter(invoice__created_at__date__gte=from_date).values('product__category__name').annotate(
            revenue=Sum('total_price')
        ).order_by('-revenue')

        return Response({
            'sales_over_time': [{'date': str(s['created_at__date']), 'revenue': float(s['revenue'])} for s in sales_data],
            'payment_split': payment_split,
            'product_performance': [{'name': p['product_name_snapshot'], 'units_sold': p['units_sold']} for p in product_data],
            'category_performance': [{'category': c['product__category__name'] or 'Uncategorized', 'revenue': float(c['revenue'])} for c in category_data]
        })


class OperationsFinanceView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        today = timezone.localtime(timezone.now()).date()
        download = request.query_params.get('download', 'false') == 'true'
        report_type = request.query_params.get('type', 'daily_snapshot')

        if report_type == 'daily_snapshot':
            invoices = Invoice.objects.filter(created_at__date=today).prefetch_related('payments', 'items', 'items__product')
            total_sales = invoices.aggregate(Sum('grand_total'))['grand_total__sum'] or 0
            
            # Use the same robust calculation as DashboardSummaryView
            cash_received = 0
            upi_received = 0
            
            # From Payment objects today
            payments_today = Payment.objects.filter(payment_date__date=today)
            for p in payments_today:
                if p.mode == 'CASH':
                    cash_received += float(p.amount)
                elif p.mode == 'UPI':
                    upi_received += float(p.amount)
            
            # From initial payments of invoices created today
            for inv in invoices:
                # We only subtract payments that happened TODAY to get the "initial" part
                # Actually, any payment recorded in the Payment table is already counted above.
                # So we just need to add (inv.amount_paid - total_payments_ever_on_this_inv)
                # No, that's not right. If an invoice was created today with 100 paid,
                # and then a payment of 50 was recorded TODAY.
                # amount_paid = 150. Payment table = 50.
                # Today's received should be 150.
                # 50 (from payment) + (150 - 50) (initial) = 150. Correct.
                
                total_payments_on_inv = inv.payments.aggregate(Sum('amount'))['amount__sum'] or 0
                initial_paid = float(inv.amount_paid) - float(total_payments_on_inv)
                if initial_paid > 0:
                    if inv.payment_method == 'UPI':
                        upi_received += initial_paid
                    else:
                        cash_received += initial_paid
            
            new_credit = 0
            for inv in invoices:
                new_credit += float(inv.outstanding_balance)

            # Calculate today's profit
            profit_data = invoices.values('id').annotate(
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
            
            total_profit = profit_data['total_profit'] or 0

            return Response({
                'total_sales': float(total_sales),
                'cash_received': float(cash_received),
                'upi_received': float(upi_received),
                'new_credit': float(new_credit),
                'total_profit': float(total_profit),
                'bill_count': invoices.count()
            })

        elif report_type == 'low_stock':
            all_products = Product.objects.filter(is_active=True)
            low_stock_list = []
            for p in all_products:
                if p.total_stock_in_cent <= p.min_stock_level:
                    low_stock_list.append({
                        'name': p.name,
                        'brand': p.brand,
                        'stock': p.total_stock_in_cent,
                        'min_level': p.min_stock_level
                    })
            
            if download:
                context = {'products': low_stock_list, 'now': timezone.now()}
                html = render_to_string('reports/low_stock_pdf.html', context)
                buffer = io.BytesIO()
                pisa_status = pisa.CreatePDF(html, dest=buffer)
                if pisa_status.err:
                    return Response({'error': 'PDF generation failed'}, status=500)
                pdf = buffer.getvalue()
                buffer.close()
                response = HttpResponse(pdf, content_type='application/pdf')
                response['Content-Disposition'] = 'attachment; filename="low_stock_report.pdf"'
                return response
            
            return Response(low_stock_list)
            
        return Response({"error": "Invalid type"}, status=400)
