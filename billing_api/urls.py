from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),

    # App URLs
    path('api/', include('accounts.urls')),
    path('api/products/', include('products.urls')),
    path('api/billing/', include('billing.urls')),
    path('api/customers/', include('customers.urls')),
    path('api/dashboard/', include('reports.dashboard_urls')),
    path('api/core/', include('core.urls')),
]

# Static and Media files for all environments
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
