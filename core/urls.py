from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('pricing/', views.pricing, name='pricing'),
    path('scores/', views.live_scores_page, name='scores'),
    path('leaderboard/', views.leaderboard, name='leaderboard'),
    path('api-docs/', views.api_docs_page, name='api_docs_page'),
    path('api/scores/', views.live_scores_api, name='live_scores_api'),
    path('health/', views.health, name='health'),
]
