from django.urls import path
from . import views
urlpatterns = [
    path('docs/', views.docs),
    path('predict/match/', views.predict_match),
    path('predict/player/', views.rate_player),
    path('predict/simulate/', views.simulate),
    path('predict/smart-ai/', views.smart_ai),
    path('forecasts/', views.forecasts),
    path('me/', views.me),
]
