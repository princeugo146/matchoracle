from django.contrib import admin
from django.urls import path, include
from django.http import JsonResponse, FileResponse
from django.conf import settings
import os

def health(request):
    return JsonResponse({'status': 'ok', 'version': '2.0.0'})

def serve_sw(request):
    """Serve service worker from root scope"""
    sw_path = os.path.join(settings.BASE_DIR, 'static', 'sw.js')
    return FileResponse(open(sw_path, 'rb'), content_type='application/javascript')

urlpatterns = [
    path('admin/', admin.site.urls),
    path('health/', health),
    path('sw.js', serve_sw),  # Service worker at root
    path('', include('core.urls')),
    path('accounts/', include('accounts.urls')),
    path('dashboard/', include('predictions.urls')),
    path('api/v1/', include('api.urls')),
    path('admin-dashboard/', include('predictions.admin_urls')),
]
