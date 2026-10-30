from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import CompanySettingsViewSet, DashboardPinViewSet, AppUpdateViewSet, AuditLogViewSet

router = DefaultRouter()
router.register(r'settings', CompanySettingsViewSet, basename='company-settings')
router.register(r'dashboard-pin', DashboardPinViewSet, basename='dashboard-pin')
router.register(r'app-update', AppUpdateViewSet, basename='app-update')
router.register(r'audit-logs', AuditLogViewSet, basename='audit-logs')

urlpatterns = [
    path('', include(router.urls)),
]
