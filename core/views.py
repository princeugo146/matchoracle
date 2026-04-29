from django.shortcuts import render
from django.conf import settings

def home(request):
    from core.models import WeeklyForecast
    from predictions.models import Prediction
    from accounts.models import User
    forecasts = WeeklyForecast.objects.filter(is_published=True)[:6]
    stats = {
        'total_predictions': Prediction.objects.count(),
        'total_users': User.objects.count(),
        'accuracy_rate': 72,
    }
    plans = settings.MATCHORACLE['PLANS']
    engines = [
        ('A','Match Prediction','🎯','#00d4ff'),
        ('B','Player Rating','⭐','#a78bfa'),
        ('C','Team Ranking','🏆','#34d399'),
        ('D','Match Simulation','🎮','#fb923c'),
    ]
    return render(request, 'core/home.html', {
        'forecasts': forecasts, 'stats': stats,
        'plans': plans, 'engines': engines
    })

def pricing(request):
    plans = settings.MATCHORACLE['PLANS']
    symbol = settings.MATCHORACLE['CURRENCY_SYMBOL']
    return render(request, 'core/pricing.html', {'plans': plans, 'symbol': symbol})
