from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from accounts.models import User
from predictions.engine import engine_a, engine_b, engine_d
import json
import logging

logger = logging.getLogger(__name__)


def get_user(request):
    key = request.headers.get('X-API-Key') or request.GET.get('api_key')
    if not key: return None, JsonResponse({'error': 'API key required'}, status=401)
    try:
        user = User.objects.get(api_key=key)
    except User.DoesNotExist:
        return None, JsonResponse({'error': 'Invalid API key'}, status=401)
    if not user.is_subscription_active:
        return None, JsonResponse({'error': 'Subscription expired'}, status=403)
    return user, None


def _queue_learning(prediction_id, home_team='', away_team=''):
    """
    Fire-and-forget: queue a deferred result check for a new prediction.
    Wraps the learning task import so any failure is fully isolated from
    the API response — learning is additive, never a hard dependency.
    """
    if not home_team or not away_team:
        return
    try:
        from predictions.learning_tasks import queue_result_check
        queue_result_check(prediction_id)
    except Exception as exc:
        logger.debug(f"_queue_learning: skipped for prediction {prediction_id}: {exc}")


def docs(request):
    return JsonResponse({'name': 'MatchOracle API v1', 'version': '2.0.0',
        'auth': 'X-API-Key header required', 'plans': 'Basic=10/day, Pro=20/day'})


@csrf_exempt
def predict_match(request):
    user, err = get_user(request)
    if err: return err
    data = json.loads(request.body)
    from predictions.models import Prediction
    result = engine_a(data)
    home_team = data.get('home', {}).get('name', '')
    away_team = data.get('away', {}).get('name', '')
    pred = Prediction.objects.create(
        user=user, engine='A', input_data=data, output_data=result,
        confidence=result.get('confidence', 0),
        home_team=home_team, away_team=away_team,
        predicted_result=result.get('verdict', ''),
    )
    # Queue deferred result check (~2 days later via Celery)
    _queue_learning(pred.id, home_team, away_team)
    return JsonResponse({'success': True, 'result': result})


@csrf_exempt
def rate_player(request):
    user, err = get_user(request)
    if err: return err
    data = json.loads(request.body)
    from predictions.models import Prediction
    result = engine_b(data)
    Prediction.objects.create(user=user, engine='B', input_data=data, output_data=result)
    return JsonResponse({'success': True, 'result': result})


@csrf_exempt
def simulate(request):
    user, err = get_user(request)
    if err: return err
    data = json.loads(request.body)
    from predictions.models import Prediction
    result = engine_d(data)
    home_team = data.get('home', {}).get('name', '')
    away_team = data.get('away', {}).get('name', '')
    pred = Prediction.objects.create(
        user=user, engine='D', input_data=data, output_data=result,
        home_team=home_team, away_team=away_team,
    )
    # Engine D (simulation) results are also worth tracking
    _queue_learning(pred.id, home_team, away_team)
    return JsonResponse({'success': True, 'result': result})


def forecasts(request):
    from core.models import WeeklyForecast
    items = WeeklyForecast.objects.filter(is_published=True)[:10]
    return JsonResponse({'forecasts': [
        {'home': f.home_team, 'away': f.away_team, 'home_win': f.home_win_pct,
         'draw': f.draw_pct, 'away_win': f.away_win_pct, 'score': f.predicted_score}
        for f in items
    ]})


def me(request):
    user, err = get_user(request)
    if err: return err
    from django.conf import settings
    plan = settings.MATCHORACLE['PLANS'].get(user.plan, {})
    return JsonResponse({
        'email': user.email, 'plan': user.plan,
        'active': user.is_subscription_active,
        'days_remaining': user.days_remaining,
        'predictions_left_today': user.predictions_left_today,
        'limit': plan.get('predictions_per_day', 3),
    })
