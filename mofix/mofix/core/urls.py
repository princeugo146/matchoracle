from django.urls import path
from . import views
urlpatterns = [
    path('', views.home, name='home'),
    path('pricing/', views.pricing, name='pricing'),
    path('scores/', views.scores, name='scores'),
    path('leaderboard/', views.leaderboard, name='leaderboard'),
    path('api-docs/', views.api_docs, name='api_docs_page'),
    path('health/', views.health_check, name='health'),
    # Legal pages
    path('privacy/', views.privacy_view, name='privacy'),
    path('terms/', views.terms_view, name='terms'),
    path('about/', views.about_view, name='about'),
]
