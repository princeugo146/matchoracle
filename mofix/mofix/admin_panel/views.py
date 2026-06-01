import logging
from datetime import timedelta

from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Count, Sum, Q
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.models import User, Payment
from predictions.models import Prediction, WeeklyTip
from .models import AdminLog

logger = logging.getLogger(__name__)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _get_client_ip(request):
    x_forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded:
        return x_forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


def _log_action(request, action, description, object_type='', object_id=''):
    """Write an AdminLog entry for the current staff user."""
    try:
        AdminLog.objects.create(
            admin_user=request.user,
            action=action,
            description=description,
            object_type=object_type,
            object_id=str(object_id),
            ip_address=_get_client_ip(request),
        )
    except Exception as exc:
        logger.warning("AdminLog write failed: %s", exc)


def _revenue_stats():
    """Return revenue breakdown dict keyed by plan."""
    from django.conf import settings
    plans = settings.MATCHORACLE['PLANS']
    symbol = settings.MATCHORACLE.get('CURRENCY_SYMBOL', 'NGN')

    breakdown = {}
    total_revenue = 0

    for plan_key, plan_cfg in plans.items():
        if plan_key == 'free':
            breakdown[plan_key] = {
                'name': plan_cfg['name'],
                'price': 0,
                'subscribers': User.objects.filter(plan=plan_key).count(),
                'revenue': 0,
                'symbol': symbol,
            }
            continue

        paid_payments = Payment.objects.filter(plan=plan_key, status='success')
        revenue = paid_payments.aggregate(total=Sum('amount'))['total'] or 0
        breakdown[plan_key] = {
            'name': plan_cfg['name'],
            'price': plan_cfg['price'],
            'subscribers': User.objects.filter(plan=plan_key).count(),
            'revenue': float(revenue),
            'symbol': symbol,
        }
        total_revenue += float(revenue)

    return breakdown, total_revenue


# ─── Dashboard ────────────────────────────────────────────────────────────────

@login_required
@staff_member_required
def admin_dashboard(request):
    now = timezone.now()
    thirty_days_ago = now - timedelta(days=30)
    seven_days_ago  = now - timedelta(days=7)

    # ── User stats ──────────────────────────────────────────────────────────
    total_users   = User.objects.count()
    active_users  = User.objects.filter(last_login__gte=thirty_days_ago).count()
    new_this_week = User.objects.filter(date_joined__gte=seven_days_ago).count()
    staff_count   = User.objects.filter(is_staff=True).count()

    # ── Prediction stats ────────────────────────────────────────────────────
    total_predictions   = Prediction.objects.count()
    predictions_today   = Prediction.objects.filter(created_at__date=now.date()).count()
    predictions_week    = Prediction.objects.filter(created_at__gte=seven_days_ago).count()

    # ── Revenue ─────────────────────────────────────────────────────────────
    revenue_breakdown, total_revenue = _revenue_stats()

    # ── Tips ────────────────────────────────────────────────────────────────
    tips = WeeklyTip.objects.all()[:10]

    # ── Recent logs ─────────────────────────────────────────────────────────
    recent_logs = AdminLog.objects.select_related('admin_user').all()[:20]

    # ── Plan distribution ───────────────────────────────────────────────────
    plan_counts = (
        User.objects
        .values('plan')
        .annotate(count=Count('id'))
        .order_by('plan')
    )

    _log_action(request, 'view', 'Viewed admin dashboard')

    context = {
        'total_users':        total_users,
        'active_users':       active_users,
        'new_this_week':      new_this_week,
        'staff_count':        staff_count,
        'total_predictions':  total_predictions,
        'predictions_today':  predictions_today,
        'predictions_week':   predictions_week,
        'total_revenue':      total_revenue,
        'revenue_breakdown':  revenue_breakdown,
        'tips':               tips,
        'recent_logs':        recent_logs,
        'plan_counts':        list(plan_counts),
    }
    return render(request, 'admin_panel/dashboard.html', context)


# ─── User Management ──────────────────────────────────────────────────────────

