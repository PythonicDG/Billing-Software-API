from django.urls import path
from .views import DashboardSummaryView, CustomerInsightsView, SalesAnalyticsView, OperationsFinanceView

urlpatterns = [
    path('summary/', DashboardSummaryView.as_view(), name='dashboard-summary'),
    path('customers/', CustomerInsightsView.as_view(), name='report-customers'),
    path('analytics/', SalesAnalyticsView.as_view(), name='report-analytics'),
    path('operations/', OperationsFinanceView.as_view(), name='report-operations'),
]
