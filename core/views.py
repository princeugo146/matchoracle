from django.shortcuts import render
from django.http import JsonResponse
from django.conf import settings
from .models import WeeklyForecast
from .live_scores import get_live_scores, get_todays_fixtures


def home(request):
    from predictions.models import Prediction
    from accounts.models import User
    forecasts = WeeklyForecast.objects.filter(is_published=True)[:6]
    total_preds = Prediction.objects.count()
    total_users = User.objects.count()
    engines = [
        ('A','Match Prediction','🎯','#00d4ff'),
        ('B','Player Rating','⭐','#a78bfa'),
        ('C','Team Ranking','🏆','#34d399'),
        ('D','Match Simulation','🎮','#fb923c'),
    ]
    features = [
        ('⚡','AI Match Prediction','V1 algorithm + Claude AI hybrid gives you win/draw/loss probabilities with full reasoning.'),
        ('📊','Player Rating System','FIFA-style ratings based on goals, assists, pass accuracy, tackles and more.'),
        ('🏆','ELO Team Rankings','Dynamic power rankings using opponent strength, goal difference and form.'),
        ('🎮','Match Simulation','Monte Carlo simulation runs 100,000 match scenarios for the most likely scoreline.'),
        ('🔴','Live Scores','All major leagues updated every 60 seconds with auto-refresh.'),
        ('📅','Weekly Tips','Free and Pro weekly match tips with AI analysis and confidence scores.'),
        ('🔗','Developer API','Full REST API with personal key. Integrate MatchOracle into your own apps.'),
        ('👥','Referral System','Earn 7 bonus days for every person you refer who subscribes.'),
        ('💬','Natural Language AI','Ask any football question in plain English and get an AI prediction.'),
    ]
    return render(request, 'core/home.html', {
        'forecasts': forecasts, 'total_preds': total_preds,
        'total_users': total_users, 'engines': engines, 'features': features,
    })


def pricing(request):
    return render(request, 'core/pricing.html')


def live_scores_page(request):
    live = get_live_scores()
    today = get_todays_fixtures()
    live_count = len([s for s in live if s.get('minute')])
    return render(request, 'core/scores.html', {
        'live': live, 'today': today, 'live_count': live_count,
    })


def live_scores_api(request):
    live = get_live_scores()
    today = get_todays_fixtures()
    return JsonResponse({
        'live': live, 'today': today,
        'live_count': len([s for s in live if s.get('minute')]),
    })


def api_docs_page(request):
    endpoints = [
        {'method':'POST','path':'/api/v1/predict/match/','description':'Engine A — Predict match result with win/draw/loss probabilities','example':'{"home":{"name":"Arsenal","goals_scored":2.1,"form":"W W D W W"},"away":{"name":"Chelsea"}}'},
        {'method':'POST','path':'/api/v1/predict/player/','description':'Engine B — Calculate FIFA-style player rating','example':'{"name":"Haaland","position":"ST","goals":22,"assists":8,"games":28}'},
        {'method':'POST','path':'/api/v1/predict/simulate/','description':'Engine D — Run Monte Carlo match simulation','example':'{"home":{"name":"Liverpool","attack":85,"defence":78,"elo":1350},"away":{"name":"Bayern","attack":88}}'},
        {'method':'GET','path':'/api/v1/forecasts/','description':'Get this week\'s match forecasts (no auth required)','example':None},
        {'method':'GET','path':'/api/v1/me/','description':'Get your account info, plan details and usage stats','example':None},
    ]
    return render(request, 'core/api_docs.html', {'endpoints': endpoints})


def leaderboard(request):
    from accounts.models import User
    from django.db.models import Count
    top_users = User.objects.annotate(
        pred_count=Count('predictions')
    ).order_by('-pred_count')[:20]
    return render(request, 'core/leaderboard.html', {'top_users': top_users})


def health(request):
    return JsonResponse({'status': 'ok', 'version': settings.MATCHORACLE['VERSION']})
