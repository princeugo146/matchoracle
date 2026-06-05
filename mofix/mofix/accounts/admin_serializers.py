"""
Admin serializers — lightweight dict-based serializers (no DRF dependency).
All serialization is done with plain Python so the admin backend works even
if djangorestframework is not installed.
"""
from datetime import timedelta

from django.utils import timezone
from django.db.models import Sum, Count, Avg, Q
from django.conf import settings


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _fmt_currency(amount, currency='NGN'):
    try:
        return f'{currency} {float(amount):,.2f}'
    except (TypeError, ValueError):
        return f'{currency} 0.00'


def _plan_badge(plan):
    badges = {'free': 'Free', 'basic': 'Basic', 'pro': 'Pro'}
    return badges.get(plan, plan.title())


# ─── User Serializer ───────────────────────────────────────────────────────────

def serialize_user(user, include_payments=False):
    """Return a JSON-safe dict for a User instance."""
    total_spent = (
        user.payments.filter(status='success')
        .aggregate(t=Sum('amount'))['t'] or 0
    )
    data = {
        'id': user.id,
        'email': user.email,
        'username': user.username,
        'first_name': user.first_name,
        'last_name': user.last_name,
        'phone': user.phone,
        'plan': user.plan,
        'plan_label': _plan_badge(user.plan),
        'is_active': user.is_active,
        'is_staff': user.is_staff,
        'is_superuser': user.is_superuser,
        'subscription_start': user.subscription_start.isoformat() if user.subscription_start else None,
        'subscription_end': user.subscription_end.isoformat() if user.subscription_end else None,
        'subscription_active': user.is_subscription_active,
        'days_remaining': user.days_remaining,
        'total_predictions': user.total_predictions,
        'correct_predictions': user.correct_predictions,
        'accuracy_rate': user.accuracy_rate,
        'predictions_today': user.predictions_today,
        'predictions_left_today': user.predictions_left_today,
        'referral_code': user.referral_code,
        'api_key': user.api_key,
        'total_spent': float(total_spent),
        'total_spent_display': _fmt_currency(total_spent),
        'date_joined': user.date_joined.isoformat(),
        'created_at': user.created_at.isoformat(),
        'last_login': user.last_login.isoformat() if user.last_login else None,
    }
    if include_payments:
        data['payments'] = [serialize_payment(p) for p in user.payments.order_by('-created_at')[:10]]
    return data


def serialize_user_list(users):
    """Serialize a queryset of users (without payment details for performance)."""
    return [serialize_user(u) for u in users]


# ─── Payment Serializer ────────────────────────────────────────────────────────

def serialize_payment(payment):
    """Return a JSON-safe dict for a Payment instance."""
    return {
        'id': payment.id,
        'user_id': payment.user_id,
        'user_email': payment.user.email,
        'plan': payment.plan,
        'plan_label': _plan_badge(payment.plan),
        'amount': float(payment.amount),
        'amount_display': _fmt_currency(payment.amount, payment.currency),
        'currency': payment.currency,
        'reference': payment.reference,
        'status': payment.status,
        'created_at': payment.created_at.isoformat(),
        'verified_at': payment.verified_at.isoformat() if payment.verified_at else None,
    }


def serialize_payment_list(payments):
    return [serialize_payment(p) for p in payments]


# ─── Revenue Serializer ────────────────────────────────────────────────────────

def serialize_revenue_stats(payments_qs, users_qs):
    """Aggregate revenue statistics from a Payment queryset."""
    from accounts.models import Payment

    success_qs = payments_qs.filter(status='success')
    stats = success_qs.aggregate(
        total_revenue=Sum('amount'),
        transaction_count=Count('id'),
    )
    total_revenue = float(stats['total_revenue'] or 0)
    transaction_count = stats['transaction_count'] or 0
    total_users = users_qs.count()
    avg_user_value = round(total_revenue / total_users, 2) if total_users else 0

    plan_breakdown = list(
        success_qs.values('plan')
        .annotate(revenue=Sum('amount'), count=Count('id'))
        .order_by('-revenue')
    )
    for row in plan_breakdown:
        row['revenue'] = float(row['revenue'])
        row['revenue_display'] = _fmt_currency(row['revenue'])
        row['plan_label'] = _plan_badge(row['plan'])

    # Monthly revenue for the last 12 months
    from django.db.models.functions import TruncMonth
    monthly = list(
        success_qs
        .annotate(month=TruncMonth('created_at'))
        .values('month')
        .annotate(revenue=Sum('amount'), count=Count('id'))
        .order_by('month')
    )
    for row in monthly:
        row['revenue'] = float(row['revenue'])
        row['month'] = row['month'].strftime('%Y-%m') if row['month'] else None

    # Plan distribution across all users
    plan_dist = list(
        users_qs.values('plan')
        .annotate(count=Count('id'))
        .order_by('-count')
    )

    return {
        'total_revenue': total_revenue,
        'total_revenue_display': _fmt_currency(total_revenue),
        'transaction_count': transaction_count,
        'total_users': total_users,
        'avg_user_value': avg_user_value,
        'avg_user_value_display': _fmt_currency(avg_user_value),
        'plan_breakdown': plan_breakdown,
        'monthly_revenue': monthly,
        'plan_distribution': plan_dist,
    }


