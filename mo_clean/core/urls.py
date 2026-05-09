from django.urls import path
from . import views
urlpatterns = [
    path('', views.home, name='home'),
    path('pricing/', views.pricing, name='pricing'),
    path('scores/', views.scores, name='scores'),
    path('leaderboard/', views.leaderboard, name='leaderboard'),
    path('api-docs/', views.api_docs, name='api_docs_page'),
    path('api/scores/', views.scores_api, name='scores_api'),
    path('health/', views.health, name='health'),
]
