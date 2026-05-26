from django.urls import path
from . import views
urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('engine/<str:engine>/', views.run_engine, name='run_engine'),
    path('smart-ai/', views.smart_ai, name='smart_ai'),
    path('ranking/add/', views.add_ranking, name='add_ranking'),
    path('history/', views.history, name='prediction_history'),
    path('tips/', views.tips, name='weekly_tips'),
    # Self-learning endpoints
    path('team-profile/<str:team_name>/', views.team_profile, name='team_profile'),
    path('engine-accuracy/<str:engine>/', views.engine_accuracy, name='engine_accuracy'),
    path('<int:prediction_id>/result/', views.prediction_result, name='prediction_result'),
]
