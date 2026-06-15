from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import CompanySettingsViewSet, DashboardPinViewSet

router = DefaultRouter()
router.register(r'settings', CompanySettingsViewSet, basename='company-settings')
router.register(r'dashboard-pin', DashboardPinViewSet, basename='dashboard-pin')

urlpatterns = [
    path('', include(router.urls)),
]
