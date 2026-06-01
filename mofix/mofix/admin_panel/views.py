import logging
from functools import wraps
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Count, Q
from django.utils import timezone
from django.http import JsonResponse
from datetime import timedelta

from accounts.models import User, Payment
from predictions.models import WeeklyTip
from .models import AdminLog

logger = logging.getLogger(__name__)


# ─── Permission decorator ────────────────────────────────────────────────────

def admin_required(view_func):
    """Only allow staff / superusers."""
    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        if not (request.user.is_staff or request.user.is_superuser):
            messages.error(request, 'You do not have permission to access the admin panel.')
            return redirect('home')
        return view_func(request, *args, **kwargs)
    return wrapper


def _get_client_ip(request):
    x_forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded:
        return x_forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


def _log(request, action, target_type='', target_id=None, description=''):
    AdminLog.objects.create(
        admin=request.user,
        action=action,
        target_type=target_type,
        target_id=target_id,
        description=description,
        ip_address=_get_client_ip(request),
    )


# ─── Dashboard ───────────────────────────────────────────────────────────────

@admin_required
def dashboard(request):
    total_users    = User.objects.count()
    active_users   = User.objects.filter(is_active=True).count()
    paid_users     = User.objects.exclude(plan='free').count()
    total_revenue  = Payment.objects.filter(status='success').aggregate(t=Sum('amount'))['t'] or 0
    recent_logs    = AdminLog.objects.select_related('admin')[:10]
    recent_signups = User.objects.order_by('-created_at')[:5]

    # Revenue last 30 days
    since = timezone.now() - timedelta(days=30)
    revenue_30d = Payment.objects.filter(status='success', verified_at__gte=since).aggregate(
        t=Sum('amount'))['t'] or 0

    # Plan breakdown
    plan_counts = {
        'free':  User.objects.filter(plan='free').count(),
        'basic': User.objects.filter(plan='basic').count(),
        'pro':   User.objects.filter(plan='pro').count(),
    }

    return render(request, 'admin_panel/admin_dashboard.html', {
        'total_users':    total_users,
        'active_users':   active_users,
        'paid_users':     paid_users,
        'total_revenue':  total_revenue,
        'revenue_30d':    revenue_30d,
        'plan_counts':    plan_counts,
        'recent_logs':    recent_logs,
        'recent_signups': recent_signups,
    })


# ─── User Management ─────────────────────────────────────────────────────────

@admin_required
def users_list(request):
    q    = request.GET.get('q', '').strip()
    plan = request.GET.get('plan', '')

    users = User.objects.all().order_by('-created_at')
    if q:
        users = users.filter(Q(email__icontains=q) | Q(first_name__icontains=q))
    if plan:
        users = users.filter(plan=plan)

    return render(request, 'admin_panel/users_list.html', {
        'users': users,
        'q': q,
        'plan_filter': plan,
    })


@admin_required
def user_edit(request, user_id):
    target = get_object_or_404(User, pk=user_id)

    if request.method == 'POST':
        old_plan = target.plan
        target.first_name = request.POST.get('first_name', target.first_name).strip()
        target.email      = request.POST.get('email', target.email).strip().lower()
        target.plan       = request.POST.get('plan', target.plan)
        target.is_active  = request.POST.get('is_active') == 'on'
        target.is_staff   = request.POST.get('is_staff') == 'on'
        target.save()

        action = 'plan_change' if old_plan != target.plan else 'user_edit'
        _log(request, action, 'User', target.pk,
             f"Edited user {target.email}; plan: {old_plan} → {target.plan}")
        messages.success(request, f'User {target.email} updated successfully.')
        return redirect('admin_users_list')

    return render(request, 'admin_panel/user_edit.html', {'target': target})


@admin_required
def user_toggle_active(request, user_id):
    target = get_object_or_404(User, pk=user_id)
    if target == request.user:
        messages.error(request, 'You cannot deactivate your own account.')
        return redirect('admin_users_list')

    target.is_active = not target.is_active
    target.save(update_fields=['is_active'])
    action = 'user_activate' if target.is_active else 'user_deactivate'
    _log(request, action, 'User', target.pk,
         f"{'Activated' if target.is_active else 'Deactivated'} user {target.email}")
    status = 'activated' if target.is_active else 'deactivated'
    messages.success(request, f'User {target.email} has been {status}.')
    return redirect('admin_users_list')


@admin_required
def user_delete(request, user_id):
    target = get_object_or_404(User, pk=user_id)
    if target == request.user:
        messages.error(request, 'You cannot delete your own account.')
        return redirect('admin_users_list')

    if request.method == 'POST':
        email = target.email
        _log(request, 'user_delete', 'User', target.pk, f"Deleted user {email}")
        target.delete()
        messages.success(request, f'User {email} has been deleted.')
        return redirect('admin_users_list')

    return render(request, 'admin_panel/user_delete_confirm.html', {'target': target})


