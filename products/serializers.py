from rest_framework import serializers
from .models import Product, Category


class CategorySerializer(serializers.ModelSerializer):
    """Serializer for Categories."""
    class Meta:
        model = Category
        fields = ['id', 'name', 'description', 'created_at']


class ProductSerializer(serializers.ModelSerializer):
    """Serializer for Products with brand, stock, and category info."""
    is_low_stock = serializers.ReadOnlyField()
    category = serializers.PrimaryKeyRelatedField(queryset=Category.objects.all(), required=False, allow_null=True)
    category_name = serializers.CharField(source='category.name', read_only=True)

    class Meta:
        model = Product
        fields = [
            'id', 'name', 'brand', 'sku', 
            'purchase_price', 'selling_price', 'mrp', 
            'stock_quantity', 'min_stock_level', 'image',
            'is_low_stock', 'category', 'category_name', 'is_active', 'created_at'
        ]
