from django.urls import path
from . import views

urlpatterns = [
    path('register/', views.register, name='register'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('profile/', views.profile, name='profile'),
    path('subscribe/<str:plan>/', views.subscribe, name='subscribe'),
    path('verify-payment/', views.verify_payment, name='verify_payment'),
]
