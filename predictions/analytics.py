"""
analytics.py
────────────
Data aggregation functions for the admin dashboard.

All functions return plain dicts/lists — no HTTP, no templates.
They are called by admin_views.py and can also be used in management
commands or Celery tasks.

Functions
---------
get_engine_performance()   — accuracy stats per engine
get_user_analytics()       — user registration, activity, plan breakdown
get_team_analytics()       — top teams by prediction volume and accuracy
get_payment_analytics()    — revenue, plan conversions, recent payments
get_api_usage()            — API call counts per user and endpoint
get_system_health()        — overall system status snapshot
"""

import logging
from datetime import timedelta
from django.utils import timezone
from django.db.models import (
    Count, Avg, Sum, Q, F, FloatField, ExpressionWrapper,
    Case, When, IntegerField, Value
)
from django.db.models.functions import TruncDate, TruncMonth

logger = logging.getLogger(__name__)


# ─── Engine Performance ───────────────────────────────────────────────────────

def get_engine_performance():
    """
    Returns accuracy and volume stats for every prediction engine.

    Shape:
        {
          'engines': [
            {
              'engine': 'A', 'label': 'Match', 'total': 120,
              'correct': 84, 'accuracy': 70.0,
              'avg_confidence': 72.3,
              'by_match_type': [{'match_type': 'league', 'accuracy': 71.2, 'sample': 80}, ...]
            }, ...
          ],
          'engine_accuracy_records': [...],   # raw EngineAccuracy rows
          'weight_adjustments': [...],        # last 20 WeightAdjustment rows
        }
    """
    from .models import Prediction, EngineAccuracy, WeightAdjustment

    ENGINE_LABELS = {'A': 'Match', 'B': 'Player', 'C': 'Ranking', 'D': 'Simulation', 'NL': 'AI'}

    engines = []
    for engine_code, label in ENGINE_LABELS.items():
        qs = Prediction.objects.filter(engine=engine_code)
        total = qs.count()
        correct = qs.filter(was_correct=True).count()
        accuracy = round(correct / total * 100, 1) if total else 0.0
        avg_conf = qs.aggregate(a=Avg('confidence'))['a'] or 0.0

        engines.append({
            'engine': engine_code,
            'label': label,
            'total': total,
            'correct': correct,
            'wrong': qs.filter(was_correct=False).count(),
            'pending': qs.filter(was_correct__isnull=True).count(),
            'accuracy': accuracy,
            'avg_confidence': round(avg_conf, 1),
        })

    ea_records = list(
        EngineAccuracy.objects.values(
            'engine', 'match_type', 'accuracy_pct',
            'home_accuracy', 'away_accuracy', 'draw_accuracy',
            'weight_adjustment', 'sample_size', 'updated_at',
        ).order_by('engine', 'match_type')
    )

    weight_log = list(
        WeightAdjustment.objects.values(
            'engine', 'parameter', 'old_weight', 'new_weight',
            'reason', 'match_type', 'accuracy_before', 'accuracy_after', 'applied_at',
        ).order_by('-applied_at')[:20]
    )

    return {
        'engines': engines,
        'engine_accuracy_records': ea_records,
        'weight_adjustments': weight_log,
    }


# ─── User Analytics ───────────────────────────────────────────────────────────

