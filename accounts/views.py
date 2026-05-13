import uuid
import requests
import logging
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

logger = logging.getLogger(__name__)


def register(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            try:
                user = form.save()
                login(request, user, backend='django.contrib.auth.backends.ModelBackend')
                try:
                    _send_welcome_email(user)
                except Exception as e:
                    logger.error(f"Welcome email error: {e}")
                messages.success(request, f'Welcome to MatchOracle! You have 3 free predictions per day.')
                return redirect('dashboard')
            except Exception as e:
                logger.error(f"Registration error: {e}", exc_info=True)
                messages.error(request, f'Registration failed: {str(e)}. Please try again.')
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f'{error}')
    else:
        form = RegisterForm()
    return render(request, 'accounts/register.html', {'form': form})


def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    if request.method == 'POST':
        form = LoginForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email'].strip().lower()
            password = form.cleaned_data['password']
            try:
                user_obj = User.objects.get(email=email)
                user = authenticate(request, username=user_obj.username, password=password)
            except User.DoesNotExist:
                user = None
            if user is not None:
                login(request, user)
                next_url = request.GET.get('next', 'dashboard')
                return redirect(next_url)
            else:
                messages.error(request, 'Incorrect email or password. Please try again.')
    else:
        form = LoginForm()
    return render(request, 'accounts/login.html', {'form': form})


def logout_view(request):
    logout(request)
    return redirect('home')


@login_required
def profile(request):
    payments = Payment.objects.filter(user=request.user).order_by('-created_at')[:5]
    plan_info = settings.MATCHORACLE['PLANS'].get(request.user.plan, {})
    return render(request, 'accounts/profile.html', {
        'payments': payments,
        'plan_info': plan_info,
    })


@login_required
def subscribe(request, plan):
    if plan not in ['basic', 'pro']:
        return redirect('pricing')
    cfg = settings.MATCHORACLE
    plan_info = cfg['PLANS'][plan]
    reference = f"mo_{uuid.uuid4().hex[:14]}"
    Payment.objects.create(
        user=request.user, plan=plan,
        amount=plan_info['price'], reference=reference
    )
    return render(request, 'accounts/checkout.html', {
        'plan': plan, 'plan_info': plan_info,
        'amount': plan_info['price'] * 100,
        'reference': reference,
    })


@login_required
def verify_payment(request):
    reference = request.GET.get('reference')
    if not reference:
        messages.error(request, 'No payment reference found.')
        return redirect('dashboard')
    try:
        payment = Payment.objects.get(reference=reference, user=request.user)
        cfg = settings.MATCHORACLE
        headers = {'Authorization': f'Bearer {cfg["PAYSTACK_SECRET_KEY"]}'}
        resp = requests.get(
            f'https://api.paystack.co/transaction/verify/{reference}',
            headers=headers, timeout=15
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
                try:
                    _send_subscription_email(request.user, payment.plan)
                except Exception:
                    pass
                messages.success(request, f'Payment successful! Your {payment.plan.title()} plan is now active.')
                return redirect('dashboard')
    except Exception as e:
        logger.error(f"Payment error: {e}", exc_info=True)
    messages.error(request, 'Payment verification failed. Please contact support.')
    return redirect('dashboard')


def _send_welcome_email(user):
    cfg = settings.MATCHORACLE
    send_mail(
        subject='Welcome to MatchOracle - Football Intelligence Engine',
        message=(
            f'Hi {user.first_name or user.username},\n\n'
            f'Welcome to MatchOracle!\n\n'
            f'You have 3 free predictions per day to try all 4 engines.\n\n'
            f'Your API Key: {user.api_key}\n'
            f'Your Referral Code: {user.referral_code}\n\n'
            f'Login at: https://matchoracle-production.up.railway.app\n\n'
            f'The MatchOracle Team'
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        fail_silently=True,
    )


def _send_subscription_email(user, plan):
    cfg = settings.MATCHORACLE
    plan_info = cfg['PLANS'][plan]
    send_mail(
        subject=f'MatchOracle {plan.title()} Plan Activated!',
        message=(
            f'Hi {user.first_name or user.username},\n\n'
            f'Your {plan_info["name"]} subscription is now ACTIVE!\n\n'
            f'Plan: {plan_info["name"]}\n'
            f'Expires: {user.subscription_end.strftime("%d %B %Y")}\n'
            f'Predictions/day: {plan_info["predictions_per_day"]}\n'
            f'API Access: {"Yes" if plan_info["api_access"] else "No"}\n\n'
            f'Your API Key: {user.api_key}\n\n'
            f'The MatchOracle Team'
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        fail_silently=True,
    )