@login_required
@staff_member_required
def user_list(request):
    qs = User.objects.all().order_by('-date_joined')

    # Filters
    plan_filter   = request.GET.get('plan', '')
    status_filter = request.GET.get('status', '')
    search_query  = request.GET.get('q', '').strip()

    if plan_filter:
        qs = qs.filter(plan=plan_filter)
    if status_filter == 'active':
        qs = qs.filter(is_active=True)
    elif status_filter == 'inactive':
        qs = qs.filter(is_active=False)
    if search_query:
        qs = qs.filter(
            Q(email__icontains=search_query) |
            Q(username__icontains=search_query) |
            Q(first_name__icontains=search_query) |
            Q(last_name__icontains=search_query)
        )

    _log_action(request, 'view', f'Viewed user list (filter: plan={plan_filter}, status={status_filter}, q={search_query})')

    context = {
        'users':          qs[:200],
        'plan_filter':    plan_filter,
        'status_filter':  status_filter,
        'search_query':   search_query,
        'total_count':    qs.count(),
    }
    return render(request, 'admin_panel/users.html', context)


@login_required
@staff_member_required
def user_detail(request, user_id):
    target_user = get_object_or_404(User, pk=user_id)
    payments    = Payment.objects.filter(user=target_user).order_by('-created_at')[:10]
    predictions = Prediction.objects.filter(user=target_user).order_by('-created_at')[:10]

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'toggle_active':
            target_user.is_active = not target_user.is_active
            target_user.save(update_fields=['is_active'])
            state = 'activated' if target_user.is_active else 'deactivated'
            _log_action(request, 'update', f'User {target_user.email} {state}', 'User', target_user.pk)
            messages.success(request, f'User {target_user.email} has been {state}.')
        elif action == 'change_plan':
            new_plan = request.POST.get('plan', 'free')
            if new_plan in ['free', 'basic', 'pro']:
                old_plan = target_user.plan
                target_user.plan = new_plan
                if new_plan == 'free':
                    target_user.subscription_end = None
                target_user.save(update_fields=['plan', 'subscription_end'])
                _log_action(
                    request, 'update',
                    f'Changed plan for {target_user.email}: {old_plan} → {new_plan}',
                    'User', target_user.pk,
                )
                messages.success(request, f'Plan updated to {new_plan} for {target_user.email}.')
        return redirect('admin_user_detail', user_id=user_id)

    _log_action(request, 'view', f'Viewed user detail: {target_user.email}', 'User', target_user.pk)

    context = {
        'target_user': target_user,
        'payments':    payments,
        'predictions': predictions,
    }
    return render(request, 'admin_panel/user_detail.html', context)


# ─── Weekly Tips Management ───────────────────────────────────────────────────

@login_required
@staff_member_required
def tips_list(request):
    tips = WeeklyTip.objects.all().order_by('-match_date')
    _log_action(request, 'view', 'Viewed weekly tips list')
    return render(request, 'admin_panel/tips.html', {'tips': tips})


@login_required
@staff_member_required
def tip_create(request):
    if request.method == 'POST':
        try:
            from django.utils.dateparse import parse_datetime
            match_date_str = request.POST.get('match_date', '')
            match_date = parse_datetime(match_date_str)
            if not match_date:
                raise ValueError('Invalid date format')

            tip = WeeklyTip.objects.create(
                home_team   = request.POST.get('home_team', '').strip(),
                away_team   = request.POST.get('away_team', '').strip(),
                competition = request.POST.get('competition', '').strip(),
                match_date  = match_date,
                tip         = request.POST.get('tip', '').strip(),
                confidence  = int(request.POST.get('confidence', 70)),
                is_pro_only = request.POST.get('is_pro_only') == 'on',
            )
            _log_action(
                request, 'create',
                f'Created WeeklyTip: {tip.home_team} vs {tip.away_team}',
                'WeeklyTip', tip.pk,
            )
            messages.success(request, f'Tip created: {tip.home_team} vs {tip.away_team}')
            return redirect('admin_tips')
        except Exception as exc:
            logger.error("Tip create error: %s", exc, exc_info=True)
            messages.error(request, f'Error creating tip: {exc}')

    return render(request, 'admin_panel/tip_form.html', {'tip': None, 'action': 'Create'})


