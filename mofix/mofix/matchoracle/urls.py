from django.contrib import admin
from django.urls import path, include
from django.http import JsonResponse, HttpResponse
from django.conf import settings
import os

def health(request):
    return JsonResponse({'status': 'ok', 'version': '2.0.0'})

def serve_sw(request):
    """Serve service worker from root scope - required for PWA"""
    # Try multiple paths
    paths_to_try = [
        os.path.join(settings.BASE_DIR, 'static', 'sw.js'),
        os.path.join(settings.BASE_DIR, 'staticfiles', 'sw.js'),
    ]
    for sw_path in paths_to_try:
        if os.path.exists(sw_path):
            with open(sw_path, 'r') as f:
                content = f.read()
            return HttpResponse(
                content,
                content_type='application/javascript; charset=utf-8',
                headers={
                    'Service-Worker-Allowed': '/',
                    'Cache-Control': 'no-cache',
                }
            )
    return HttpResponse('// Service worker not found', content_type='application/javascript')

def serve_manifest(request):
    """Serve manifest.json"""
    paths_to_try = [
        os.path.join(settings.BASE_DIR, 'static', 'manifest.json'),
        os.path.join(settings.BASE_DIR, 'staticfiles', 'manifest.json'),
    ]
    for path in paths_to_try:
        if os.path.exists(path):
            with open(path, 'r') as f:
                content = f.read()
            return HttpResponse(content, content_type='application/manifest+json')
    return HttpResponse('{}', content_type='application/manifest+json')

urlpatterns = [
    path('admin/', admin.site.urls),
    path('health/', health),
    path('sw.js', serve_sw),
    path('manifest.json', serve_manifest),
    path('', include('core.urls')),
    path('accounts/', include('accounts.urls')),
    path('dashboard/', include('predictions.urls')),
    path('api/v1/', include('api.urls')),
    path('panel/', include('admin_panel.urls')),
]
