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
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.core.cache import cache
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

        if not email or not password:
            error = 'Email and password are required.'
        elif password != password2:
            error = 'Passwords do not match.'
        elif len(password) < 6:
            error = 'Password must be at least 6 characters.'
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


# ─── Password Reset ───────────────────────────────────────────────────────────

def forgot_password(request):
    """Step 1: User enters email, receives reset link."""
    if request.user.is_authenticated:
        return redirect('dashboard')

    sent = False
    error = None
    email = ''

    if request.method == 'POST':
        email = request.POST.get('email', '').strip().lower()
        if not email:
            error = 'Please enter your email address.'
        else:
            # Rate-limit: max 3 reset requests per email per hour
            cache_key = f'pwd_reset_{email}'
            attempts = cache.get(cache_key, 0)
            if attempts >= 3:
                error = 'Too many reset requests. Please wait an hour before trying again.'
            else:
                cache.set(cache_key, attempts + 1, timeout=3600)
                # Always show "sent" to prevent email enumeration
                try:
                    user = User.objects.get(email=email)
                    _send_reset_email(request, user)
                except User.DoesNotExist:
                    pass  # Don't reveal whether email exists
                except Exception as e:
                    logger.error(f"Password reset email error: {e}", exc_info=True)
                sent = True

    return render(request, 'accounts/forgot_password.html', {
        'sent': sent,
        'error': error,
        'email': email,
    })


def _send_reset_email(request, user):
    """Generate a secure token and send the reset email."""
    uid   = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    reset_url = request.build_absolute_uri(
        f'/accounts/reset-password/{uid}/{token}/'
    )
    html_body = render_to_string('accounts/password_reset_email.html', {
        'user': user,
        'reset_url': reset_url,
    })
    send_mail(
        subject='Reset your MatchOracle password',
        message=(
            f'Hi {user.first_name or user.email},\n\n'
            f'Click the link below to reset your password (valid for 24 hours):\n\n'
            f'{reset_url}\n\n'
            f'If you did not request this, ignore this email.\n\n'
            f'— MatchOracle Team'
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        html_message=html_body,
        fail_silently=False,
    )


def reset_password(request, uidb64, token):
    """Step 2: User clicks link, sets new password."""
    if request.user.is_authenticated:
        return redirect('dashboard')

    # Validate token
    try:
        uid  = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None

    if user is None or not default_token_generator.check_token(user, token):
        return render(request, 'accounts/reset_password.html', {'invalid_link': True})

    error   = None
    success = False

    if request.method == 'POST':
        password  = request.POST.get('password', '')
        password2 = request.POST.get('password2', '')

        if not password or not password2:
            error = 'Please fill in both password fields.'
        elif password != password2:
            error = 'Passwords do not match.'
        elif len(password) < 8:
            error = 'Password must be at least 8 characters.'
        else:
            user.set_password(password)
            user.save()
            logger.info(f"Password reset successful for {user.email}")
            success = True

    return render(request, 'accounts/reset_password.html', {
        'invalid_link': False,
        'success': success,
        'error': error,
        'uidb64': uidb64,
        'token': token,
    })
