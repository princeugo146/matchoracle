import json, logging
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.utils import timezone
from django.http import JsonResponse
from .models import Prediction, TeamRanking, WeeklyTip
from .engine import engine_a, engine_b, compute_elo, engine_d, natural_language

logger = logging.getLogger(__name__)

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
            result = natural_language(input_data.get('question', ''))
            predicted_result = result.get('prediction', '')
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
