import json, logging
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.utils import timezone
from django.http import JsonResponse
from .models import Prediction, TeamRanking, WeeklyTip
from .engine import engine_a, engine_b, compute_elo, engine_d, natural_language, get_confidence_badge

logger = logging.getLogger(__name__)


def _smart_predict_safe(question):
    """
    Route NL questions through smart_ai.smart_predict (Anthropic + web search).
    Falls back to engine.natural_language if smart_ai is unavailable.
    Normalises the response so both code paths return the same keys.
    """
    try:
        from .smart_ai import smart_predict
        result = smart_predict(question)
        # smart_predict uses 'verdict' — alias to 'prediction' for compatibility
        if 'verdict' in result and 'prediction' not in result:
            result['prediction'] = result['verdict']
        # Ensure confidence_badge is always present
        if 'confidence_badge' not in result:
            result['confidence_badge'] = get_confidence_badge(result.get('confidence', 0))
        # Build consensus block from engine agreement
        if 'match_prediction' in result and result['match_prediction']:
            mp = result['match_prediction']
            sim = result.get('simulation') or {}
            engines_agree = []
            verdict = result.get('verdict') or result.get('prediction', '')
            if mp.get('verdict') == verdict:
                engines_agree.append('Engine A')
            if sim.get('likely_score') and verdict and verdict != 'Draw':
                # crude check: sim home_win > 50 means home team likely
                if verdict == result.get('home_team') and sim.get('home_win', 0) > 50:
                    engines_agree.append('Engine D')
                elif verdict == result.get('away_team') and sim.get('away_win', 0) > 50:
                    engines_agree.append('Engine D')
            result['consensus'] = {
                'prediction': verdict,
                'engines_agree': engines_agree,
                'agreement_count': len(engines_agree),
            }
        return result
    except Exception as e:
        logger.warning(f"smart_predict failed, falling back to natural_language: {e}")
        result = natural_language(question)
        if 'confidence_badge' not in result:
            result['confidence_badge'] = get_confidence_badge(result.get('confidence', 0))
        return result

@login_required
def dashboard(request):
    from core.live_scores import get_live_scores
    from core.models import WeeklyForecast
    user = request.user
    recent = Prediction.objects.filter(user=user)[:8]
    rankings = TeamRanking.objects.filter(user=user)[:10]
    tips = WeeklyTip.objects.filter(is_pro_only=False)[:3]
    forecasts = WeeklyForecast.objects.filter(is_published=True)[:4]
    live_scores = get_live_scores()[:4]
    plan_info = settings.MATCHORACLE['PLANS'].get(user.plan, {})
    stats = {
        'total': Prediction.objects.filter(user=user).count(),
        'accuracy': user.accuracy_rate,
        'left_today': user.predictions_left_today,
        'limit': plan_info.get('predictions_per_day', 3),
    }
    return render(request, 'predictions/dashboard.html', {
        'recent': recent, 'rankings': rankings, 'stats': stats,
        'tips': tips, 'forecasts': forecasts, 'live_scores': live_scores,
        'plan_info': plan_info,
    })

