from django.urls import path
from . import views
from . import views_analytics

urlpatterns = [
    # ── Core prediction views ─────────────────────────────────────────────────
    path('', views.dashboard, name='dashboard'),
    path('engine/<str:engine>/', views.run_engine, name='run_engine'),
    path('ranking/add/', views.add_ranking, name='add_ranking'),
    path('history/', views.history, name='prediction_history'),
    path('tips/', views.tips, name='weekly_tips'),

    # ── Phase 4: Analytics (staff only) ──────────────────────────────────────
    path('analytics/', views_analytics.analytics_dashboard, name='analytics_dashboard'),
    path('analytics/engines/', views_analytics.engine_comparison, name='engine_comparison'),
    path('analytics/users/', views_analytics.user_analytics, name='user_analytics'),
    path('analytics/teams/', views_analytics.team_analytics, name='team_analytics'),
    path('analytics/revenue/', views_analytics.revenue_analytics, name='revenue_analytics'),
    path('analytics/export/', views_analytics.export_analytics, name='export_analytics'),

    # ── JSON API endpoints (Chart.js AJAX) ───────────────────────────────────
    path('analytics/api/trend/', views_analytics.api_accuracy_trend, name='api_accuracy_trend'),
    path('analytics/api/engines/', views_analytics.api_engine_stats, name='api_engine_stats'),
    path('analytics/api/revenue/', views_analytics.api_revenue_trend, name='api_revenue_trend'),
]