# ─── Weekly Tip Serializer ─────────────────────────────────────────────────────

def serialize_tip(tip):
    """Return a JSON-safe dict for a WeeklyTip instance."""
    return {
        'id': tip.id,
        'home_team': tip.home_team,
        'away_team': tip.away_team,
        'competition': tip.competition,
        'match_date': tip.match_date.isoformat(),
        'tip': tip.tip,
        'confidence': tip.confidence,
        'is_pro_only': tip.is_pro_only,
        'created_at': tip.created_at.isoformat(),
    }


def serialize_tip_list(tips):
    return [serialize_tip(t) for t in tips]


# ─── Analytics Serializer ──────────────────────────────────────────────────────

def serialize_analytics(users_qs, predictions_qs):
    """Aggregate analytics data."""
    from django.db.models.functions import TruncDay, TruncMonth

    total_users = users_qs.count()
    active_users = users_qs.filter(is_active=True).count()
    paid_users = users_qs.exclude(plan='free').count()
    total_predictions = predictions_qs.count()

    # Predictions per engine
    engine_breakdown = list(
        predictions_qs.values('engine')
        .annotate(count=Count('id'))
        .order_by('-count')
    )

    # New users per day (last 30 days)
    thirty_days_ago = timezone.now() - timedelta(days=30)
    daily_signups = list(
        users_qs.filter(date_joined__gte=thirty_days_ago)
        .annotate(day=TruncDay('date_joined'))
        .values('day')
        .annotate(count=Count('id'))
        .order_by('day')
    )
    for row in daily_signups:
        row['day'] = row['day'].strftime('%Y-%m-%d') if row['day'] else None

    # Predictions per day (last 30 days)
    daily_predictions = list(
        predictions_qs.filter(created_at__gte=thirty_days_ago)
        .annotate(day=TruncDay('created_at'))
        .values('day')
        .annotate(count=Count('id'))
        .order_by('day')
    )
    for row in daily_predictions:
        row['day'] = row['day'].strftime('%Y-%m-%d') if row['day'] else None

    # Accuracy stats
    correct = predictions_qs.filter(was_correct=True).count()
    incorrect = predictions_qs.filter(was_correct=False).count()
    pending = predictions_qs.filter(was_correct__isnull=True).count()
    accuracy = round(correct / max(correct + incorrect, 1) * 100, 1)

    return {
        'total_users': total_users,
        'active_users': active_users,
        'inactive_users': total_users - active_users,
        'paid_users': paid_users,
        'free_users': total_users - paid_users,
        'conversion_rate': round(paid_users / max(total_users, 1) * 100, 1),
        'total_predictions': total_predictions,
        'correct_predictions': correct,
        'incorrect_predictions': incorrect,
        'pending_predictions': pending,
        'overall_accuracy': accuracy,
        'engine_breakdown': engine_breakdown,
        'daily_signups': daily_signups,
        'daily_predictions': daily_predictions,
    }


# ─── Weekly Forecast Serializer ────────────────────────────────────────────────

def serialize_forecast(forecast):
    return {
        'id': forecast.id,
        'home_team': forecast.home_team,
        'away_team': forecast.away_team,
        'match_date': forecast.match_date.isoformat(),
        'competition': forecast.competition,
        'home_win_pct': forecast.home_win_pct,
        'draw_pct': forecast.draw_pct,
        'away_win_pct': forecast.away_win_pct,
        'predicted_score': forecast.predicted_score,
        'confidence': forecast.confidence,
        'ai_insight': forecast.ai_insight,
        'is_published': forecast.is_published,
        'created_at': forecast.created_at.isoformat(),
    }


def serialize_forecast_list(forecasts):
    return [serialize_forecast(f) for f in forecasts]
