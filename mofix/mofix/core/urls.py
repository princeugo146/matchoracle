from django.urls import path
from . import views
urlpatterns = [
    path('', views.home, name='home'),
    path('pricing/', views.pricing, name='pricing'),
    path('scores/', views.scores, name='scores'),
    path('leaderboard/', views.leaderboard, name='leaderboard'),
    path('api-docs/', views.api_docs, name='api_docs_page'),
    path('health/', views.health_check, name='health'),
    path('legal/privacy/', views.privacy_policy, name='privacy_policy'),
    path('legal/terms/', views.terms_of_service, name='terms_of_service'),
    path('about/', views.about_us, name='about_us'),
]
