from django.contrib import admin, messages

from .audit import log_action
from .models import AuditLog


class DeletedFilter(admin.SimpleListFilter):
    title = 'status'
    parameter_name = 'deleted'

    def lookups(self, request, model_admin):
        return [('no', 'Active'), ('yes', 'Deleted (recoverable)')]

    def queryset(self, request, queryset):
        if self.value() == 'yes':
            return queryset.filter(is_deleted=True)
        if self.value() == 'no':
            return queryset.filter(is_deleted=False)
        return queryset


class SoftDeleteAdminMixin:
    """
    Admin for soft-deletable models:
      * shows active AND deleted rows (filter "status" on the right),
      * "Restore selected" brings deleted rows back,
      * the normal admin delete is the PERMANENT delete (and is logged).
    """
    actions = ['restore_selected']

    def get_queryset(self, request):
        qs = self.model.all_objects.get_queryset()
        ordering = self.get_ordering(request)
        return qs.order_by(*ordering) if ordering else qs

    def get_list_display(self, request):
        return (*super().get_list_display(request), 'deleted_status')

    def get_list_filter(self, request):
        return (DeletedFilter, *super().get_list_filter(request))

    def get_readonly_fields(self, request, obj=None):
        return (*super().get_readonly_fields(request, obj), 'is_deleted', 'deleted_at', 'deleted_by')

    @admin.display(description='Status', ordering='is_deleted')
    def deleted_status(self, obj):
        return '🗑 Deleted' if obj.is_deleted else '✅ Active'

    # --- restore -----------------------------------------------------------
    def on_restore(self, request, obj):
        """Hook for model-specific work (e.g. bills take their stock again)."""

    @admin.action(description='♻ Restore selected (undo delete)')
    def restore_selected(self, request, queryset):
        count = 0
        for obj in queryset.filter(is_deleted=True):
            self.on_restore(request, obj)
            obj.restore()
            log_action(request, AuditLog.UPDATE, self.model.__name__, obj.pk, str(obj),
                       f"Restored {self.model._meta.verbose_name} {obj} (admin)")
            count += 1
        self.message_user(request, f"Restored {count} record(s).", messages.SUCCESS)

    # --- permanent delete --------------------------------------------------
    def delete_model(self, request, obj):
        pk, label = obj.pk, str(obj)
        super().delete_model(request, obj)
        log_action(request, AuditLog.DELETE, self.model.__name__, pk, label,
                   f"Permanently deleted {self.model._meta.verbose_name} {label} (admin)",
                   details={'permanent': True})

    def delete_queryset(self, request, queryset):
        rows = [(o.pk, str(o)) for o in queryset]
        super().delete_queryset(request, queryset)
        for pk, label in rows:
            log_action(request, AuditLog.DELETE, self.model.__name__, pk, label,
                       f"Permanently deleted {self.model._meta.verbose_name} {label} (admin)",
                       details={'permanent': True})
