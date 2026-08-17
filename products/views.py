from rest_framework import viewsets, filters, status
from rest_framework.response import Response
from rest_framework.decorators import action
from django.http import HttpResponse
import csv
import io
from datetime import datetime
from rest_framework.pagination import PageNumberPagination

from .models import Product, Category
from .serializers import ProductSerializer, CategorySerializer
from accounts.permissions import IsOwnerOrReadOnly


class StandardResultsSetPagination(PageNumberPagination):
    """Custom pagination class for better Flutter integration."""
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 100

    def get_paginated_response(self, data):
        return Response({
            'success': True,
            'count': self.page.paginator.count,
            'next': self.get_next_link(),
            'previous': self.get_previous_link(),
            'results': data
        })


class CategoryViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing Categories (Owner can CUD, Staff can Read).
    """
    queryset = Category.objects.all().order_by('name')
    serializer_class = CategorySerializer
    permission_classes = [IsOwnerOrReadOnly]
    pagination_class = None  # No pagination for category dropdowns


class ProductViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing inventory (Owner can CUD, Staff can Read).
    Features: Pagination, Search by name/brand/category, Sorting.
    """
    serializer_class = ProductSerializer
    permission_classes = [IsOwnerOrReadOnly]
    pagination_class = StandardResultsSetPagination
    
    # Built-in search & ordering
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'brand', 'sku', 'category__name']
    ordering_fields = ['selling_price', 'stock_quantity', 'created_at']

    def get_queryset(self):
        """Optionally restricts the returned products based on stock status."""
        from django.db.models import Sum, F
        queryset = Product.objects.all().order_by('-created_at')
        stock_filter = self.request.query_params.get('stock_filter')
        
        if stock_filter == 'low_stock':
            # Low Stock: 0 < stock_quantity <= min_stock_level * 10
            queryset = queryset.filter(stock_quantity__lte=F('min_stock_level') * 10, stock_quantity__gt=0)
        elif stock_filter == 'out_of_stock':
            queryset = queryset.filter(stock_quantity__lte=0)
        elif stock_filter == 'available':
            queryset = queryset.filter(stock_quantity__gt=0)
        elif stock_filter == 'top_sellers':
            from billing.models import InvoiceItem
            from django.db.models import Sum, Case, When
            # Get top 10 most sold product IDs
            top_product_ids = InvoiceItem.objects.filter(
                product__isnull=False,
                product__is_active=True
            ).values('product').annotate(
                total_sold_qty=Sum('quantity')
            ).order_by('-total_sold_qty').values_list('product', flat=True)[:10]
            
            if top_product_ids:
                # Maintain order of sales
                preserved_order = Case(*[When(id=pk, then=pos) for pos, pk in enumerate(top_product_ids)])
                queryset = queryset.filter(id__in=top_product_ids).order_by(preserved_order)
            else:
                queryset = queryset.none()
            
        return queryset

    def create(self, request, *args, **kwargs):
        """Custom create to include success key."""
        response = super().create(request, *args, **kwargs)
        return Response({
            'success': True,
            'message': 'Product added to inventory.',
            'data': response.data
        }, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        """Custom update to include success key."""
        response = super().update(request, *args, **kwargs)
        return Response({
            'success': True,
            'message': 'Product updated successfully.',
            'data': response.data
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'], url_path='export_csv')
    def export_csv(self, request):
        """Exports products to a CSV file, respecting filters and ordering."""
        products = self.filter_queryset(self.get_queryset())
        
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="products.csv"'
        
        writer = csv.writer(response)
        writer.writerow([
            'Name', 'Brand', 'Category', 'SKU', 'Purchase Price', 
            'Selling Price', 'MRP', 'No Of Case', 'Cent In Per Case', 'Min Stock Level'
        ])
        
        for product in products:
            writer.writerow([
                product.name,
                product.brand,
                product.category.name if product.category else '',
                product.sku or '',
                f"{product.purchase_price} / {product.entry_mode}",
                f"{product.selling_price} / {product.entry_mode}",
                product.mrp or '',
                product.no_of_case,
                product.cent_in_per_cs,
                product.min_stock_level
            ])
            
        return response

    @action(detail=False, methods=['get'], url_path='health_analytics')
    def health_analytics(self, request):
        """Returns inventory health analytics."""
        from django.db.models import Sum, F, Count, Q, Case, When, Value, ExpressionWrapper, FloatField
        
        products = Product.objects.all()
        
        # When entry_mode == 'cent', stock_quantity is in pieces (10 pieces = 1 cent),
        # but purchase_price & selling_price are per cent. So multiplier is 0.1.
        # When entry_mode == 'piece', stock_quantity and prices are per piece. Multiplier is 1.0.
        stock_unit_multiplier = Case(
            When(entry_mode='cent', then=Value(0.1)),
            default=Value(1.0),
            output_field=FloatField()
        )
        
        stats = products.aggregate(
            total_value=Sum(
                ExpressionWrapper(
                    F('stock_quantity') * stock_unit_multiplier * F('purchase_price'),
                    output_field=FloatField()
                )
            ),
            potential_revenue=Sum(
                ExpressionWrapper(
                    F('stock_quantity') * stock_unit_multiplier * F('selling_price'),
                    output_field=FloatField()
                )
            ),
            # Low Stock: total_stock_in_cent <= min_stock_level
            # total_stock_in_cent = stock_quantity / 10.0
            low_stock_count=Count('id', filter=Q(stock_quantity__lte=F('min_stock_level') * 10) & Q(stock_quantity__gt=0)),
            out_of_stock_count=Count('id', filter=Q(stock_quantity__lte=0))
        )
        
        return Response({
            'success': True,
            'data': {
                'total_inventory_value': float(stats['total_value'] or 0.0),
                'potential_revenue': float(stats['potential_revenue'] or 0.0),
                'low_stock_items': stats['low_stock_count'] or 0,
                'out_of_stock_items': stats['out_of_stock_count'] or 0,
            }
        })

    @action(detail=False, methods=['get'], url_path='download_template')
    def download_template(self, request):
        """Generates and returns a CSV template for bulk product upload."""
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="products_template.csv"'
        
        writer = csv.writer(response)
        writer.writerow([
            'Name', 'Brand', 'Category', 'SKU', 'Purchase Price', 
            'Selling Price', 'MRP', 'No Of Case', 'Cent In Per Case', 'Min Stock Level'
        ])
        writer.writerow([
            'Standard Crackers 10in1', 'Standard', 'Crackers', '', '150.00',
            '250.00', '300.00', '10', '5', '5'
        ])
        return response

    @action(detail=False, methods=['get'], url_path='frequent')
    def frequent(self, request):
        """Returns the top 10 most frequently sold products."""
        from billing.models import InvoiceItem
        from django.db.models import Sum
        
        # Get top product IDs from InvoiceItem
        top_product_ids = InvoiceItem.objects.filter(product__isnull=False).values('product').annotate(
            total_sold=Sum('quantity')
        ).order_by('-total_sold').values_list('product', flat=True)[:10]
        
        # Filter products that are in the top list and are active
        products = Product.objects.filter(id__in=top_product_ids, is_active=True)
        
        # Sort them manually to maintain the 'total_sold' order
        product_list = sorted(
            products, 
            key=lambda p: list(top_product_ids).index(p.id) if p.id in top_product_ids else 999
        )
        
        serializer = self.get_serializer(product_list, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['post'], url_path='bulk_upload')
    def bulk_upload(self, request):
        """Parses an uploaded CSV file and performs bulk creation/updating of products."""
        csv_file = request.FILES.get('file')
        if not csv_file:
            return Response(
                {'success': False, 'error': 'No file was provided.'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            file_data = csv_file.read().decode('utf-8-sig')
            io_string = io.StringIO(file_data)
            reader = csv.reader(io_string)
            
            header = next(reader, None)
            if not header:
                return Response(
                    {'success': False, 'error': 'The uploaded file is empty.'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            headers_map = {name.strip().lower(): i for i, name in enumerate(header)}
            
            def get_val(row, field_name, default=''):
                idx = headers_map.get(field_name.lower())
                if idx is not None and idx < len(row):
                    return row[idx].strip()
                return default

            created_count = 0
            updated_count = 0
            errors = []

            from decimal import Decimal
            from products.models import Category, Product

            for row_idx, row in enumerate(reader, start=2):
                if not row or not any(row):
                    continue
                
                name = get_val(row, 'name')
                selling_price_str = get_val(row, 'selling price')

                if not name:
                    errors.append(f"Row {row_idx}: Name is required.")
                    continue
                if not selling_price_str:
                    errors.append(f"Row {row_idx}: Selling Price is required.")
                    continue

                try:
                    selling_price = Decimal(selling_price_str)
                except Exception:
                    errors.append(f"Row {row_idx}: Invalid Selling Price '{selling_price_str}'.")
                    continue

                brand = get_val(row, 'brand')
                category_name = get_val(row, 'category', 'General')
                sku = get_val(row, 'sku')
                
                purchase_price_str = get_val(row, 'purchase price', '0.00')
                mrp_str = get_val(row, 'mrp')
                no_of_case_str = get_val(row, 'no of case', '0')
                cent_in_per_cs_str = get_val(row, 'cent in per case', '0')
                min_stock_str = get_val(row, 'min stock level', '5')

                try:
                    purchase_price = Decimal(purchase_price_str) if purchase_price_str else Decimal('0.00')
                    mrp = Decimal(mrp_str) if mrp_str else None
                    no_of_case = int(no_of_case_str) if no_of_case_str else 0
                    cent_in_per_cs = Decimal(cent_in_per_cs_str) if cent_in_per_cs_str else Decimal('0.00')
                    min_stock = int(min_stock_str) if min_stock_str else 5
                except Exception as e:
                    errors.append(f"Row {row_idx}: Formatting error in numbers: {e}")
                    continue

                category = None
                if category_name:
                    category, _ = Category.objects.get_or_create(name=category_name)

                product = None
                if sku:
                    product = Product.objects.filter(sku=sku).first()

                # Determine entry_mode based on cent_in_per_cs if possible, 
                # but for bulk upload, default to 'cent' as existing data is cent-based.
                # Assuming incoming CSV data uses cent logic for cent_in_per_cs.
                
                if product:
                    product.name = name
                    product.brand = brand
                    product.category = category
                    product.purchase_price = purchase_price
                    product.selling_price = selling_price
                    product.mrp = mrp
                    product.no_of_case = no_of_case
                    product.cent_in_per_cs = cent_in_per_cs
                    product.min_stock_level = min_stock
                    product.save()
                    updated_count += 1
                else:
                    Product.objects.create(
                        name=name,
                        brand=brand,
                        category=category,
                        sku=sku if sku else None,
                        purchase_price=purchase_price,
                        selling_price=selling_price,
                        mrp=mrp,
                        no_of_case=no_of_case,
                        cent_in_per_cs=cent_in_per_cs,
                        min_stock_level=min_stock,
                        entry_mode='cent' # Default for imported products
                    )
                    created_count += 1

            return Response({
                'success': True,
                'created_count': created_count,
                'updated_count': updated_count,
                'errors': errors
            }, status=status.HTTP_200_OK if not errors else status.HTTP_207_MULTI_STATUS)

        except Exception as e:
            return Response(
                {'success': False, 'error': f'Failed to process file: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
