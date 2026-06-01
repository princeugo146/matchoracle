from django.shortcuts import render
from django.http import JsonResponse
from .models import WeeklyForecast
from .live_scores import get_live_scores, get_todays_fixtures

def home(request):
    from predictions.models import Prediction
    from accounts.models import User
    return render(request, 'core/home.html', {
        'forecasts': WeeklyForecast.objects.filter(is_published=True)[:6],
        'total_preds': Prediction.objects.count(),
        'total_users': User.objects.count(),
    })

def pricing(request):
    return render(request, 'core/pricing.html')

def scores(request):
    live = get_live_scores()
    today = get_todays_fixtures()
    return render(request, 'core/scores.html', {
        'live': live, 'today': today,
        'live_count': len([s for s in live if s.get('minute')]),
    })

def leaderboard(request):
    from accounts.models import User
    from django.db.models import Count
    top_users = User.objects.annotate(pred_count=Count('predictions')).order_by('-pred_count')[:20]
    return render(request, 'core/leaderboard.html', {'top_users': top_users})

def api_docs(request):
    return render(request, 'core/api_docs.html')

def health_check(request):
    return JsonResponse({'status': 'ok', 'version': '2.0.0'})

def privacy_policy(request):
    return render(request, 'legal/privacy_policy.html')

def terms_of_service(request):
    return render(request, 'legal/terms_of_service.html')

def about_us(request):
    return render(request, 'legal/about_us.html')

def api_docs(request):
    endpoints = [
        {'method':'POST','path':'/api/v1/predict/match/','desc':'Engine A - Match prediction with win/draw/loss %','example':'{"home":{"name":"Arsenal","goals_scored":2.1,"form":"W W D W W"},"away":{"name":"Chelsea"}}'},
        {'method':'POST','path':'/api/v1/predict/player/','desc':'Engine B - FIFA-style player rating','example':'{"name":"Haaland","position":"ST","goals":22,"assists":8,"games":28}'},
        {'method':'POST','path':'/api/v1/predict/simulate/','desc':'Engine D - Monte Carlo match simulation','example':'{"home":{"name":"Liverpool","attack":85,"defence":78,"elo":1350},"away":{"name":"Bayern","attack":88,"defence":80}}'},
        {'method':'GET','path':'/api/v1/forecasts/','desc':'Get weekly match forecasts (no auth needed)','example':None},
        {'method':'GET','path':'/api/v1/me/','desc':'Get your account info, plan and usage stats','example':None},
    ]
    return render(request, 'core/api_docs.html', {'endpoints': endpoints})
