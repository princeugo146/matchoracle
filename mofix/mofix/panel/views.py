import json
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db.models import Count, Sum, Q
from django.utils import timezone
from django.http import JsonResponse
from datetime import timedelta

from accounts.models import User, Payment
from predictions.models import Prediction, WeeklyTip
from .models import WeeklyTipAdmin, AdminLog
from .decorators import admin_required, log_action


# ─── Dashboard ────────────────────────────────────────────────────────────────

@admin_required
def dashboard(request):
    now = timezone.now()
    thirty_days_ago = now - timedelta(days=30)
    seven_days_ago = now - timedelta(days=7)

    # User stats
    total_users = User.objects.count()
    new_users_month = User.objects.filter(created_at__gte=thirty_days_ago).count()
    new_users_week = User.objects.filter(created_at__gte=seven_days_ago).count()
    active_users = User.objects.filter(
        predictions__created_at__gte=seven_days_ago
    ).distinct().count()

    # Plan breakdown
    plan_counts = {
        'free': User.objects.filter(plan='free').count(),
        'basic': User.objects.filter(plan='basic').count(),
        'pro': User.objects.filter(plan='pro').count(),
    }

    # Revenue stats
    total_revenue = Payment.objects.filter(status='success').aggregate(
        total=Sum('amount')
    )['total'] or 0
    revenue_month = Payment.objects.filter(
        status='success', verified_at__gte=thirty_days_ago
    ).aggregate(total=Sum('amount'))['total'] or 0

    # Prediction stats
    total_predictions = Prediction.objects.count()
    predictions_week = Prediction.objects.filter(created_at__gte=seven_days_ago).count()
    correct_preds = Prediction.objects.filter(was_correct=True).count()
    total_verified = Prediction.objects.filter(was_correct__isnull=False).count()
    avg_accuracy = round(correct_preds / total_verified * 100, 1) if total_verified else 0

    # Recent transactions
    recent_payments = Payment.objects.filter(
        status='success'
    ).select_related('user').order_by('-verified_at')[:5]

    # Recent admin logs
    recent_logs = AdminLog.objects.select_related('admin').order_by('-created_at')[:5]

    # Tips count
    total_tips = WeeklyTipAdmin.objects.count()
    published_tips = WeeklyTipAdmin.objects.filter(is_published=True).count()

    context = {
        'total_users': total_users,
        'new_users_month': new_users_month,
        'new_users_week': new_users_week,
        'active_users': active_users,
        'plan_counts': plan_counts,
        'total_revenue': total_revenue,
        'revenue_month': revenue_month,
        'total_predictions': total_predictions,
        'predictions_week': predictions_week,
        'avg_accuracy': avg_accuracy,
        'recent_payments': recent_payments,
        'recent_logs': recent_logs,
        'total_tips': total_tips,
        'published_tips': published_tips,
    }
    return render(request, 'panel/admin_dashboard.html', context)


# ─── User Management ──────────────────────────────────────────────────────────

@admin_required
def user_list(request):
    qs = User.objects.all().order_by('-date_joined')

    # Search
    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(Q(email__icontains=q) | Q(first_name__icontains=q) | Q(username__icontains=q))

    # Filter by plan
    plan_filter = request.GET.get('plan', '')
    if plan_filter:
        qs = qs.filter(plan=plan_filter)

    # Filter by status
    status_filter = request.GET.get('status', '')
    if status_filter == 'active':
        qs = qs.filter(is_active=True)
    elif status_filter == 'inactive':
        qs = qs.filter(is_active=False)

    # Annotate with prediction count
    qs = qs.annotate(pred_count=Count('predictions'))

    context = {
        'users': qs,
        'q': q,
        'plan_filter': plan_filter,
        'status_filter': status_filter,
        'total_count': qs.count(),
    }
    return render(request, 'panel/user_management.html', context)


@admin_required
def user_detail(request, user_id):
    target_user = get_object_or_404(User, pk=user_id)
    payments = Payment.objects.filter(user=target_user).order_by('-created_at')[:10]
    predictions = Prediction.objects.filter(user=target_user).order_by('-created_at')[:10]
    context = {
        'target_user': target_user,
        'payments': payments,
        'predictions': predictions,
    }
    return render(request, 'panel/user_detail.html', context)


