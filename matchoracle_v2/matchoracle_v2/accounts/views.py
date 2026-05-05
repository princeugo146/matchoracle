import uuid
import requests
from django.shortcuts import render, redirect
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.conf import settings
from django.utils import timezone
from django.core.mail import send_mail
from django.http import JsonResponse
from .models import User, Payment
from .forms import RegisterForm, LoginForm
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)


def register(request):
    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            # Handle referral
            ref_code = request.session.get('ref_code') or request.POST.get('ref_code')
            if ref_code:
                try:
                    referrer = User.objects.get(referral_code=ref_code)
                    user.referred_by = referrer
                    user.save()
                    # Give referrer 7 bonus days
                    referrer.referral_bonus_days += 7
                    if referrer.subscription_end:
                        referrer.subscription_end += timedelta(days=7)
                    referrer.save()
                except User.DoesNotExist:
                    pass
            login(request, user, backend='django.contrib.auth.backends.ModelBackend')
            _send_welcome_email(user)
            messages.success(request, f'Welcome to MatchOracle! You have 6 free predictions to start.')
            return redirect('dashboard')
    else:
        form = RegisterForm()
    return render(request, 'accounts/register.html', {'form': form})


def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    if request.method == 'POST':
        form = LoginForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            password = form.cleaned_data['password']
            user = authenticate(request, username=email, password=password)
            if user:
                login(request, user)
                next_url = request.GET.get('next', 'dashboard')
                return redirect(next_url)
            messages.error(request, 'Invalid email or password.')
    else:
        form = LoginForm()
    return render(request, 'accounts/login.html', {'form': form})


def logout_view(request):
    logout(request)
    return redirect('home')


@login_required
def profile(request):
    from predictions.models import Prediction
    recent = Prediction.objects.filter(user=request.user).order_by('-created_at')[:5]
    payments = Payment.objects.filter(user=request.user).order_by('-created_at')[:5]
    return render(request, 'accounts/profile.html', {
        'user': request.user, 'recent': recent, 'payments': payments,
    })


@login_required
def subscribe(request, plan):
    if plan not in ['basic', 'pro']:
        return redirect('pricing')
    cfg = settings.MATCHORACLE
    plan_info = cfg['PLANS'][plan]
    amount = plan_info['price'] * 100
    reference = f"mo_{uuid.uuid4().hex[:14]}"
    Payment.objects.create(
        user=request.user, plan=plan,
        amount=plan_info['price'], currency='NGN', reference=reference
    )
    return render(request, 'accounts/checkout.html', {
        'plan': plan, 'plan_info': plan_info,
        'amount': amount, 'reference': reference,
        'paystack_public_key': cfg['PAYSTACK_PUBLIC_KEY'],
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

    cfg = settings.MATCHORACLE
    try:
        headers = {'Authorization': f'Bearer {cfg["PAYSTACK_SECRET_KEY"]}'}
        resp = requests.get(
            f'https://api.paystack.co/transaction/verify/{reference}',
            headers=headers, timeout=10
        )
        if resp.status_code == 200:
            data = resp.json()
            if data.get('data', {}).get('status') == 'success':
                payment.status = 'success'
                payment.verified_at = timezone.now()
                payment.save()
                plan_days = cfg['PLANS'][payment.plan]['duration_days']
                request.user.plan = payment.plan
                request.user.subscription_start = timezone.now()
                request.user.subscription_end = timezone.now() + timedelta(days=plan_days)
                request.user.save()
                _send_subscription_email(request.user, payment.plan)
                messages.success(request, f'🎉 Payment successful! Your {payment.plan.title()} plan is now active.')
                return redirect('dashboard')
    except Exception as e:
        logger.error(f"Payment verification error: {e}")

    # Synchronous verification failed — queue an async retry via Celery
    try:
        from core.tasks import verify_payment_task
        verify_payment_task.delay(reference=reference, user_id=request.user.pk)
        messages.info(request, 'Payment is being verified. Your plan will be activated within a minute.')
    except Exception as e:
        logger.error(f"Payment verification error: {e}")
        messages.error(request, 'Payment verification failed. Contact support.')
    return redirect('dashboard')


@login_required
def update_favourites(request):
    if request.method == 'POST':
        import json
        data = json.loads(request.body)
        teams = data.get('teams', [])[:5]
        request.user.favourite_teams = teams
        request.user.save()
        return JsonResponse({'success': True})
    return JsonResponse({'error': 'POST only'}, status=405)


@login_required
def regenerate_api_key(request):
    from .models import generate_api_key
    request.user.api_key = generate_api_key()
    request.user.save()
    return JsonResponse({'api_key': request.user.api_key})


def _send_welcome_email(user):
    try:
        from core.tasks import send_email_task
        send_email_task.delay(
            subject='Welcome to MatchOracle ⚽ — Your AI Football Engine',
            message=f'''Hi {user.first_name or user.username},

Welcome to MatchOracle — Your Football Intelligence Engine!

You have 6 FREE predictions to try.

Your API Key: {user.api_key}
Your Referral Code: {user.referral_code}

Login: https://matchoracle-production.up.railway.app/accounts/login/

The MatchOracle Team
''',
            recipient_list=[user.email],
        )
    except Exception as e:
        logger.error(f"Welcome email error: {e}")


def _send_subscription_email(user, plan):
    cfg = settings.MATCHORACLE
    plan_info = cfg['PLANS'][plan]
    try:
        send_mail(
            subject=f'MatchOracle {plan.title()} Plan Active! ⚽',
            message=f'''Hi {user.first_name or user.username},

Your {plan_info["name"]} subscription is now ACTIVE!

Plan: {plan_info["name"]}
Expires: {user.subscription_end.strftime("%d %B %Y")}
Predictions/day: {plan_info["predictions_per_day"]}
API Access: {"Yes" if plan_info["api_access"] else "No"}

Your API Key: {user.api_key}

The MatchOracle Team
''',
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=True,
        )
    except Exception as e:
        logger.error(f"Subscription email error: {e}")
