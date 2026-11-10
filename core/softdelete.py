"""
Soft delete: deleting from the app only hides a record; the row stays in the
database and can be restored (or permanently deleted) from the Django admin.

    Model.objects      -> active rows only (what the app/API sees)
    Model.all_objects  -> every row, including deleted ones (admin, uniqueness checks)

Existing rows get is_deleted=False when the migration runs, so nothing that
exists today changes or disappears.
"""
from django.conf import settings
from django.db import models
from django.utils import timezone


class ActiveManager(models.Manager):
    """Hides soft-deleted rows."""

    def get_queryset(self):
        return super().get_queryset().filter(is_deleted=False)


class ActiveInvoiceChildManager(models.Manager):
    """For invoice items/payments: hides rows whose bill was soft-deleted."""

    def get_queryset(self):
        return super().get_queryset().filter(invoice__is_deleted=False)


class SoftDeleteModel(models.Model):
    is_deleted = models.BooleanField(default=False, db_index=True, editable=False)
    deleted_at = models.DateTimeField(null=True, blank=True, editable=False)
    deleted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, editable=False, related_name='+',
    )

    objects = ActiveManager()          # first manager = default manager
    all_objects = models.Manager()

    class Meta:
        abstract = True

    def soft_delete(self, user=None):
        """Mark as deleted. Does NOT remove the row (Model.delete() still does that)."""
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.deleted_by = user if (user is not None and user.is_authenticated) else None
        # .update() so no save() side effects (stock recalculation, auto_now, etc.)
        type(self).all_objects.filter(pk=self.pk).update(
            is_deleted=True, deleted_at=self.deleted_at, deleted_by=self.deleted_by)

    def restore(self):
        self.is_deleted = False
        self.deleted_at = None
        self.deleted_by = None
        type(self).all_objects.filter(pk=self.pk).update(
            is_deleted=False, deleted_at=None, deleted_by=None)
