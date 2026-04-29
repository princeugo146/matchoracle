from django.urls import path
from . import views

urlpatterns = [
    path('docs/', views.api_docs, name='api_docs'),
    path('predict/match/', views.predict_match, name='api_predict_match'),
    path('predict/player/', views.rate_player, name='api_rate_player'),
    path('predict/simulate/', views.simulate_match, name='api_simulate'),
    path('forecasts/', views.forecasts, name='api_forecasts'),
    path('me/', views.me, name='api_me'),
]
