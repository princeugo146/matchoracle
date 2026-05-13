from django.shortcuts import render
from django.http import JsonResponse
from django.conf import settings
from .models import WeeklyForecast
from .live_scores import get_live_scores, get_todays_fixtures

def home(request):
    from predictions.models import Prediction
    from accounts.models import User
    forecasts = WeeklyForecast.objects.filter(is_published=True)[:6]
    return render(request, 'core/home.html', {
        'forecasts': forecasts,
        'total_preds': Prediction.objects.count(),
        'total_users': User.objects.count(),
    })

def pricing(request):
    return render(request, 'core/pricing.html')

def scores(request):
    live = get_live_scores()
    today = get_todays_fixtures()
    live_count = len([s for s in live if s.get('minute')])
    return render(request, 'core/scores.html', {'live': live, 'today': today, 'live_count': live_count})

def scores_api(request):
    live = get_live_scores()
    return JsonResponse({'live': live, 'today': get_todays_fixtures()})

def leaderboard(request):
    from accounts.models import User
    from django.db.models import Count
    top_users = User.objects.annotate(pred_count=Count('predictions')).order_by('-pred_count')[:20]
    return render(request, 'core/leaderboard.html', {'top_users': top_users})

def api_docs(request):
    return render(request, 'core/api_docs.html')

def health(request):
    return JsonResponse({'status': 'ok'})
