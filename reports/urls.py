from django.urls import path, re_path
from .views import DashboardSummaryView, CustomerInsightsView, SalesAnalyticsView, OperationsFinanceView

urlpatterns = [
    re_path(r'^summary/?$', DashboardSummaryView.as_view(), name='dashboard-summary'),
    re_path(r'^customers/?$', CustomerInsightsView.as_view(), name='report-customers'),
    re_path(r'^analytics/?$', SalesAnalyticsView.as_view(), name='report-analytics'),
    re_path(r'^operations/?$', OperationsFinanceView.as_view(), name='report-operations'),
]
