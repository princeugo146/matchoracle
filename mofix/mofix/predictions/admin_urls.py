"""
URL routing for the MatchOracle custom admin dashboards.
Mount this under a staff-only prefix in matchoracle/urls.py, e.g.:
    path('admin/matchoracle/', include('predictions.admin_urls')),
"""
from django.urls import path
from . import admin_views

app_name = 'matchoracle_admin'

urlpatterns = [
    path('',                  admin_views.admin_dashboard,  name='dashboard'),
    path('engine-performance/', admin_views.engine_performance, name='engine_performance'),
    path('user-analytics/',   admin_views.user_analytics,   name='user_analytics'),
    path('team-profiles/',    admin_views.team_profiles,    name='team_profiles'),
    path('patterns/',         admin_views.patterns,         name='patterns'),
    path('payments/',         admin_views.payments,         name='payments'),
    path('api-usage/',        admin_views.api_usage,        name='api_usage'),
    path('health/',           admin_views.system_health,    name='health'),
]
