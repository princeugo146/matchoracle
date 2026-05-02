from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from django.conf import settings
from accounts.models import User
from predictions.models import Prediction
from predictions.engine import engine_a, engine_b, engine_d

def get_api_user(request):
    key = request.headers.get('X-API-Key') or request.GET.get('api_key')
    if not key:
        return None, Response({'error': 'API key required. Include X-API-Key header.'}, status=401)
    try:
        user = User.objects.get(api_key=key)
    except User.DoesNotExist:
        return None, Response({'error': 'Invalid API key.'}, status=401)
    if not user.is_subscription_active:
        return None, Response({'error': 'Subscription expired.'}, status=403)
    if not settings.MATCHORACLE['PLANS'][user.plan]['api_access']:
        return None, Response({'error': 'API access requires Basic or Pro plan.'}, status=403)
    return user, None

@api_view(['GET'])
@permission_classes([AllowAny])
def api_docs(request):
    return Response({
        'name': 'MatchOracle API v1',
        'version': settings.MATCHORACLE['VERSION'],
        'authentication': 'Include X-API-Key header',
        'endpoints': {
            'POST /api/v1/predict/match/': 'Engine A — Match prediction',
            'POST /api/v1/predict/player/': 'Engine B — Player rating',
            'POST /api/v1/predict/simulate/': 'Engine D — Match simulation',
            'GET  /api/v1/forecasts/': 'Weekly forecasts (free)',
            'GET  /api/v1/me/': 'Account info',
        },
        'plans': {
            'basic': '₦2,000/month — 100 predictions/day',
            'pro': '₦15,000/year — 500 predictions/day',
        }
    })

@api_view(['POST'])
@permission_classes([AllowAny])
def predict_match(request):
    user, err = get_api_user(request)
    if err: return err
    result = engine_a(request.data)
    Prediction.objects.create(user=user, engine='A', input_data=dict(request.data), output_data=result, confidence=result.get('confidence', 0))
    return Response({'success': True, 'result': result})

@api_view(['POST'])
@permission_classes([AllowAny])
def rate_player(request):
    user, err = get_api_user(request)
    if err: return err
    result = engine_b(request.data)
    Prediction.objects.create(user=user, engine='B', input_data=dict(request.data), output_data=result)
    return Response({'success': True, 'result': result})

@api_view(['POST'])
@permission_classes([AllowAny])
def simulate_match(request):
    user, err = get_api_user(request)
    if err: return err
    result = engine_d(request.data)
    Prediction.objects.create(user=user, engine='D', input_data=dict(request.data), output_data=result)
    return Response({'success': True, 'result': result})

@api_view(['GET'])
@permission_classes([AllowAny])
def forecasts(request):
    from core.models import WeeklyForecast
    items = WeeklyForecast.objects.filter(is_published=True)[:10]
    return Response({'forecasts': [{'home': f.home_team, 'away': f.away_team, 'date': f.match_date, 'home_win': f.home_win_pct, 'draw': f.draw_pct, 'away_win': f.away_win_pct, 'predicted_score': f.predicted_score, 'confidence': f.confidence} for f in items]})

@api_view(['GET'])
@permission_classes([AllowAny])
def me(request):
    user, err = get_api_user(request)
    if err: return err
    cfg = settings.MATCHORACLE
    return Response({'email': user.email, 'plan': user.plan, 'subscription_active': user.is_subscription_active, 'days_remaining': user.days_remaining, 'predictions_today': user.predictions_today, 'daily_limit': cfg['PLANS'][user.plan]['predictions_per_day'], 'api_access': cfg['PLANS'][user.plan]['api_access'], 'accuracy_rate': user.accuracy_rate})
