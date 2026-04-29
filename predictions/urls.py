from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('engine/<str:engine>/', views.run_engine, name='run_engine'),
    path('ranking/add/', views.add_ranking, name='add_ranking'),
]
