from django.contrib import admin
from core.admin_softdelete import SoftDeleteAdminMixin
from .models import Customer

@admin.register(Customer)
class CustomerAdmin(SoftDeleteAdminMixin, admin.ModelAdmin):
    list_display = ("name", "phone", "email", "created_at")
    search_fields = ("name", "phone", "email")
    list_filter = ("created_at",)
    ordering = ("-created_at",)
    readonly_fields = ("id", "created_at", "updated_at")
