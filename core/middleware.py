from django.core.cache import cache
from django.http import JsonResponse
import time

class RateLimitMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith('/api/'):
            ip = self.get_client_ip(request)
            key = f'ratelimit_{ip}'
            requests = cache.get(key, 0)
            if requests >= 100:
                return JsonResponse({'error': 'Rate limit exceeded. Please slow down.'}, status=429)
            cache.set(key, requests + 1, 3600)
        return self.get_response(request)

    def get_client_ip(self, request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        return x_forwarded_for.split(',')[0] if x_forwarded_for else request.META.get('REMOTE_ADDR')
