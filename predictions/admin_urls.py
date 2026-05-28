from django.urls import path
from . import admin_views

app_name = 'admin_dashboard'

urlpatterns = [
    path('', admin_views.DashboardView.as_view(), name='dashboard'),
    path('engine/', admin_views.EnginePerformanceView.as_view(), name='engine_performance'),
    path('users/', admin_views.UserAnalyticsView.as_view(), name='user_analytics'),
    path('payments/', admin_views.PaymentTrackingView.as_view(), name='payment_tracking'),
    path('api-usage/', admin_views.APIUsageView.as_view(), name='api_usage'),
    path('health/', admin_views.SystemHealthView.as_view(), name='system_health'),
    # JSON endpoints for live refresh
    path('json/health/', admin_views.health_json, name='health_json'),
    path('json/engine/', admin_views.engine_json, name='engine_json'),
    # CSV exports
    path('export/<str:dataset>/', admin_views.export_csv, name='export_csv'),
]
