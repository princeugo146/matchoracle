from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.utils import timezone
from .models import Prediction, TeamRanking
from .engine import engine_a_predict, engine_b_rate, compute_elo, engine_d_simulate
import json

@login_required
def dashboard(request):
    user = request.user
    recent = Prediction.objects.filter(user=user)[:10]
    rankings = TeamRanking.objects.filter(user=user)[:10]
    stats = {
        'total': Prediction.objects.filter(user=user).count(),
        'engine_a': Prediction.objects.filter(user=user, engine='A').count(),
        'engine_b': Prediction.objects.filter(user=user, engine='B').count(),
        'engine_d': Prediction.objects.filter(user=user, engine='D').count(),
    }
    plans = settings.MATCHORACLE['PLANS']
    return render(request, 'predictions/dashboard.html', {
        'recent': recent, 'rankings': rankings, 'stats': stats,
        'plans': plans, 'symbol': settings.MATCHORACLE['CURRENCY_SYMBOL'],
    })

@login_required
def run_engine(request, engine):
    user = request.user
    if not user.can_predict:
        return render(request, 'predictions/limit_reached.html', {'plans': settings.MATCHORACLE['PLANS']})

    if request.method == 'POST':
        input_data = json.loads(request.body)
        result = None

        if engine == 'A':
            result = engine_a_predict(input_data)
        elif engine == 'B':
            result = engine_b_rate(input_data)
        elif engine == 'D':
            result = engine_d_simulate(input_data)

        if result:
            Prediction.objects.create(user=user, engine=engine, input_data=input_data,
                                      output_data=result, confidence=result.get('confidence', 0))
            # Update usage
            today = timezone.now().date()
            if user.predictions_date != today:
                user.predictions_today = 1
                user.predictions_date = today
            else:
                user.predictions_today += 1
            if user.plan == 'free':
                user.trial_count += 1
            user.save()

            from django.http import JsonResponse
            return JsonResponse({'success': True, 'result': result})

    return render(request, 'predictions/engine.html', {'engine': engine})

@login_required
def add_ranking(request):
    if request.method == 'POST':
        import json
        data = json.loads(request.body)
        name = data.get('name', '').strip()
        if not name:
            from django.http import JsonResponse
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
            defaults={'power_elo': elo, 'wins': wins, 'draws': draws, 'losses': losses, 'goals_for': gf, 'goals_against': ga}
        )
        rankings = list(TeamRanking.objects.filter(user=request.user).values('name','power_elo','wins','draws','losses','goals_for','goals_against'))
        from django.http import JsonResponse
        return JsonResponse({'success': True, 'rankings': rankings})

    from django.http import JsonResponse
    return JsonResponse({'error': 'POST only'}, status=405)
