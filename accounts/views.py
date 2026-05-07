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
    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            try:
                user = form.save()
                login(request, user, backend='django.contrib.auth.backends.ModelBackend')
                try:
                    _send_welcome_email(user)
                except Exception as e:
                    logger.error(f"Email error: {e}")
                messages.success(request, 'Welcome to MatchOracle! You have 6 free predictions.')
                return redirect('dashboard')
            except Exception as e:
                logger.error(f"Registration error: {e}")
                messages.error(request, 'Registration failed. Please try again.')
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
            try:
                user = authenticate(request, username=email, password=password)
                if user:
                    login(request, user)
                    return redirect(request.GET.get('next', 'dashboard'))
                messages.error(request, 'Invalid email or password.')
            except Exception as e:
                logger.error(f"Login error: {e}")
                messages.error(request, 'Login failed. Please try again.')
    else:
        form = LoginForm()
    return render(request, 'accounts/login.html', {'form': form})


def logout_view(request):
    logout(request)
    return redirect('home')


@login_required
def profile(request):
    payments = Payment.objects.filter(user=request.user).order_by('-created_at')[:5]
    return render(request, 'accounts/profile.html', {'payments': payments})


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
        messages.error(request, 'No payment reference.')
        return redirect('dashboard')
    try:
        payment = Payment.objects.get(reference=reference, user=request.user)
        cfg = settings.MATCHORACLE
        headers = {'Authorization': f'Bearer {cfg["PAYSTACK_SECRET_KEY"]}'}
        resp = requests.get(f'https://api.paystack.co/transaction/verify/{reference}', headers=headers, timeout=10)
        if resp.status_code == 200 and resp.json().get('data', {}).get('status') == 'success':
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
            messages.success(request, f'Payment successful! {payment.plan.title()} plan is now active.')
            return redirect('dashboard')
    except Exception as e:
        logger.error(f"Payment error: {e}")
    messages.error(request, 'Payment verification failed.')
    return redirect('dashboard')


def _send_welcome_email(user):
    send_mail(
        subject='Welcome to MatchOracle!',
        message=f'Hi {user.first_name or user.username},\n\nWelcome to MatchOracle!\n\nYour API Key: {user.api_key}\nReferral Code: {user.referral_code}\n\nYou have 6 free predictions.\n\nMatchOracle Team',
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        fail_silently=True,
    )


def _send_subscription_email(user, plan):
    cfg = settings.MATCHORACLE
    send_mail(
        subject=f'MatchOracle {plan.title()} Plan Active!',
        message=f'Hi {user.first_name or user.username},\n\nYour {plan} plan is active!\n\nExpires: {user.subscription_end.strftime("%d %B %Y")}\nAPI Key: {user.api_key}\n\nMatchOracle Team',
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        fail_silently=True,
    )
