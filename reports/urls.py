from django.urls import path
from .views import (
    DailySalesView,
    OutstandingCustomersView,
    StockSummaryView,
    CustomerSalesView,
)

urlpatterns = [
    path('daily-sales/', DailySalesView.as_view(), name='daily-sales'),
    path('outstanding/', OutstandingCustomersView.as_view(), name='outstanding'),
    path('stock-summary/', StockSummaryView.as_view(), name='stock-summary'),
    path('customer-sales/', CustomerSalesView.as_view(), name='customer-sales'),
]
