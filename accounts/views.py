import uuid
import requests
import logging
from django.shortcuts import render, redirect
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.conf import settings
from django.utils import timezone
from django.http import JsonResponse
from .models import User, Payment
from datetime import timedelta

logger = logging.getLogger(__name__)


def register(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    error = None
    if request.method == 'POST':
        email = request.POST.get('email', '').strip().lower()
        password = request.POST.get('password', '')
        password2 = request.POST.get('password2', '')
        first_name = request.POST.get('first_name', '').strip()
        security_question = request.POST.get('security_question', '').strip()
        security_answer = request.POST.get('security_answer', '').strip()

        if not email or not password:
            error = 'Email and password are required.'
        elif password != password2:
            error = 'Passwords do not match.'
        elif len(password) < 6:
            error = 'Password must be at least 6 characters.'
        elif not security_question or not security_answer:
            error = 'Please set a security question and answer for account recovery.'
        elif User.objects.filter(email=email).exists():
            error = 'An account with this email already exists. Please login.'
        else:
            try:
                user = User.objects.create_user(
                    username=email,
                    email=email,
                    password=password,
                    first_name=first_name,
                )
                user.security_question = security_question
                user.security_answer = security_answer
                user.save()
                login(request, user, backend='django.contrib.auth.backends.ModelBackend')
                messages.success(request, f'Welcome to MatchOracle! You have 3 free predictions per day.')
                return redirect('dashboard')
            except Exception as e:
                logger.error(f"Register error: {e}", exc_info=True)
                error = f'Registration failed. Please try again.'

    return render(request, 'accounts/register.html', {'error': error})


def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    error = None
    if request.method == 'POST':
        email = request.POST.get('email', '').strip().lower()
        password = request.POST.get('password', '')
        if not email or not password:
            error = 'Please enter your email and password.'
        else:
            user = None
            # Method 1: authenticate with email as username
            user = authenticate(request, username=email, password=password)
            # Method 2: find user by email then authenticate with their username
            if not user:
                try:
                    u = User.objects.get(email=email)
                    user = authenticate(request, username=u.username, password=password)
                except User.DoesNotExist:
                    pass
            if user and user.is_active:
                login(request, user)
                next_url = request.GET.get('next', '/dashboard/')
                return redirect(next_url)
            else:
                error = 'Incorrect email or password. Please try again.'

    return render(request, 'accounts/login.html', {'error': error})


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
    reference = 'mo_' + uuid.uuid4().hex[:14]
    Payment.objects.create(
        user=request.user, plan=plan,
        amount=plan_info['price'], reference=reference
    )
    return render(request, 'accounts/checkout.html', {
        'plan': plan,
        'plan_info': plan_info,
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
                messages.success(request, f'Payment successful! Your {payment.plan.title()} plan is now active.')
                return redirect('dashboard')
    except Exception as e:
        logger.error(f"Payment verify error: {e}", exc_info=True)
    messages.error(request, 'Payment verification failed. Contact support.')
    return redirect('dashboard')


def password_reset_request(request):
    """User enters email to start password reset"""
    if request.method == 'POST':
        email = request.POST.get('email', '').strip().lower()
        try:
            user = User.objects.get(email=email)
            if not user.security_question:
                messages.error(request, 'No security question set for this account. Please contact support.')
                return render(request, 'accounts/password_reset_request.html')
            # Store user ID in session for next step
            request.session['reset_user_id'] = user.id
            request.session['reset_email'] = email
            return redirect('security_question')
        except User.DoesNotExist:
            messages.error(request, 'No account found with that email address.')
    return render(request, 'accounts/password_reset_request.html')


def security_question(request):
    """Display security question for verification"""
    user_id = request.session.get('reset_user_id')
    if not user_id:
        return redirect('password_reset')

    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return redirect('password_reset')

    if request.method == 'POST':
        answer = request.POST.get('answer', '').strip().lower()
        stored_answer = user.security_answer.strip().lower()

        if answer == stored_answer:
            request.session['reset_verified'] = True
            return redirect('password_reset_confirm')
        else:
            messages.error(request, 'Incorrect answer. Please try again.')

    return render(request, 'accounts/security_question.html', {
        'question': user.security_question,
        'email': user.email,
    })


def password_reset_confirm(request):
    """User sets new password after answering security question"""
    user_id = request.session.get('reset_user_id')
    verified = request.session.get('reset_verified')

    if not user_id or not verified:
        return redirect('password_reset')

    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return redirect('password_reset')

    if request.method == 'POST':
        password1 = request.POST.get('password1', '')
        password2 = request.POST.get('password2', '')

        if not password1 or not password2:
            messages.error(request, 'Please fill in all fields.')
        elif password1 != password2:
            messages.error(request, 'Passwords do not match.')
        elif len(password1) < 8:
            messages.error(request, 'Password must be at least 8 characters.')
        else:
            user.set_password(password1)
            user.save()

            # Clear reset session keys
            request.session.pop('reset_user_id', None)
            request.session.pop('reset_email', None)
            request.session.pop('reset_verified', None)

            messages.success(request, 'Password reset successful! Please log in with your new password.')
            return redirect('login')

    return render(request, 'accounts/password_reset_confirm.html')
