from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from accounts.models import User
from predictions.engine import engine_a, engine_b, engine_d, get_confidence_badge
import json

def get_user(request):
    key = request.headers.get('X-API-Key') or request.GET.get('api_key')
    if not key: return None, JsonResponse({'error':'API key required'},status=401)
    try:
        user = User.objects.get(api_key=key)
    except User.DoesNotExist:
        return None, JsonResponse({'error':'Invalid API key'},status=401)
    if not user.is_subscription_active:
        return None, JsonResponse({'error':'Subscription expired'},status=403)
    return user, None

def docs(request):
    return JsonResponse({
        'name': 'MatchOracle API v1',
        'version': '2.0.0',
        'auth': 'X-API-Key header required',
        'plans': 'Basic=10/day, Pro=20/day',
        'endpoints': {
            'POST /api/v1/predict/match/': 'Engine A — match prediction with World Cup features',
            'POST /api/v1/predict/player/': 'Engine B — player rating',
            'POST /api/v1/predict/simulate/': 'Engine D — Monte Carlo simulation',
            'POST /api/v1/predict/smart-ai/': 'Engine NL — Smart AI with internet connectivity',
            'GET  /api/v1/forecasts/': 'Published weekly forecasts',
            'GET  /api/v1/me/': 'Account info',
        },
        'world_cup_fields': {
            'home.tactical_style': 'high_press|counter_attack|possession|defensive_block|wing_play|long_ball|balanced',
            'match_context.match_type': 'league|friendly|qualifier|group|knockout|semifinal|final|worldcup',
            'home.tournament_experience': '0-10 scale',
            'home.knockout_mentality': '0-10 scale',
        },
    })

@csrf_exempt
def predict_match(request):
    """
    POST /api/v1/predict/match/
    Engine A — match prediction with full World Cup / tactical features.

    Supports:
      home.tactical_style, away.tactical_style
      match_context.match_type (league/friendly/qualifier/group/knockout/semifinal/final/worldcup)
      home.tournament_experience (0-10), home.knockout_mentality (0-10)
      home.coach_years, home.xi_consistency, home.key_partnerships
    """
    user, err = get_user(request)
    if err: return err
    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    from predictions.models import Prediction
    result = engine_a(data)
    home_team = data.get('home', {}).get('name', '')
    away_team = data.get('away', {}).get('name', '')
    Prediction.objects.create(
        user=user, engine='A', input_data=data, output_data=result,
        confidence=result.get('confidence', 0),
        home_team=home_team, away_team=away_team,
        predicted_result=result.get('verdict', ''),
    )
    return JsonResponse({'success': True, 'result': result})

@csrf_exempt
def rate_player(request):
    """POST /api/v1/predict/player/ — Engine B player rating."""
    user, err = get_user(request)
    if err: return err
    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    from predictions.models import Prediction
    result = engine_b(data)
    Prediction.objects.create(user=user, engine='B', input_data=data, output_data=result)
    return JsonResponse({'success': True, 'result': result})

@csrf_exempt
def simulate(request):
    """POST /api/v1/predict/simulate/ — Engine D Monte Carlo simulation."""
    user, err = get_user(request)
    if err: return err
    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    from predictions.models import Prediction
    result = engine_d(data)
    home_team = data.get('home', {}).get('name', '')
    away_team = data.get('away', {}).get('name', '')
    Prediction.objects.create(
        user=user, engine='D', input_data=data, output_data=result,
        home_team=home_team, away_team=away_team,
        predicted_result=result.get('likely_score', ''),
    )
    return JsonResponse({'success': True, 'result': result})

@csrf_exempt
def smart_ai(request):
    """
    POST /api/v1/predict/smart-ai/
    Engine NL — Smart AI with Anthropic Claude + internet connectivity.
    Accepts: {"question": "Who will win Brazil vs Argentina in the World Cup final?"}
    Returns: answer, prediction, confidence, confidence_badge, consensus, key_factors,
             home_team, away_team, home_win, draw, away_win, betting_insight, is_today.
    """
    user, err = get_user(request)
    if err: return err
    try:
        body = json.loads(request.body)
    except Exception:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    question = body.get('question', '').strip()
    if not question:
        return JsonResponse({'error': 'question is required'}, status=400)

    try:
        from predictions.smart_ai import smart_predict
        result = smart_predict(question)
    except Exception as e:
        from predictions.engine import natural_language
        result = natural_language(question)

    # Normalise keys
    if 'verdict' in result and 'prediction' not in result:
        result['prediction'] = result['verdict']
    if 'confidence_badge' not in result:
        result['confidence_badge'] = get_confidence_badge(result.get('confidence', 0))

    # Build consensus
    mp = result.get('match_prediction') or {}
    sim = result.get('simulation') or {}
    verdict = result.get('prediction') or result.get('verdict', '')
    engines_agree = []
    if mp.get('verdict') == verdict:
        engines_agree.append('Engine A')
    if sim and verdict and verdict != 'Draw':
        if verdict == result.get('home_team') and sim.get('home_win', 0) > 50:
            engines_agree.append('Engine D')
        elif verdict == result.get('away_team') and sim.get('away_win', 0) > 50:
            engines_agree.append('Engine D')
    result['consensus'] = {
        'prediction': verdict,
        'engines_agree': engines_agree,
        'agreement_count': len(engines_agree),
    }

    from predictions.models import Prediction
    Prediction.objects.create(
        user=user, engine='NL',
        input_data={'question': question},
        output_data=result,
        confidence=result.get('confidence', 0),
        home_team=result.get('home_team') or '',
        away_team=result.get('away_team') or '',
        predicted_result=verdict,
    )
    return JsonResponse({'success': True, 'result': result})

def forecasts(request):
    from core.models import WeeklyForecast
    items = WeeklyForecast.objects.filter(is_published=True)[:10]
    return JsonResponse({'forecasts': [
        {
            'home': f.home_team, 'away': f.away_team,
            'home_win': f.home_win_pct, 'draw': f.draw_pct, 'away_win': f.away_win_pct,
            'score': f.predicted_score,
            'confidence_badge': get_confidence_badge(f.confidence),
        }
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