@login_required
@staff_member_required
def tip_edit(request, tip_id):
    tip = get_object_or_404(WeeklyTip, pk=tip_id)

    if request.method == 'POST':
        try:
            from django.utils.dateparse import parse_datetime
            match_date_str = request.POST.get('match_date', '')
            match_date = parse_datetime(match_date_str)
            if not match_date:
                raise ValueError('Invalid date format')

            tip.home_team   = request.POST.get('home_team', '').strip()
            tip.away_team   = request.POST.get('away_team', '').strip()
            tip.competition = request.POST.get('competition', '').strip()
            tip.match_date  = match_date
            tip.tip         = request.POST.get('tip', '').strip()
            tip.confidence  = int(request.POST.get('confidence', 70))
            tip.is_pro_only = request.POST.get('is_pro_only') == 'on'
            tip.save()

            _log_action(
                request, 'update',
                f'Updated WeeklyTip: {tip.home_team} vs {tip.away_team}',
                'WeeklyTip', tip.pk,
            )
            messages.success(request, f'Tip updated: {tip.home_team} vs {tip.away_team}')
            return redirect('admin_tips')
        except Exception as exc:
            logger.error("Tip edit error: %s", exc, exc_info=True)
            messages.error(request, f'Error updating tip: {exc}')

    return render(request, 'admin_panel/tip_form.html', {'tip': tip, 'action': 'Edit'})


@login_required
@staff_member_required
@require_POST
def tip_delete(request, tip_id):
    tip = get_object_or_404(WeeklyTip, pk=tip_id)
    label = f'{tip.home_team} vs {tip.away_team}'
    tip.delete()
    _log_action(request, 'delete', f'Deleted WeeklyTip: {label}', 'WeeklyTip', tip_id)
    messages.success(request, f'Tip deleted: {label}')
    return redirect('admin_tips')


# ─── Revenue Analytics ────────────────────────────────────────────────────────

@login_required
@staff_member_required
def revenue_view(request):
    revenue_breakdown, total_revenue = _revenue_stats()

    # Recent successful payments
    recent_payments = (
        Payment.objects
        .filter(status='success')
        .select_related('user')
        .order_by('-verified_at')[:50]
    )

    # Monthly revenue for the last 6 months
    monthly_data = []
    now = timezone.now()
    for i in range(5, -1, -1):
        month_start = (now.replace(day=1) - timedelta(days=i * 30)).replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        )
        month_end = (month_start + timedelta(days=32)).replace(day=1)
        month_revenue = (
            Payment.objects
            .filter(status='success', verified_at__gte=month_start, verified_at__lt=month_end)
            .aggregate(total=Sum('amount'))['total'] or 0
        )
        monthly_data.append({
            'label':   month_start.strftime('%b %Y'),
            'revenue': float(month_revenue),
        })

    _log_action(request, 'view', 'Viewed revenue analytics')

    context = {
        'revenue_breakdown': revenue_breakdown,
        'total_revenue':     total_revenue,
        'recent_payments':   recent_payments,
        'monthly_data':      monthly_data,
    }
    return render(request, 'admin_panel/revenue.html', context)


# ─── Admin Logs ───────────────────────────────────────────────────────────────

@login_required
@staff_member_required
def logs_view(request):
    qs = AdminLog.objects.select_related('admin_user').all()

    action_filter = request.GET.get('action', '')
    search_query  = request.GET.get('q', '').strip()

    if action_filter:
        qs = qs.filter(action=action_filter)
    if search_query:
        qs = qs.filter(
            Q(description__icontains=search_query) |
            Q(admin_user__email__icontains=search_query) |
            Q(object_type__icontains=search_query)
        )

    context = {
        'logs':           qs[:300],
        'action_filter':  action_filter,
        'search_query':   search_query,
        'action_choices': AdminLog.ACTION_CHOICES,
    }
    return render(request, 'admin_panel/logs.html', context)
