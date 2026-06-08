from django.contrib import admin
from .models import Invoice, InvoiceItem

class InvoiceItemInline(admin.TabularInline):
    model = InvoiceItem
    extra = 1
    readonly_fields = ("id", "total_price")

@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ("invoice_number", "customer", "grand_total", "amount_paid", "payment_status", "created_at")
    list_filter = ("payment_status", "payment_method", "created_at")
    search_fields = ("invoice_number", "customer__name", "customer__phone")
    inlines = [InvoiceItemInline]
    readonly_fields = ("id", "invoice_number", "created_at", "updated_at")

@admin.register(InvoiceItem)
class InvoiceItemAdmin(admin.ModelAdmin):
    list_display = ("invoice", "product_name_snapshot", "quantity", "unit", "unit_price", "total_price")
    list_filter = ("unit",)
    search_fields = ("invoice__invoice_number", "product_name_snapshot", "sku_snapshot")
