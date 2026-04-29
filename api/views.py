from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status
from django.conf import settings
from accounts.models import User
from predictions.models import Prediction
from predictions.engine import engine_a_predict, engine_b_rate, engine_d_simulate
from functools import wraps

def require_api_key(f):
    @wraps(f)
    def wrapper(request, *args, **kwargs):
        key = request.headers.get('X-API-Key') or request.GET.get('api_key')
        if not key:
            return Response({'error': 'API key required. Include X-API-Key header.'}, status=401)
        try:
            user = User.objects.get(api_key=key)
        except User.DoesNotExist:
            return Response({'error': 'Invalid API key.'}, status=401)
        if not user.is_subscription_active:
            return Response({'error': 'Subscription expired. Visit matchoracle.com to renew.'}, status=403)
        if not settings.MATCHORACLE['PLANS'][user.plan]['api_access']:
            return Response({'error': 'API access requires Basic or Pro plan.'}, status=403)
        request.api_user = user
        return f(request, *args, **kwargs)
    return wrapper

@api_view(['GET'])
@permission_classes([AllowAny])
def api_docs(request):
    return Response({
        'name': 'MatchOracle API',
        'version': 'v1',
        'description': 'Football Intelligence Engine API',
        'authentication': 'Include X-API-Key header with your API key',
        'endpoints': {
            'POST /api/v1/predict/match/': 'Engine A — Match prediction',
            'POST /api/v1/predict/player/': 'Engine B — Player rating',
            'POST /api/v1/predict/simulate/': 'Engine D — Match simulation',
            'GET  /api/v1/forecasts/': 'Weekly match forecasts (free)',
            'GET  /api/v1/me/': 'Your account info',
        },
        'plans': {
            'free': '6 trial predictions — no API access',
            'basic': '₦2,000/month — 100 predictions/day — API access',
            'pro': '₦15,000/year — 500 predictions/day — API access',
        }
    })

@api_view(['POST'])
@permission_classes([AllowAny])
def predict_match(request):
    key = request.headers.get('X-API-Key') or request.GET.get('api_key')
    if not key:
        return Response({'error': 'API key required'}, status=401)
    try:
        user = User.objects.get(api_key=key)
    except User.DoesNotExist:
        return Response({'error': 'Invalid API key'}, status=401)
    if not user.is_subscription_active:
        return Response({'error': 'Subscription expired'}, status=403)

    result = engine_a_predict(request.data)
    Prediction.objects.create(user=user, engine='A', input_data=request.data,
                              output_data=result, confidence=result.get('confidence',0))
    return Response({'success': True, 'engine': 'A', 'result': result})

@api_view(['POST'])
@permission_classes([AllowAny])
def rate_player(request):
    key = request.headers.get('X-API-Key') or request.GET.get('api_key')
    if not key:
        return Response({'error': 'API key required'}, status=401)
    try:
        user = User.objects.get(api_key=key)
    except User.DoesNotExist:
        return Response({'error': 'Invalid API key'}, status=401)

    result = engine_b_rate(request.data)
    Prediction.objects.create(user=user, engine='B', input_data=request.data, output_data=result)
    return Response({'success': True, 'engine': 'B', 'result': result})

@api_view(['POST'])
@permission_classes([AllowAny])
def simulate_match(request):
    key = request.headers.get('X-API-Key') or request.GET.get('api_key')
    if not key:
        return Response({'error': 'API key required'}, status=401)
    try:
        user = User.objects.get(api_key=key)
    except User.DoesNotExist:
        return Response({'error': 'Invalid API key'}, status=401)

    result = engine_d_simulate(request.data)
    Prediction.objects.create(user=user, engine='D', input_data=request.data, output_data=result)
    return Response({'success': True, 'engine': 'D', 'result': result})

@api_view(['GET'])
@permission_classes([AllowAny])
def forecasts(request):
    from core.models import WeeklyForecast
    items = WeeklyForecast.objects.filter(is_published=True)[:10]
    data = [{'home': f.home_team, 'away': f.away_team, 'date': f.match_date,
              'home_win': f.home_win_pct, 'draw': f.draw_pct, 'away_win': f.away_win_pct,
              'predicted_score': f.predicted_score, 'confidence': f.confidence} for f in items]
    return Response({'forecasts': data})

@api_view(['GET'])
@permission_classes([AllowAny])
def me(request):
    key = request.headers.get('X-API-Key') or request.GET.get('api_key')
    if not key:
        return Response({'error': 'API key required'}, status=401)
    try:
        user = User.objects.get(api_key=key)
    except User.DoesNotExist:
        return Response({'error': 'Invalid API key'}, status=401)
    cfg = settings.MATCHORACLE
    return Response({
        'email': user.email, 'plan': user.plan,
        'subscription_active': user.is_subscription_active,
        'days_remaining': user.days_remaining,
        'predictions_today': user.predictions_today,
        'daily_limit': cfg['PLANS'][user.plan]['predictions_per_day'],
        'api_access': cfg['PLANS'][user.plan]['api_access'],
    })
