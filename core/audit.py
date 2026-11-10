from django.db import transaction
from django.db.models.fields.files import FieldFile

from .models import AuditLog


def _client_ip(request):
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR') or None


def _user_label(user):
    who = user.email or user.username
    role = getattr(user, 'role', '')
    return f"{who} ({role})" if role else who


def log_action(request, action, entity_type, entity_id, entity_label, summary, reason='', details=None):
    """Write one audit entry. Call inside the same transaction as the change it records."""
    user = getattr(request, 'user', None)
    if user is not None and not user.is_authenticated:
        user = None
    return AuditLog.objects.create(
        user=user,
        user_label=_user_label(user) if user else '',
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id or ''),
        entity_label=(entity_label or '')[:255],
        summary=summary[:500],
        reason=(reason or '').strip(),
        details=details or {},
        ip_address=_client_ip(request),
    )


def snapshot(instance, fields):
    """Small plain-text copy of the given fields, for create/delete entries."""
    data = {}
    for name in fields:
        value = getattr(instance, name, None)
        if isinstance(value, FieldFile):          # FileField / ImageField
            data[name] = value.name or None
        elif value is None or value == '':
            data[name] = None
        else:
            data[name] = str(value)
    return data


def changes(before, after):
    """Only the fields that changed: {field: {'from': old, 'to': new}}."""
    return {k: {'from': before.get(k), 'to': after.get(k)}
            for k in after if before.get(k) != after.get(k)}


def _reason(request):
    """Optional reason, sent as a body field or a ?reason= query parameter."""
    data = getattr(request, 'data', None)
    reason = data.get('reason') if hasattr(data, 'get') else None
    return reason or request.query_params.get('reason', '')


class AuditedViewSetMixin:
    """
    Adds audit entries to a ModelViewSet's create / update / delete.

    Set on the viewset:
        audit_entity_type = 'Customer'
        audit_fields = ['name', 'phone', ...]      # what to record (keep it short)
    and optionally override audit_label(instance).

    Entries stay small: create/delete store the listed fields, edits store only
    the fields that changed. Nothing is logged for an edit that changed nothing.
    """
    audit_entity_type = None
    audit_fields = ()

    def audit_label(self, instance):
        return str(instance)

    def _audit_snapshot(self, instance):
        return snapshot(instance, self.audit_fields)

    def perform_create(self, serializer):
        with transaction.atomic():
            super().perform_create(serializer)
            obj = serializer.instance
            label = self.audit_label(obj)
            log_action(
                self.request, AuditLog.CREATE, self.audit_entity_type, obj.pk, label,
                f"Created {self.audit_entity_type.lower()} {label}",
                details={'data': self._audit_snapshot(obj)},
            )

    def perform_update(self, serializer):
        with transaction.atomic():
            before = self._audit_snapshot(serializer.instance)
            super().perform_update(serializer)
            obj = serializer.instance
            diff = changes(before, self._audit_snapshot(obj))
            if diff:
                label = self.audit_label(obj)
                log_action(
                    self.request, AuditLog.UPDATE, self.audit_entity_type, obj.pk, label,
                    f"Edited {self.audit_entity_type.lower()} {label} ({', '.join(diff)})",
                    reason=_reason(self.request),
                    details={'changes': diff},
                )

    def perform_destroy(self, instance):
        with transaction.atomic():
            pk, label, data = instance.pk, self.audit_label(instance), self._audit_snapshot(instance)
            soft = hasattr(instance, 'soft_delete')
            if soft:
                # From the app a delete only hides the record; the admin can restore it.
                instance.soft_delete(self.request.user)
            else:
                super().perform_destroy(instance)
            log_action(
                self.request, AuditLog.DELETE, self.audit_entity_type, pk, label,
                f"Deleted {self.audit_entity_type.lower()} {label}",
                reason=_reason(self.request),
                details={'data': data, 'soft_deleted': soft},
            )