def get_user_analytics():
    """
    Returns user registration trends, plan breakdown, and top users.

    Shape:
        {
          'totals': {'total': int, 'free': int, 'basic': int, 'pro': int, 'active_today': int},
          'registrations_last_30': [{'date': date, 'count': int}, ...],
          'plan_breakdown': [{'plan': str, 'count': int, 'pct': float}, ...],
          'top_users': [{'email': str, 'plan': str, 'total_predictions': int, 'accuracy_rate': float}, ...],
          'recent_signups': [{'email': str, 'plan': str, 'created_at': datetime}, ...],
        }
    """
    from accounts.models import User

    now = timezone.now()
    today = now.date()
    thirty_days_ago = now - timedelta(days=30)

    total = User.objects.count()
    plan_counts = {
        row['plan']: row['cnt']
        for row in User.objects.values('plan').annotate(cnt=Count('id'))
    }

    active_today = User.objects.filter(predictions_date=today).count()

    # Daily registrations for the last 30 days
    reg_qs = (
        User.objects
        .filter(created_at__gte=thirty_days_ago)
        .annotate(date=TruncDate('created_at'))
        .values('date')
        .annotate(count=Count('id'))
        .order_by('date')
    )
    registrations_last_30 = [
        {'date': row['date'], 'count': row['count']} for row in reg_qs
    ]

    # Plan breakdown with percentages
    plan_breakdown = []
    for plan, cnt in plan_counts.items():
        plan_breakdown.append({
            'plan': plan,
            'count': cnt,
            'pct': round(cnt / total * 100, 1) if total else 0.0,
        })
    plan_breakdown.sort(key=lambda x: x['count'], reverse=True)

    # Top 20 users by prediction volume
    top_users = list(
        User.objects
        .filter(total_predictions__gt=0)
        .order_by('-total_predictions')
        .values('email', 'plan', 'total_predictions', 'correct_predictions', 'created_at')[:20]
    )
    for u in top_users:
        tp = u['total_predictions'] or 0
        cp = u['correct_predictions'] or 0
        u['accuracy_rate'] = round(cp / tp * 100, 1) if tp else 0.0

    recent_signups = list(
        User.objects
        .order_by('-created_at')
        .values('email', 'plan', 'created_at', 'total_predictions')[:15]
    )

    return {
        'totals': {
            'total': total,
            'free': plan_counts.get('free', 0),
            'basic': plan_counts.get('basic', 0),
            'pro': plan_counts.get('pro', 0),
            'active_today': active_today,
        },
        'registrations_last_30': registrations_last_30,
        'plan_breakdown': plan_breakdown,
        'top_users': top_users,
        'recent_signups': recent_signups,
    }


# ─── Team Analytics ───────────────────────────────────────────────────────────

def get_team_analytics():
    """
    Returns team profile stats and prediction accuracy per team.

    Shape:
        {
          'team_profiles': [TeamProfile dicts, ...],
          'top_predicted_teams': [{'team': str, 'count': int}, ...],
          'pattern_summary': {'total': int, 'reliable': int, 'by_type': [...]},
          'player_profiles': [PlayerProfile dicts, ...],
        }
    """
    from .models import TeamProfile, PatternMemory, PlayerProfile, Prediction

    team_profiles = list(
        TeamProfile.objects
        .values(
            'team_name', 'avg_goals_scored', 'avg_goals_conceded',
            'tactical_style', 'home_accuracy', 'away_accuracy',
            'sample_size', 'updated_at',
        )
        .order_by('-sample_size')[:50]
    )

    # Most predicted home teams
    home_teams = (
        Prediction.objects
        .exclude(home_team='')
        .values('home_team')
        .annotate(count=Count('id'))
        .order_by('-count')[:20]
    )
    top_predicted = [{'team': r['home_team'], 'count': r['count']} for r in home_teams]

    # Pattern memory summary
    total_patterns = PatternMemory.objects.count()
    reliable_patterns = PatternMemory.objects.filter(
        occurrences__gte=F('min_sample')
    ).count()
    by_type = list(
        PatternMemory.objects
        .values('pattern_type')
        .annotate(count=Count('id'), avg_accuracy=Avg('accuracy'))
        .order_by('-count')
    )

    player_profiles = list(
        PlayerProfile.objects
        .values(
            'name', 'team', 'position', 'overall_rating',
            'injury_status', 'goals_this_season', 'assists_this_season',
            'appearances_this_season', 'prediction_impact', 'updated_at',
        )
        .order_by('-overall_rating')[:50]
    )

    return {
        'team_profiles': team_profiles,
        'top_predicted_teams': top_predicted,
        'pattern_summary': {
            'total': total_patterns,
            'reliable': reliable_patterns,
            'by_type': [
                {
                    'type': r['pattern_type'],
                    'count': r['count'],
                    'avg_accuracy': round(r['avg_accuracy'] or 0, 1),
                }
                for r in by_type
            ],
        },
        'player_profiles': player_profiles,
    }


# ─── Payment Analytics ────────────────────────────────────────────────────────

