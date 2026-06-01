from django.urls import path
from . import views

urlpatterns = [
    # Dashboard
    path('dashboard/',          views.admin_dashboard, name='admin_dashboard'),

    # User management
    path('users/',              views.user_list,        name='admin_users'),
    path('users/<int:user_id>/', views.user_detail,     name='admin_user_detail'),

    # Weekly tips
    path('tips/',               views.tips_list,        name='admin_tips'),
    path('tips/create/',        views.tip_create,       name='admin_tip_create'),
    path('tips/<int:tip_id>/edit/',   views.tip_edit,   name='admin_tip_edit'),
    path('tips/<int:tip_id>/delete/', views.tip_delete, name='admin_tip_delete'),

    # Revenue
    path('revenue/',            views.revenue_view,     name='admin_revenue'),

    # Logs
    path('logs/',               views.logs_view,        name='admin_logs'),
]
