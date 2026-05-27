from django.contrib import admin
from .models import Product, Category


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'description', 'created_at')
    search_fields = ('name', 'description')
    ordering = ('name',)


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        'name', 'category', 'brand', 'selling_price', 
        'stock_quantity', 'is_low_stock_status', 'is_active'
    )
    list_filter = ('category', 'brand', 'is_active')
    search_fields = ('name', 'category__name', 'brand', 'sku')
    ordering = ('-created_at',)
    
    # Read-only fields in form
    readonly_fields = ('id', 'created_at', 'updated_at')
    
    # Custom colored indicator for low stock
    @admin.display(description="Stock Status")
    def is_low_stock_status(self, obj):
        if obj.is_low_stock:
            return "⚠️ Low Stock"
        return "✅ In Stock"
