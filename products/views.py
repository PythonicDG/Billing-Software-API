from rest_framework import viewsets, filters, status
from rest_framework.response import Response
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
    queryset = Product.objects.all().order_by('-created_at')
    serializer_class = ProductSerializer
    permission_classes = [IsOwnerOrReadOnly]
    pagination_class = StandardResultsSetPagination
    
    # Built-in search & ordering
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'brand', 'sku', 'category__name']
    ordering_fields = ['selling_price', 'stock_quantity', 'created_at']

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
