from .models import AuditLog


def _client_ip(request):
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR') or None


def log_action(request, action, entity_type, entity_id, entity_label, summary, reason='', details=None):
    """Write one audit entry. Call inside the same transaction as the change it records."""
    user = getattr(request, 'user', None)
    if user is not None and not user.is_authenticated:
        user = None
    return AuditLog.objects.create(
        user=user,
        user_label=f"{user.email} ({user.role})" if user else '',
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id),
        entity_label=entity_label,
        summary=summary,
        reason=(reason or '').strip(),
        details=details or {},
        ip_address=_client_ip(request),
    )
