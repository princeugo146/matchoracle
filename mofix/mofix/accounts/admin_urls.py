"""
URL patterns for the MatchOracle admin API.

All routes are prefixed with /admin-api/ in the main urls.py.
Every view enforces superuser-only access via the @superuser_required decorator.
"""
from django.urls import path
from . import admin_views

urlpatterns = [
    # ── Overview ──────────────────────────────────────────────────────────────
    path('', admin_views.admin_overview, name='admin_overview'),

    # ── User Management ───────────────────────────────────────────────────────
    path('users/', admin_views.admin_users_list, name='admin_users_list'),
    path('users/<int:user_id>/', admin_views.admin_user_detail, name='admin_user_detail'),
    path('users/<int:user_id>/action/', admin_views.admin_user_action, name='admin_user_action'),

    # ── Revenue Dashboard ─────────────────────────────────────────────────────
    path('revenue/', admin_views.admin_revenue, name='admin_revenue'),

    # ── Weekly Tips ───────────────────────────────────────────────────────────
    path('tips/', admin_views.admin_tips_list, name='admin_tips_list'),
    path('tips/<int:tip_id>/', admin_views.admin_tip_detail, name='admin_tip_detail'),

    # ── Weekly Forecasts ──────────────────────────────────────────────────────
    path('forecasts/', admin_views.admin_forecasts_list, name='admin_forecasts_list'),
    path('forecasts/<int:forecast_id>/', admin_views.admin_forecast_detail, name='admin_forecast_detail'),

    # ── Analytics ─────────────────────────────────────────────────────────────
    path('analytics/', admin_views.admin_analytics, name='admin_analytics'),
    path('predictions/', admin_views.admin_predictions_list, name='admin_predictions_list'),

    # ── Activity Log ──────────────────────────────────────────────────────────
    path('activity/', admin_views.admin_activity_log, name='admin_activity_log'),

    # ── Settings ──────────────────────────────────────────────────────────────
    path('settings/', admin_views.admin_settings, name='admin_settings'),
]
