from django.urls import path
from . import views

urlpatterns = [
    path('',                          views.dashboard,          name='admin_dashboard'),
    path('users/',                    views.users_list,         name='admin_users_list'),
    path('users/<int:user_id>/edit/', views.user_edit,          name='admin_user_edit'),
    path('users/<int:user_id>/toggle-active/', views.user_toggle_active, name='admin_user_toggle'),
    path('users/<int:user_id>/delete/', views.user_delete,      name='admin_user_delete'),
    path('tips/',                     views.tips_list,          name='admin_tips_list'),
    path('tips/create/',              views.tip_create,         name='admin_tip_create'),
    path('tips/<int:tip_id>/edit/',   views.tip_edit,           name='admin_tip_edit'),
    path('tips/<int:tip_id>/delete/', views.tip_delete,         name='admin_tip_delete'),
    path('revenue/',                  views.revenue_dashboard,  name='admin_revenue'),
    path('audit-log/',                views.audit_log,          name='admin_audit_log'),
]
