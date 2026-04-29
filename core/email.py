from django.core.mail import send_mail
from django.conf import settings

def send_api_key_email(user, plan):
    plan_data = settings.SUBSCRIPTION_PLANS.get(plan, {})
    subject = f"MatchOracle {plan.title()} Plan Activated - Your API Key"
    message = f"""Hello {user.first_name or user.email},

Your MatchOracle {plan_data.get('name', plan)} subscription is ACTIVE!

YOUR API KEY: {user.api_key}

Plan: {plan_data.get('name', plan)}
Price: {plan_data.get('price_display', '')}
Expires: {user.plan_expires.strftime('%B %d, %Y') if user.plan_expires else 'N/A'}

Use this key in API requests as header: X-MatchOracle-Key: {user.api_key}

Features:
{chr(10).join(['- ' + f for f in plan_data.get('features', [])])}

Keep this key safe!
The MatchOracle Team"""
    try:
        send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [user.email], fail_silently=True)
    except: pass

def send_welcome_email(user):
    subject = "Welcome to MatchOracle - Football Intelligence Engine"
    message = f"""Hello {user.first_name or 'there'},

Welcome to MatchOracle! You have 6 FREE predictions to start.

Engines available:
- Engine A: Match Prediction
- Engine B: Player Rating  
- Engine C: Team Ranking
- Engine D: Match Simulation

Upgrade anytime:
- Basic: N2,000/month
- Pro: N15,000/year

The MatchOracle Team"""
    try:
        send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [user.email], fail_silently=True)
    except: pass

def send_weekly_forecast_email(user, forecasts):
    subject = "MatchOracle Weekly Forecast - Top Matches This Week"
    lines = [f"- {f['home']} vs {f['away']}: {f['prediction']} ({f['confidence']}% confidence)" for f in forecasts]
    message = f"""Hello {user.first_name or 'there'},

This week's top predictions:

{chr(10).join(lines)}

The MatchOracle Team"""
    try:
        send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [user.email], fail_silently=True)
    except: pass