def get_payment_analytics():
    """
    Returns revenue totals, plan conversion stats, and recent payments.

    Shape:
        {
          'totals': {'total_revenue': Decimal, 'verified_revenue': Decimal,
                     'total_payments': int, 'verified_payments': int},
          'by_plan': [{'plan': str, 'count': int, 'revenue': Decimal}, ...],
          'by_currency': [{'currency': str, 'revenue': Decimal}, ...],
          'monthly_revenue': [{'month': date, 'revenue': Decimal, 'count': int}, ...],
          'recent_payments': [payment dicts, ...],
          'status_breakdown': [{'status': str, 'count': int}, ...],
        }
    """
    from accounts.models import Payment

    total_payments = Payment.objects.count()
    verified_payments = Payment.objects.filter(status='success').count()
    total_revenue = Payment.objects.filter(status='success').aggregate(
        s=Sum('amount')
    )['s'] or 0
    all_revenue = Payment.objects.aggregate(s=Sum('amount'))['s'] or 0

    by_plan = list(
        Payment.objects
        .filter(status='success')
        .values('plan')
        .annotate(count=Count('id'), revenue=Sum('amount'))
        .order_by('-revenue')
    )

    by_currency = list(
        Payment.objects
        .filter(status='success')
        .values('currency')
        .annotate(revenue=Sum('amount'), count=Count('id'))
        .order_by('-revenue')
    )

    # Monthly revenue for the last 12 months
    twelve_months_ago = timezone.now() - timedelta(days=365)
    monthly_revenue = list(
        Payment.objects
        .filter(status='success', created_at__gte=twelve_months_ago)
        .annotate(month=TruncMonth('created_at'))
        .values('month')
        .annotate(revenue=Sum('amount'), count=Count('id'))
        .order_by('month')
    )

    recent_payments = list(
        Payment.objects
        .select_related('user')
        .order_by('-created_at')
        .values(
            'id', 'user__email', 'plan', 'amount', 'currency',
            'status', 'reference', 'created_at', 'verified_at',
        )[:25]
    )

    status_breakdown = list(
        Payment.objects
        .values('status')
        .annotate(count=Count('id'))
        .order_by('-count')
    )

    return {
        'totals': {
            'total_revenue': total_revenue,
            'all_revenue': all_revenue,
            'total_payments': total_payments,
            'verified_payments': verified_payments,
            'conversion_rate': round(verified_payments / total_payments * 100, 1) if total_payments else 0.0,
        },
        'by_plan': by_plan,
        'by_currency': by_currency,
        'monthly_revenue': monthly_revenue,
        'recent_payments': recent_payments,
        'status_breakdown': status_breakdown,
    }


# ─── API Usage ────────────────────────────────────────────────────────────────

def get_api_usage():
    """
    Returns API usage stats derived from Prediction records created via
    the API (engine A/B/D only, no NL, filtered by users with api_access plans).

    Shape:
        {
          'totals': {'total_api_calls': int, 'api_users': int},
          'by_engine': [{'engine': str, 'count': int}, ...],
          'top_api_users': [{'email': str, 'plan': str, 'calls': int}, ...],
          'daily_calls_last_30': [{'date': date, 'count': int}, ...],
          'active_api_keys': int,
        }
    """
    from .models import Prediction
    from accounts.models import User

    now = timezone.now()
    thirty_days_ago = now - timedelta(days=30)

    # Users on plans with API access
    api_users = User.objects.filter(plan__in=['basic', 'pro'])
    api_user_ids = list(api_users.values_list('id', flat=True))

    total_api_calls = Prediction.objects.filter(user_id__in=api_user_ids).count()

    by_engine = list(
        Prediction.objects
        .filter(user_id__in=api_user_ids)
        .values('engine')
        .annotate(count=Count('id'))
        .order_by('-count')
    )

    top_api_users = list(
        Prediction.objects
        .filter(user_id__in=api_user_ids)
        .values('user__email', 'user__plan')
        .annotate(calls=Count('id'))
        .order_by('-calls')[:20]
    )

    daily_calls = list(
        Prediction.objects
        .filter(user_id__in=api_user_ids, created_at__gte=thirty_days_ago)
        .annotate(date=TruncDate('created_at'))
        .values('date')
        .annotate(count=Count('id'))
        .order_by('date')
    )

    active_api_keys = User.objects.filter(
        plan__in=['basic', 'pro'],
        api_key__gt='',
    ).count()

    return {
        'totals': {
            'total_api_calls': total_api_calls,
            'api_users': api_users.count(),
            'active_api_keys': active_api_keys,
        },
        'by_engine': by_engine,
        'top_api_users': top_api_users,
        'daily_calls_last_30': daily_calls,
    }


# ─── System Health ────────────────────────────────────────────────────────────

