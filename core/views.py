from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import CompanySettings, DashboardAccessToken
from .serializers import CompanySettingsSerializer, DashboardPinSetSerializer, DashboardPinVerifySerializer
from accounts.permissions import IsOwner


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
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['GET'], permission_classes=[IsOwner])
    def backup(self, request):
        """Returns the database file for backup."""
        import os
        from django.conf import settings
        from django.http import FileResponse
        
        db_path = settings.DATABASES['default']['NAME']
        if os.path.exists(db_path):
            return FileResponse(open(db_path, 'rb'), as_attachment=True, filename='fataka_backup.sqlite3')
        return Response({'error': 'Database file not found'}, status=status.HTTP_404_NOT_FOUND)

    @action(detail=False, methods=['POST'], permission_classes=[IsOwner])
    def restore(self, request):
        """Restores the database from a provided sqlite3 file."""
        password = request.data.get('password')
        if not password or not request.user.check_password(password):
            return Response({'error': 'Invalid password'}, status=status.HTTP_403_FORBIDDEN)

        backup_file = request.FILES.get('backup_file')
        if not backup_file:
            return Response({'error': 'No backup file provided'}, status=status.HTTP_400_BAD_REQUEST)

        import os
        from django.conf import settings
        
        db_path = settings.DATABASES['default']['NAME']
        
        # Save the uploaded file to replace current DB
        try:
            with open(db_path, 'wb+') as destination:
                for chunk in backup_file.chunks():
                    destination.write(chunk)
            return Response({'message': 'Database restored successfully. Please restart the application if needed.'})
        except Exception as e:
            return Response({'error': f'Failed to restore database: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['POST'], permission_classes=[IsOwner])
    def reset_data(self, request):
        """Deletes all business data but keeps settings and staff."""
        password = request.data.get('password')
        if not password or not request.user.check_password(password):
            return Response({'error': 'Invalid password'}, status=status.HTTP_403_FORBIDDEN)

        from billing.models import Invoice, InvoiceItem, Payment
        from products.models import Product, Category
        from customers.models import Customer, CustomerLedger
        
        try:
            # Delete in order to satisfy foreign keys if CASCADE not used everywhere
            Payment.objects.all().delete()
            InvoiceItem.objects.all().delete()
            Invoice.objects.all().delete()
            Product.objects.all().delete()
            Category.objects.all().delete()
            CustomerLedger.objects.all().delete()
            Customer.objects.all().delete()
            
            return Response({'message': 'All business data has been reset successfully.'})
        except Exception as e:
            return Response({'error': f'Failed to reset data: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class DashboardPinViewSet(viewsets.GenericViewSet):
    """
    Manages the global dashboard PIN for the application.
    
    Endpoints:
        GET  /status/       — Check if a PIN is set (any authenticated user)
        POST /set_pin/      — Set or update the PIN (OWNER only)
        POST /verify/       — Verify PIN and get a temporary access token
        POST /revoke/       — Revoke the current dashboard access token
        POST /remove_pin/   — Remove PIN protection entirely (OWNER only)
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

    @action(detail=False, methods=['POST'], permission_classes=[IsOwner])
    def set_pin(self, request):
        """Set or update the dashboard PIN. OWNER only."""
        serializer = DashboardPinSetSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        settings_obj = CompanySettings.get_settings()
        settings_obj.set_pin(serializer.validated_data['pin'])

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

    @action(detail=False, methods=['POST'], permission_classes=[IsOwner])
    def remove_pin(self, request):
        """Remove the dashboard PIN entirely. OWNER only."""
        settings_obj = CompanySettings.get_settings()
        settings_obj.remove_pin()

        # Also revoke all active tokens since PIN is removed
        DashboardAccessToken.objects.filter(is_active=True).update(is_active=False)

        return Response({
            'message': 'Dashboard PIN has been removed. Dashboard is now accessible without a PIN.',
            'has_pin': False,
        })
