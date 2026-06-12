from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import CompanySettingsViewSet

router = DefaultRouter()
router.register(r'settings', CompanySettingsViewSet, basename='company-settings')

urlpatterns = [
    path('', include(router.urls)),
]