@admin_required
def toggle_user_status(request, user_id):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST only'}, status=405)
    target_user = get_object_or_404(User, pk=user_id)
    if target_user == request.user:
        return JsonResponse({'error': 'Cannot deactivate yourself'}, status=400)
    target_user.is_active = not target_user.is_active
    target_user.save(update_fields=['is_active'])
    action = 'activate' if target_user.is_active else 'deactivate'
    log_action(
        request, action, 'User', target_user.pk,
        target_user.email,
        f"User {'activated' if target_user.is_active else 'deactivated'}"
    )
    status_label = 'activated' if target_user.is_active else 'deactivated'
    messages.success(request, f'User {target_user.email} has been {status_label}.')
    return redirect('admin_users')


@admin_required
def change_user_plan(request, user_id):
    if request.method != 'POST':
        return redirect('admin_users')
    target_user = get_object_or_404(User, pk=user_id)
    new_plan = request.POST.get('plan', 'free')
    if new_plan not in ['free', 'basic', 'pro']:
        messages.error(request, 'Invalid plan.')
        return redirect('admin_users')
    old_plan = target_user.plan
    target_user.plan = new_plan
    if new_plan != 'free':
        from datetime import timedelta
        from django.conf import settings
        days = settings.MATCHORACLE['PLANS'][new_plan]['duration_days']
        target_user.subscription_start = timezone.now()
        target_user.subscription_end = timezone.now() + timedelta(days=days)
    else:
        target_user.subscription_end = None
    target_user.save()
    log_action(
        request, 'update', 'User', target_user.pk,
        target_user.email,
        f"Plan changed from {old_plan} to {new_plan}"
    )
    messages.success(request, f"Plan updated to {new_plan.title()} for {target_user.email}.")
    return redirect('admin_users')


# ─── Weekly Tips Management ───────────────────────────────────────────────────

@admin_required
def tips_list(request):
    tips = WeeklyTipAdmin.objects.select_related('created_by').all()
    return render(request, 'panel/tips_management.html', {'tips': tips})


@admin_required
def tip_create(request):
    if request.method == 'POST':
        try:
            from django.utils.dateparse import parse_datetime
            match_date_str = request.POST.get('match_date', '')
            match_date = parse_datetime(match_date_str) or timezone.now()

            confidence = int(request.POST.get('confidence', 70))
            tip = WeeklyTipAdmin.objects.create(
                title=request.POST.get('title', '').strip(),
                description=request.POST.get('description', '').strip(),
                home_team=request.POST.get('home_team', '').strip(),
                away_team=request.POST.get('away_team', '').strip(),
                competition=request.POST.get('competition', 'Premier League').strip(),
                match_date=match_date,
                tip=request.POST.get('tip', '').strip(),
                confidence=confidence,
                is_pro_only=request.POST.get('is_pro_only') == 'on',
                is_published=request.POST.get('is_published') == 'on',
                created_by=request.user,
            )
            log_action(request, 'create', 'WeeklyTipAdmin', tip.pk, str(tip))
            messages.success(request, f'Tip "{tip.title}" created successfully.')
            return redirect('admin_tips')
        except Exception as e:
            messages.error(request, f'Error creating tip: {e}')
    return render(request, 'panel/tip_form.html', {'action': 'Create', 'tip': None})


@admin_required
def tip_edit(request, tip_id):
    tip = get_object_or_404(WeeklyTipAdmin, pk=tip_id)
    if request.method == 'POST':
        try:
            from django.utils.dateparse import parse_datetime
            match_date_str = request.POST.get('match_date', '')
            match_date = parse_datetime(match_date_str) or tip.match_date

            tip.title = request.POST.get('title', '').strip()
            tip.description = request.POST.get('description', '').strip()
            tip.home_team = request.POST.get('home_team', '').strip()
            tip.away_team = request.POST.get('away_team', '').strip()
            tip.competition = request.POST.get('competition', 'Premier League').strip()
            tip.match_date = match_date
            tip.tip = request.POST.get('tip', '').strip()
            tip.confidence = int(request.POST.get('confidence', 70))
            tip.is_pro_only = request.POST.get('is_pro_only') == 'on'
            tip.is_published = request.POST.get('is_published') == 'on'
            tip.result = request.POST.get('result', '')
            tip.save()
            log_action(request, 'update', 'WeeklyTipAdmin', tip.pk, str(tip))
            messages.success(request, f'Tip "{tip.title}" updated successfully.')
            return redirect('admin_tips')
        except Exception as e:
            messages.error(request, f'Error updating tip: {e}')
    return render(request, 'panel/tip_form.html', {'action': 'Edit', 'tip': tip})


