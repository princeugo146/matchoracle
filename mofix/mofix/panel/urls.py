from django.urls import path
from . import views

urlpatterns = [
    path('dashboard/', views.dashboard, name='admin_dashboard'),
    path('users/', views.user_list, name='admin_users'),
    path('users/<int:user_id>/', views.user_detail, name='admin_user_detail'),
    path('users/<int:user_id>/toggle/', views.toggle_user_status, name='admin_toggle_user'),
    path('users/<int:user_id>/plan/', views.change_user_plan, name='admin_change_plan'),
    path('tips/', views.tips_list, name='admin_tips'),
    path('tips/create/', views.tip_create, name='admin_tip_create'),
    path('tips/<int:tip_id>/edit/', views.tip_edit, name='admin_tip_edit'),
    path('tips/<int:tip_id>/delete/', views.tip_delete, name='admin_tip_delete'),
    path('revenue/', views.revenue_dashboard, name='admin_revenue'),
    path('logs/', views.admin_logs, name='admin_logs'),
]
