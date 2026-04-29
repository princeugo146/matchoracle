import uuid
import requests
import json
from django.shortcuts import render, redirect
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.conf import settings
from django.utils import timezone
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.http import JsonResponse
from .models import User, Payment
from .forms import RegisterForm, LoginForm
from datetime import timedelta

def register(request):
    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            send_welcome_email(user)
            messages.success(request, f'Welcome to MatchOracle! You have 6 free predictions.')
            return redirect('dashboard')
    else:
        form = RegisterForm()
    return render(request, 'accounts/register.html', {'form': form})

def login_view(request):
    if request.method == 'POST':
        form = LoginForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            password = form.cleaned_data['password']
            user = authenticate(request, username=email, password=password)
            if user:
                login(request, user)
                return redirect(request.GET.get('next', 'dashboard'))
            messages.error(request, 'Invalid email or password.')
    else:
        form = LoginForm()
    return render(request, 'accounts/login.html', {'form': form})

def logout_view(request):
    logout(request)
    return redirect('home')

@login_required
def profile(request):
    return render(request, 'accounts/profile.html', {'user': request.user})

@login_required
def subscribe(request, plan):
    if plan not in ['basic', 'pro']:
        messages.error(request, 'Invalid plan.')
        return redirect('pricing')
    
    cfg = settings.MATCHORACLE
    plan_info = cfg['PLANS'][plan]
    amount = plan_info['price'] * 100  # Paystack uses kobo
    reference = f"mo_{uuid.uuid4().hex[:12]}"

    Payment.objects.create(
        user=request.user, plan=plan,
        amount=plan_info['price'], currency='NGN', reference=reference
    )

    return render(request, 'accounts/checkout.html', {
        'plan': plan, 'plan_info': plan_info,
        'amount': amount, 'reference': reference,
        'symbol': cfg['CURRENCY_SYMBOL'],
        'paystack_public_key': cfg['PAYSTACK_PUBLIC_KEY'],
        'user': request.user,
    })

@login_required
def verify_payment(request):
    reference = request.GET.get('reference')
    if not reference:
        messages.error(request, 'No payment reference found.')
        return redirect('dashboard')

    try:
        payment = Payment.objects.get(reference=reference, user=request.user)
    except Payment.DoesNotExist:
        messages.error(request, 'Payment not found.')
        return redirect('dashboard')

    # Verify with Paystack
    cfg = settings.MATCHORACLE
    headers = {'Authorization': f'Bearer {cfg["PAYSTACK_SECRET_KEY"]}'}
    resp = requests.get(f'https://api.paystack.co/transaction/verify/{reference}', headers=headers)
    
    if resp.status_code == 200:
        data = resp.json()
        if data['data']['status'] == 'success':
            payment.status = 'success'
            payment.verified_at = timezone.now()
            payment.save()

            plan_days = cfg['PLANS'][payment.plan]['duration_days']
            request.user.plan = payment.plan
            request.user.subscription_start = timezone.now()
            request.user.subscription_end = timezone.now() + timedelta(days=plan_days)
            request.user.save()

            send_subscription_email(request.user, payment.plan)
            messages.success(request, f'🎉 Payment successful! Your {payment.plan.title()} plan is now active.')
            return redirect('dashboard')

    messages.error(request, 'Payment verification failed. Contact support.')
    return redirect('dashboard')

def send_welcome_email(user):
    try:
        send_mail(
            subject='Welcome to MatchOracle ⚽',
            message=f'''Hi {user.first_name or user.username},

Welcome to MatchOracle — Your Football Intelligence Engine!

You have 6 FREE predictions to try all 4 engines:
• Engine A: Match Prediction
• Engine B: Player Rating  
• Engine C: Team Ranking
• Engine D: Match Simulation

Your API Key: {user.api_key}

Login at: http://yourdomain.com/accounts/login/

The MatchOracle Team
''',
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=True,
        )
    except Exception:
        pass

def send_subscription_email(user, plan):
    cfg = settings.MATCHORACLE
    plan_info = cfg['PLANS'][plan]
    try:
        send_mail(
            subject=f'MatchOracle {plan.title()} Plan Activated! ⚽',
            message=f'''Hi {user.first_name or user.username},

Your {plan_info["name"]} subscription is now ACTIVE!

Plan: {plan_info["name"]}
Expires: {user.subscription_end.strftime("%d %B %Y")}
Daily Predictions: {plan_info["predictions_per_day"]}
API Access: {"Yes" if plan_info["api_access"] else "No"}

Your API Key: {user.api_key}

Use your API key to integrate MatchOracle into your own apps.
Documentation: http://yourdomain.com/api/v1/docs/

The MatchOracle Team
''',
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=True,
        )
    except Exception:
        pass
