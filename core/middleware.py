import time
from django.core.cache import cache
from django.http import JsonResponse
from django.conf import settings


class PerformanceMiddleware:
    """Optimizes response time and handles rate limiting."""
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Add keep-alive header
        response = self.get_response(request)
        response['X-Powered-By'] = 'MatchOracle v2'
        response['Cache-Control'] = 'no-store' if request.user.is_authenticated else 'public, max-age=60'

        # Rate limiting for API
        if request.path.startswith('/api/'):
            ip = self._get_ip(request)
            key = f'rate_{ip}'
            count = cache.get(key, 0)
            if count >= 200:
                return JsonResponse({'error': 'Rate limit exceeded'}, status=429)
            cache.set(key, count + 1, 3600)

        return response

    def _get_ip(self, request):
        xff = request.META.get('HTTP_X_FORWARDED_FOR')
        return xff.split(',')[0] if xff else request.META.get('REMOTE_ADDR', '')
