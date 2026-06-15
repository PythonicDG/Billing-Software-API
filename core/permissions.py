from rest_framework.permissions import BasePermission
from .models import DashboardAccessToken, CompanySettings


class HasDashboardAccess(BasePermission):
    """
    Permission class that requires a valid dashboard access token.
    
    The token must be passed in the 'X-Dashboard-Token' header.
    If no PIN is set on the company settings, access is granted without a token.
    """
    message = "Dashboard access token is required. Please enter your PIN to access the dashboard."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        # Check if a PIN is even set
        settings_obj = CompanySettings.get_settings()
        if not settings_obj.has_pin:
            # No PIN configured — allow access without token
            return True

        # PIN is set — require a valid dashboard token
        token_str = request.META.get('HTTP_X_DASHBOARD_TOKEN', '')
        if not token_str:
            self.message = "Dashboard access token is missing. Please enter your PIN."
            return False

        is_valid, token_obj = DashboardAccessToken.validate_token(token_str)
        if not is_valid:
            self.message = "Dashboard access token has expired. Please re-enter your PIN."
            return False

        return True
