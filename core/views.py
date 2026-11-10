from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from .models import CompanySettings, DashboardAccessToken, AppRelease, AuditLog
from .serializers import (
    CompanySettingsSerializer, 
    DashboardPinSetSerializer, 
    DashboardPinVerifySerializer,
    AppReleaseSerializer,
    AuditLogSerializer,
)
from .audit import log_action, snapshot, changes

SETTINGS_AUDIT_FIELDS = ['name', 'address', 'phone', 'logo', 'gst_number', 'receipt_message']


class CompanySettingsViewSet(viewsets.GenericViewSet):
    queryset = CompanySettings.objects.all()
    serializer_class = CompanySettingsSerializer
    permission_classes = [permissions.IsAuthenticated]

    def list(self, request):
        settings = CompanySettings.get_settings()
        serializer = self.get_serializer(settings)
        return Response(serializer.data)

    @action(detail=False, methods=['patch', 'put'])
    def update_settings(self, request):
        settings = CompanySettings.get_settings()
        serializer = self.get_serializer(settings, data=request.data, partial=True)
        if serializer.is_valid():
            before = snapshot(settings, SETTINGS_AUDIT_FIELDS)
            serializer.save()
            diff = changes(before, snapshot(settings, SETTINGS_AUDIT_FIELDS))
            if diff:
                log_action(request, AuditLog.UPDATE, 'Settings', settings.pk, settings.name,
                           f"Edited company settings ({', '.join(diff)})",
                           details={'changes': diff})
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class DashboardPinViewSet(viewsets.GenericViewSet):
    """
    Manages the global dashboard PIN for the application.
    
    Endpoints:
        GET  /status/       — Check if a PIN is set (any authenticated user)
        POST /set_pin/      — Set or update the PIN 
        POST /verify/       — Verify PIN and get a temporary access token
        POST /revoke/       — Revoke the current dashboard access token
        POST /remove_pin/   — Remove PIN protection entirely 
    """
    permission_classes = [permissions.IsAuthenticated]

    @action(detail=False, methods=['GET'])
    def status(self, request):
        """Check if a dashboard PIN is currently set."""
        settings_obj = CompanySettings.get_settings()
        return Response({
            'has_pin': settings_obj.has_pin,
            'is_locked': settings_obj.is_locked,
            'lockout_remaining_seconds': settings_obj.lockout_remaining_seconds,
        })

    @action(detail=False, methods=['POST'])
    def set_pin(self, request):
        """Set or update the dashboard PIN."""
        serializer = DashboardPinSetSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        settings_obj = CompanySettings.get_settings()
        had_pin = settings_obj.has_pin
        settings_obj.set_pin(serializer.validated_data['pin'])
        log_action(request, AuditLog.UPDATE if had_pin else AuditLog.CREATE,
                   'Dashboard PIN', settings_obj.pk, 'Dashboard PIN',
                   'Changed dashboard PIN' if had_pin else 'Set dashboard PIN')

        return Response({
            'message': 'Dashboard PIN has been set successfully.',
            'has_pin': True,
        })

    @action(detail=False, methods=['POST'])
    def verify(self, request):
        """
        Verify the PIN and issue a temporary dashboard access token.
        Returns the token and its expiry time on success.
        """
        serializer = DashboardPinVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        settings_obj = CompanySettings.get_settings()

        # If no PIN is set, no verification needed
        if not settings_obj.has_pin:
            return Response({
                'message': 'No PIN is set. Dashboard is accessible.',
                'has_pin': False,
            })

        raw_pin = serializer.validated_data['pin']
        success, error_msg, attempts_remaining = settings_obj.check_pin(raw_pin)

        if success:
            # Create a temporary access token
            token_obj = DashboardAccessToken.create_for_user(request.user)
            return Response({
                'message': 'PIN verified successfully.',
                'dashboard_token': token_obj.token,
                'expires_at': token_obj.expires_at.isoformat(),
            })
        else:
            response_data = {
                'error': error_msg,
                'attempts_remaining': attempts_remaining,
                'is_locked': settings_obj.is_locked,
            }
            if settings_obj.is_locked:
                response_data['lockout_remaining_seconds'] = settings_obj.lockout_remaining_seconds

            return Response(response_data, status=status.HTTP_403_FORBIDDEN)

    @action(detail=False, methods=['POST'])
    def revoke(self, request):
        """Revoke all active dashboard access tokens for the current user."""
        DashboardAccessToken.revoke_for_user(request.user)
        return Response({'message': 'Dashboard access revoked.'})

    @action(detail=False, methods=['POST'])
    def remove_pin(self, request):
        """Remove the dashboard PIN entirely."""
        settings_obj = CompanySettings.get_settings()
        had_pin = settings_obj.has_pin
        settings_obj.remove_pin()
        if had_pin:
            log_action(request, AuditLog.DELETE, 'Dashboard PIN', settings_obj.pk,
                       'Dashboard PIN', 'Removed dashboard PIN')

        # Also revoke all active tokens since PIN is removed
        DashboardAccessToken.objects.filter(is_active=True).update(is_active=False)

        return Response({
            'message': 'Dashboard PIN has been removed. Dashboard is now accessible without a PIN.',
            'has_pin': False,
        })


class AppUpdateViewSet(viewsets.ViewSet):
    """
    Public endpoint to check for the latest desktop app release.
    GET /api/core/app-update/latest/
    """
    permission_classes = [permissions.AllowAny]

    @action(detail=False, methods=['GET'])
    def latest(self, request):
        latest_release = AppRelease.objects.filter(is_active=True).first()
        if not latest_release:
            return Response({
                'has_update': False,
                'message': 'No active releases available.',
            }, status=status.HTTP_200_OK)

        serializer = AppReleaseSerializer(latest_release, context={'request': request})
        return Response({
            'has_update': True,
            'release': serializer.data,
        }, status=status.HTTP_200_OK)



class IsOwner(permissions.BasePermission):
    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and (user.role == 'OWNER' or user.is_superuser))


class AuditLogPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = 'page_size'
    max_page_size = 200


class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    """
    GET /api/core/audit-logs/ — Owner only, newest first, 50 per page (?page=2).
    Filters: ?action=DELETE &entity_type=Invoice &entity_id= &user= &date_from=YYYY-MM-DD &date_to=YYYY-MM-DD &search=
    """
    queryset = AuditLog.objects.all()
    serializer_class = AuditLogSerializer
    permission_classes = [IsOwner]
    pagination_class = AuditLogPagination

    def get_queryset(self):
        from django.db.models import Q
        qs = super().get_queryset()
        params = self.request.query_params
        for field in ('action', 'entity_type', 'entity_id', 'user'):
            if params.get(field):
                qs = qs.filter(**{field: params[field]})
        if params.get('date_from'):
            qs = qs.filter(timestamp__date__gte=params['date_from'])
        if params.get('date_to'):
            qs = qs.filter(timestamp__date__lte=params['date_to'])
        if params.get('search'):
            q = params['search']
            qs = qs.filter(Q(entity_label__icontains=q) | Q(summary__icontains=q)
                           | Q(reason__icontains=q) | Q(user_label__icontains=q))
        return qs