# ─── Weekly Tips Management ───────────────────────────────────────────────────

@admin_required
def tips_list(request):
    tips = WeeklyTip.objects.all().order_by('-match_date')
    return render(request, 'admin_panel/tips_management.html', {'tips': tips})


@admin_required
def tip_create(request):
    if request.method == 'POST':
        try:
            tip = WeeklyTip.objects.create(
                home_team   = request.POST['home_team'].strip(),
                away_team   = request.POST['away_team'].strip(),
                competition = request.POST.get('competition', '').strip(),
                match_date  = request.POST['match_date'],
                tip         = request.POST['tip'].strip(),
                confidence  = int(request.POST.get('confidence', 70)),
                is_pro_only = request.POST.get('is_pro_only') == 'on',
            )
            _log(request, 'tip_create', 'WeeklyTip', tip.pk,
                 f"Created tip: {tip.home_team} vs {tip.away_team}")
            messages.success(request, 'Tip created successfully.')
            return redirect('admin_tips_list')
        except Exception as e:
            messages.error(request, f'Error creating tip: {e}')

    return render(request, 'admin_panel/tip_form.html', {'tip': None, 'action': 'Create'})


@admin_required
def tip_edit(request, tip_id):
    tip = get_object_or_404(WeeklyTip, pk=tip_id)

    if request.method == 'POST':
        try:
            tip.home_team   = request.POST['home_team'].strip()
            tip.away_team   = request.POST['away_team'].strip()
            tip.competition = request.POST.get('competition', '').strip()
            tip.match_date  = request.POST['match_date']
            tip.tip         = request.POST['tip'].strip()
            tip.confidence  = int(request.POST.get('confidence', 70))
            tip.is_pro_only = request.POST.get('is_pro_only') == 'on'
            tip.save()
            _log(request, 'tip_edit', 'WeeklyTip', tip.pk,
                 f"Edited tip: {tip.home_team} vs {tip.away_team}")
            messages.success(request, 'Tip updated successfully.')
            return redirect('admin_tips_list')
        except Exception as e:
            messages.error(request, f'Error updating tip: {e}')

    return render(request, 'admin_panel/tip_form.html', {'tip': tip, 'action': 'Edit'})


@admin_required
def tip_delete(request, tip_id):
    tip = get_object_or_404(WeeklyTip, pk=tip_id)
    if request.method == 'POST':
        desc = f"Deleted tip: {tip.home_team} vs {tip.away_team}"
        _log(request, 'tip_delete', 'WeeklyTip', tip.pk, desc)
        tip.delete()
        messages.success(request, 'Tip deleted.')
        return redirect('admin_tips_list')
    return render(request, 'admin_panel/tip_delete_confirm.html', {'tip': tip})


# ─── Revenue Dashboard ────────────────────────────────────────────────────────

@admin_required
def revenue_dashboard(request):
    # All-time totals
    total_revenue = Payment.objects.filter(status='success').aggregate(
        t=Sum('amount'))['t'] or 0
    total_payments = Payment.objects.filter(status='success').count()

    # Revenue by plan
    revenue_by_plan = {}
    for plan in ('basic', 'pro'):
        revenue_by_plan[plan] = Payment.objects.filter(
            status='success', plan=plan
        ).aggregate(t=Sum('amount'))['t'] or 0

    # Active subscriptions
    now = timezone.now()
    active_subs = User.objects.filter(
        subscription_end__gt=now
    ).exclude(plan='free').count()

    # Monthly revenue (last 12 months)
    monthly = []
    for i in range(11, -1, -1):
        start = (now - timedelta(days=30 * i)).replace(
            hour=0, minute=0, second=0, microsecond=0)
        end   = start + timedelta(days=30)
        rev   = Payment.objects.filter(
            status='success', verified_at__gte=start, verified_at__lt=end
        ).aggregate(t=Sum('amount'))['t'] or 0
        monthly.append({
            'label': start.strftime('%b %Y'),
            'revenue': float(rev),
        })

    # Revenue per user
    total_users = User.objects.count() or 1
    rev_per_user = round(float(total_revenue) / total_users, 2)

    # Recent payments
    recent_payments = Payment.objects.filter(
        status='success'
    ).select_related('user').order_by('-verified_at')[:20]

    return render(request, 'admin_panel/revenue_dashboard.html', {
        'total_revenue':    total_revenue,
        'total_payments':   total_payments,
        'revenue_by_plan':  revenue_by_plan,
        'active_subs':      active_subs,
        'monthly':          monthly,
        'rev_per_user':     rev_per_user,
        'recent_payments':  recent_payments,
    })


# ─── Audit Log ────────────────────────────────────────────────────────────────

@admin_required
def audit_log(request):
    logs = AdminLog.objects.select_related('admin').all()[:200]
    return render(request, 'admin_panel/audit_log.html', {'logs': logs})
