import json
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.utils import timezone
from django.http import JsonResponse
from django.db.models import Count, Avg
from .models import Prediction, TeamRanking, WeeklyTip
from .engine import engine_a, engine_b, compute_elo, engine_d, natural_language_predict


@login_required
def dashboard(request):
    from core.live_scores import get_live_scores
    from core.models import WeeklyForecast
    user = request.user
    recent = Prediction.objects.filter(user=user)[:8]
    rankings = TeamRanking.objects.filter(user=user)[:10]
    tips = WeeklyTip.objects.filter(is_pro_only=False).order_by('-created_at')[:3]
    pro_tips = WeeklyTip.objects.filter(is_pro_only=True).order_by('-created_at')[:3]
    forecasts = WeeklyForecast.objects.filter(is_published=True)[:4]
    live_scores = get_live_scores()[:4]

    stats = {
        'total': Prediction.objects.filter(user=user).count(),
        'engine_a': Prediction.objects.filter(user=user, engine='A').count(),
        'engine_b': Prediction.objects.filter(user=user, engine='B').count(),
        'engine_d': Prediction.objects.filter(user=user, engine='D').count(),
        'accuracy': user.accuracy_rate,
    }

    # Prediction history for chart
    from django.db.models.functions import TruncDate
    history = (
        Prediction.objects.filter(user=user)
        .annotate(date=TruncDate('created_at'))
        .values('date')
        .annotate(count=Count('id'))
        .order_by('date')
    )[:30]

    return render(request, 'predictions/dashboard.html', {
        'recent': recent, 'rankings': rankings, 'stats': stats,
        'tips': tips, 'pro_tips': pro_tips, 'forecasts': forecasts,
        'live_scores': live_scores, 'history': list(history),
    })


@login_required
def run_engine(request, engine):
    user = request.user
    if not user.is_subscription_active:
        return JsonResponse({'error': 'subscription_expired'}, status=403)
    if not user.can_predict:
        return JsonResponse({'error': 'daily_limit_reached'}, status=429)

    if request.method == 'POST':
        try:
            input_data = json.loads(request.body)
        except Exception:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        result = None
        home_team = ''
        away_team = ''
        predicted_result = ''

        if engine == 'A':
            result = engine_a(input_data)
            home_team = input_data.get('home', {}).get('name', '')
            away_team = input_data.get('away', {}).get('name', '')
            predicted_result = result.get('verdict', '')
        elif engine == 'B':
            result = engine_b(input_data)
        elif engine == 'D':
            result = engine_d(input_data)
            home_team = input_data.get('home', {}).get('name', '')
            away_team = input_data.get('away', {}).get('name', '')
            predicted_result = result.get('likely_score', '')
        elif engine == 'NL':
            question = input_data.get('question', '')
            result = natural_language_predict(question)
        else:
            return JsonResponse({'error': 'Invalid engine'}, status=400)

        if result:
            Prediction.objects.create(
                user=user, engine=engine, input_data=input_data,
                output_data=result, confidence=result.get('confidence', 0),
                home_team=home_team, away_team=away_team,
                predicted_result=predicted_result,
            )
            # Update usage
            today = timezone.now().date()
            if user.predictions_date != today:
                user.predictions_today = 1
                user.predictions_date = today
            else:
                user.predictions_today += 1
            if user.plan == 'free':
                user.trial_count += 1
            user.total_predictions += 1
            user.save()

            return JsonResponse({'success': True, 'result': result})

    return JsonResponse({'error': 'POST only'}, status=405)


@login_required
def add_ranking(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
        except Exception:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        name = data.get('name', '').strip()
        if not name:
            return JsonResponse({'error': 'Team name required'}, status=400)

        wins = int(data.get('wins', 0))
        draws = int(data.get('draws', 0))
        losses = int(data.get('losses', 0))
        gf = int(data.get('goals_for', 0))
        ga = int(data.get('goals_against', 0))
        opp = float(data.get('opp_strength', 5))
        base = int(data.get('base_elo', 1000))
        elo = compute_elo(wins, draws, losses, gf, ga, opp, base)

        team, _ = TeamRanking.objects.update_or_create(
            user=request.user, name=name,
            defaults={
                'power_elo': elo, 'wins': wins, 'draws': draws,
                'losses': losses, 'goals_for': gf, 'goals_against': ga
            }
        )
        rankings = list(TeamRanking.objects.filter(user=request.user).values(
            'name', 'power_elo', 'wins', 'draws', 'losses', 'goals_for', 'goals_against'
        ))
        return JsonResponse({'success': True, 'rankings': rankings})

    return JsonResponse({'error': 'POST only'}, status=405)


@login_required
def prediction_history(request):
    predictions = Prediction.objects.filter(user=request.user).order_by('-created_at')
    engine_filter = request.GET.get('engine', '')
    if engine_filter:
        predictions = predictions.filter(engine=engine_filter)
    return render(request, 'predictions/history.html', {
        'predictions': predictions[:50],
        'engine_filter': engine_filter,
        'stats': {
            'total': predictions.count(),
            'accuracy': request.user.accuracy_rate,
        }
    })


@login_required
def weekly_tips(request):
    user = request.user
    free_tips = WeeklyTip.objects.filter(is_pro_only=False).order_by('-created_at')[:10]
    pro_tips = WeeklyTip.objects.filter(is_pro_only=True).order_by('-created_at')[:10] if user.plan == 'pro' else []
    return render(request, 'predictions/tips.html', {
        'free_tips': free_tips, 'pro_tips': pro_tips,
        'is_pro': user.plan == 'pro',
    })