def get_system_health():
    """
    Returns a snapshot of overall system health.

    Shape:
        {
          'predictions': {'total': int, 'today': int, 'last_7_days': int},
          'users': {'total': int, 'active_today': int},
          'learning': {'team_profiles': int, 'patterns': int, 'engine_records': int,
                       'pending_results': int, 'weight_adjustments': int},
          'payments': {'pending': int, 'verified_today': int},
          'conversation_memory': {'active_sessions': int},
          'status': 'healthy' | 'degraded' | 'warning',
          'checks': [{'name': str, 'status': str, 'value': str}, ...],
        }
    """
    from .models import (
        Prediction, TeamProfile, PatternMemory, EngineAccuracy,
        WeightAdjustment, ConversationMemory, PredictionResult,
    )
    from accounts.models import User, Payment

    now = timezone.now()
    today = now.date()
    seven_days_ago = now - timedelta(days=7)

    total_predictions = Prediction.objects.count()
    predictions_today = Prediction.objects.filter(
        created_at__date=today
    ).count()
    predictions_7d = Prediction.objects.filter(
        created_at__gte=seven_days_ago
    ).count()

    total_users = User.objects.count()
    active_today = User.objects.filter(predictions_date=today).count()

    team_profiles = TeamProfile.objects.count()
    stale_profiles = TeamProfile.objects.filter(
        updated_at__lt=now - timedelta(hours=48)
    ).count()
    patterns = PatternMemory.objects.count()
    engine_records = EngineAccuracy.objects.count()
    pending_results = Prediction.objects.filter(
        was_correct__isnull=True,
        engine__in=['A', 'NL'],
        home_team__gt='',
        created_at__lt=now - timedelta(days=2),
    ).count()
    weight_adjustments = WeightAdjustment.objects.count()

    pending_payments = Payment.objects.filter(status='pending').count()
    verified_today = Payment.objects.filter(
        status='success', verified_at__date=today
    ).count()

    active_sessions = ConversationMemory.objects.filter(
        expires_at__gt=now
    ).count()

    # Build health checks
    checks = []

    # Prediction volume check
    if predictions_today == 0 and total_users > 5:
        checks.append({'name': 'Prediction Volume', 'status': 'warning', 'value': '0 predictions today'})
    else:
        checks.append({'name': 'Prediction Volume', 'status': 'ok', 'value': f'{predictions_today} today'})

    # Stale team profiles
    if stale_profiles > 10:
        checks.append({'name': 'Team Profiles', 'status': 'warning', 'value': f'{stale_profiles} stale profiles'})
    else:
        checks.append({'name': 'Team Profiles', 'status': 'ok', 'value': f'{team_profiles} profiles, {stale_profiles} stale'})

    # Pending result checks
    if pending_results > 50:
        checks.append({'name': 'Result Checking', 'status': 'warning', 'value': f'{pending_results} unverified predictions'})
    else:
        checks.append({'name': 'Result Checking', 'status': 'ok', 'value': f'{pending_results} pending'})

    # Pending payments
    if pending_payments > 20:
        checks.append({'name': 'Payments', 'status': 'warning', 'value': f'{pending_payments} stuck pending'})
    else:
        checks.append({'name': 'Payments', 'status': 'ok', 'value': f'{pending_payments} pending'})

    # Engine accuracy records
    if engine_records == 0:
        checks.append({'name': 'Engine Accuracy', 'status': 'warning', 'value': 'No accuracy records yet'})
    else:
        checks.append({'name': 'Engine Accuracy', 'status': 'ok', 'value': f'{engine_records} records'})

    # Overall status
    warning_count = sum(1 for c in checks if c['status'] == 'warning')
    if warning_count == 0:
        overall_status = 'healthy'
    elif warning_count <= 2:
        overall_status = 'warning'
    else:
        overall_status = 'degraded'

    return {
        'predictions': {
            'total': total_predictions,
            'today': predictions_today,
            'last_7_days': predictions_7d,
        },
        'users': {
            'total': total_users,
            'active_today': active_today,
        },
        'learning': {
            'team_profiles': team_profiles,
            'stale_profiles': stale_profiles,
            'patterns': patterns,
            'engine_records': engine_records,
            'pending_results': pending_results,
            'weight_adjustments': weight_adjustments,
        },
        'payments': {
            'pending': pending_payments,
            'verified_today': verified_today,
        },
        'conversation_memory': {
            'active_sessions': active_sessions,
        },
        'status': overall_status,
        'checks': checks,
    }
