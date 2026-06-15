from django.contrib import admin
from .models import CompanySettings, DashboardAccessToken


@admin.register(CompanySettings)
class CompanySettingsAdmin(admin.ModelAdmin):
    list_display = ('name', 'phone', 'gst_number', 'has_pin_display')
    readonly_fields = ('pin_failed_attempts', 'pin_locked_until')
    exclude = ('dashboard_pin_hash',)  # Never show the hash in admin

    def has_pin_display(self, obj):
        return "✅ Yes" if obj.has_pin else "❌ No"
    has_pin_display.short_description = "Dashboard PIN Set"

    def has_add_permission(self, request):
        # Prevent creating more than one settings object
        if self.model.objects.count() >= 1:
            return False
        return super().has_add_permission(request)

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(DashboardAccessToken)
class DashboardAccessTokenAdmin(admin.ModelAdmin):
    list_display = ('user', 'token_preview', 'created_at', 'expires_at', 'is_active', 'is_valid_display')
    list_filter = ('is_active', 'created_at')
    readonly_fields = ('token', 'user', 'created_at', 'expires_at')

    def token_preview(self, obj):
        return f"{obj.token[:8]}..." if obj.token else ""
    token_preview.short_description = "Token"

    def is_valid_display(self, obj):
        return "✅" if obj.is_valid else "❌"
    is_valid_display.short_description = "Valid"

    def has_add_permission(self, request):
        return False  # Tokens are created programmatically only