@admin_required
def tip_delete(request, tip_id):
    tip = get_object_or_404(WeeklyTipAdmin, pk=tip_id)
    if request.method == 'POST':
        tip_repr = str(tip)
        tip.delete()
        log_action(request, 'delete', 'WeeklyTipAdmin', tip_id, tip_repr)
        messages.success(request, 'Tip deleted successfully.')
        return redirect('admin_tips')
    return render(request, 'panel/tip_confirm_delete.html', {'tip': tip})


# ─── Revenue Dashboard ────────────────────────────────────────────────────────

@admin_required
def revenue_dashboard(request):
    now = timezone.now()
    thirty_days_ago = now - timedelta(days=30)
    ninety_days_ago = now - timedelta(days=90)

    # Overall revenue
    total_revenue = Payment.objects.filter(status='success').aggregate(
        total=Sum('amount')
    )['total'] or 0

    # MRR (last 30 days)
    mrr = Payment.objects.filter(
        status='success', verified_at__gte=thirty_days_ago
    ).aggregate(total=Sum('amount'))['total'] or 0

    # Revenue by plan
    revenue_by_plan = {}
    for plan in ['basic', 'pro']:
        revenue_by_plan[plan] = Payment.objects.filter(
            status='success', plan=plan
        ).aggregate(total=Sum('amount'))['total'] or 0

    # Subscription counts
    sub_counts = {
        'basic': User.objects.filter(plan='basic').count(),
        'pro': User.objects.filter(plan='pro').count(),
    }

    # Recent transactions
    recent_transactions = Payment.objects.filter(
        status='success'
    ).select_related('user').order_by('-verified_at')[:20]

    # Monthly revenue for last 3 months (simple breakdown)
    monthly_revenue = []
    for i in range(3):
        month_start = (now - timedelta(days=30 * (i + 1))).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        month_end = (now - timedelta(days=30 * i)).replace(
            hour=23, minute=59, second=59
        )
        rev = Payment.objects.filter(
            status='success',
            verified_at__gte=month_start,
            verified_at__lte=month_end
        ).aggregate(total=Sum('amount'))['total'] or 0
        monthly_revenue.append({
            'label': month_start.strftime('%b %Y'),
            'amount': rev,
        })
    monthly_revenue.reverse()

    # Pending payments
    pending_count = Payment.objects.filter(status='pending').count()
    failed_count = Payment.objects.filter(status='failed').count()

    context = {
        'total_revenue': total_revenue,
        'mrr': mrr,
        'revenue_by_plan': revenue_by_plan,
        'sub_counts': sub_counts,
        'recent_transactions': recent_transactions,
        'monthly_revenue': monthly_revenue,
        'pending_count': pending_count,
        'failed_count': failed_count,
    }
    return render(request, 'panel/revenue_dashboard.html', context)


# ─── Admin Logs ───────────────────────────────────────────────────────────────

@admin_required
def admin_logs(request):
    logs = AdminLog.objects.select_related('admin').all()

    # Filter by action
    action_filter = request.GET.get('action', '')
    if action_filter:
        logs = logs.filter(action=action_filter)

    # Filter by admin
    admin_filter = request.GET.get('admin', '')
    if admin_filter:
        logs = logs.filter(admin__email__icontains=admin_filter)

    context = {
        'logs': logs[:100],
        'action_filter': action_filter,
        'admin_filter': admin_filter,
        'action_choices': AdminLog.ACTION_CHOICES,
    }
    return render(request, 'panel/admin_logs.html', context)
