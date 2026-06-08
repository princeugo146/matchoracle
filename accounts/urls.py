from django.urls import path
from . import views

urlpatterns = [
    path('register/', views.register, name='register'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('profile/', views.profile, name='profile'),
    path('subscribe/<str:plan>/', views.subscribe, name='subscribe'),
    path('verify-payment/', views.verify_payment, name='verify_payment'),

    # Security question-based password reset
    path('password-reset/', views.password_reset_request, name='password_reset'),
    path('password-reset/question/', views.security_question, name='security_question'),
    path('password-reset/confirm/', views.password_reset_confirm, name='password_reset_confirm'),
]