@login_required
def run_engine(request, engine):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST only'}, status=405)
    user = request.user

    # Reset counter if new day
    today = timezone.now().date()
    if user.predictions_date != today:
        user.predictions_today = 0
        user.predictions_date = today
        user.save(update_fields=['predictions_today', 'predictions_date'])

    if not user.can_predict:
        plan_info = settings.MATCHORACLE['PLANS'].get(user.plan, {})
        limit = plan_info.get('predictions_per_day', 3)
        return JsonResponse({
            'error': 'daily_limit_reached',
            'message': f'You have used all {limit} predictions for today. Upgrade for more!',
        }, status=429)

    try:
        input_data = json.loads(request.body)
    except Exception:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    try:
        result = None
        home_team = ''; away_team = ''; predicted_result = ''
        if engine == 'A':
            result = engine_a(input_data)
            home_team = input_data.get('home', {}).get('name', '')
            away_team = input_data.get('away', {}).get('name', '')
            predicted_result = result.get('verdict', '')
        elif engine == 'B':
            result = engine_b(input_data)
            predicted_result = f"{result.get('tier','')} ({result.get('rating',0)})"
        elif engine == 'D':
            result = engine_d(input_data)
            home_team = input_data.get('home', {}).get('name', '')
            away_team = input_data.get('away', {}).get('name', '')
            predicted_result = result.get('likely_score', '')
        elif engine == 'NL':
            result = _smart_predict_safe(input_data.get('question', ''))
            predicted_result = result.get('prediction') or result.get('verdict', '')
        else:
            return JsonResponse({'error': 'Invalid engine'}, status=400)

        if result:
            Prediction.objects.create(
                user=user, engine=engine, input_data=input_data,
                output_data=result, confidence=result.get('confidence', 0),
                home_team=home_team, away_team=away_team,
                predicted_result=predicted_result,
            )
            user.predictions_today += 1
            user.total_predictions += 1
            user.save(update_fields=['predictions_today', 'total_predictions'])
            return JsonResponse({
                'success': True,
                'result': result,
                'predictions_left': user.predictions_left_today,
            })
    except Exception as e:
        logger.error(f"Engine {engine} error: {e}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)

@login_required
def add_ranking(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST only'}, status=405)
    try:
        data = json.loads(request.body)
        name = data.get('name', '').strip()
        if not name:
            return JsonResponse({'error': 'Name required'}, status=400)
        wins = int(data.get('wins', 0)); draws = int(data.get('draws', 0))
        losses = int(data.get('losses', 0)); gf = int(data.get('goals_for', 0))
        ga = int(data.get('goals_against', 0)); opp = float(data.get('opp_strength', 5))
        base = int(data.get('base_elo', 1000))
        elo = compute_elo(wins, draws, losses, gf, ga, opp, base)
        TeamRanking.objects.update_or_create(
            user=request.user, name=name,
            defaults={'power_elo': elo, 'wins': wins, 'draws': draws,
                      'losses': losses, 'goals_for': gf, 'goals_against': ga}
        )
        rankings = list(TeamRanking.objects.filter(user=request.user).values(
            'name', 'power_elo', 'wins', 'draws', 'losses', 'goals_for', 'goals_against'
        ))
        return JsonResponse({'success': True, 'rankings': rankings})
    except Exception as e:
        logger.error(f"Ranking error: {e}")
        return JsonResponse({'error': str(e)}, status=500)

@login_required
def history(request):
    predictions = Prediction.objects.filter(user=request.user)[:50]
    return render(request, 'predictions/history.html', {
        'predictions': predictions,
        'stats': {'total': predictions.count(), 'accuracy': request.user.accuracy_rate}
    })

@login_required
def tips(request):
    free_tips = WeeklyTip.objects.filter(is_pro_only=False)[:10]
    pro_tips = WeeklyTip.objects.filter(is_pro_only=True)[:10] if request.user.plan == 'pro' else []
    return render(request, 'predictions/tips.html', {
        'free_tips': free_tips, 'pro_tips': pro_tips,
        'is_pro': request.user.plan == 'pro',
    })


@login_required
def smart_ai_view(request):
    """
    POST /dashboard/smart-ai/
    Dedicated Smart AI endpoint (Engine NL) with full Anthropic + web search.
    Returns structured JSON with confidence badge, consensus, and key factors.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST only'}, status=405)

    user = request.user

    # Daily limit check
    today = timezone.now().date()
    if user.predictions_date != today:
        user.predictions_today = 0
        user.predictions_date = today
        user.save(update_fields=['predictions_today', 'predictions_date'])

    if not user.can_predict:
        plan_info = settings.MATCHORACLE['PLANS'].get(user.plan, {})
        limit = plan_info.get('predictions_per_day', 3)
        return JsonResponse({
            'error': 'daily_limit_reached',
            'message': f'You have used all {limit} predictions for today. Upgrade for more!',
        }, status=429)

    try:
        body = json.loads(request.body)
    except Exception:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    question = body.get('question', '').strip()
    if not question:
        return JsonResponse({'error': 'question is required'}, status=400)

    try:
        result = _smart_predict_safe(question)

        # Persist prediction
        home_team = result.get('home_team') or ''
        away_team = result.get('away_team') or ''
        predicted_result = result.get('prediction') or result.get('verdict', '')
        Prediction.objects.create(
            user=user, engine='NL', input_data={'question': question},
            output_data=result, confidence=result.get('confidence', 0),
            home_team=home_team, away_team=away_team,
            predicted_result=predicted_result,
        )
        user.predictions_today += 1
        user.total_predictions += 1
        user.save(update_fields=['predictions_today', 'total_predictions'])

        return JsonResponse({
            'success': True,
            'result': result,
            'predictions_left': user.predictions_left_today,
        })
    except Exception as e:
        logger.error(f"Smart AI error: {e}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)
