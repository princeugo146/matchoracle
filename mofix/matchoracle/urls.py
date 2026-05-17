from django.contrib import admin
from django.urls import path, include
from django.http import JsonResponse

def health(request):
    return JsonResponse({'status': 'ok', 'version': '2.0.0'})

urlpatterns = [
    path('admin/', admin.site.urls),
    path('health/', health),
    path('', include('core.urls')),
    path('accounts/', include('accounts.urls')),
    path('dashboard/', include('predictions.urls')),
    path('api/v1/', include('api.urls')),
]
