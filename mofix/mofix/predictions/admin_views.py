"""
Custom admin dashboard views for the MatchOracle learning system.
All views require staff membership (is_staff=True).
"""
import logging
from datetime import timedelta

from django.contrib.admin.views.decorators import staff_member_required
from django.core.paginator import Paginator
from django.db.models import Avg, Count, Q, Sum
from django.shortcuts import render
from django.utils import timezone

from .models import (
    EngineAccuracy, PatternMemory, PlayerProfile,
    Prediction, PredictionResult, TeamProfile, WeightAdjustment,
)

logger = logging.getLogger(__name__)

# ─── Helpers ──────────────────────────────────────────────────────────────────

ENGINE_LABELS = {'A': 'Match', 'B': 'Player', 'D': 'Simulation', 'NL': 'AI'}


def _safe_pct(numerator, denominator):
    """Return percentage rounded to 1 dp, or 0.0 if denominator is zero."""
    if not denominator:
        return 0.0
    return round(numerator / denominator * 100, 1)


def _engine_breakdown():
    """Return per-engine accuracy stats dict."""
    stats = {}
    for engine, label in ENGINE_LABELS.items():
        qs = PredictionResult.objects.filter(
            prediction__engine=engine,
            was_correct__isnull=False,
        )
        total = qs.count()
        correct = qs.filter(was_correct=True).count()
        stats[engine] = {
            'label':    label,
            'total':    total,
            'correct':  correct,
            'accuracy': _safe_pct(correct, total),
        }
    return stats


# ─── Dashboard home ───────────────────────────────────────────────────────────

@staff_member_required
def admin_dashboard(request):
    now = timezone.now()
    week_ago  = now - timedelta(days=7)
    month_ago = now - timedelta(days=30)

    # ── KPIs ──────────────────────────────────────────────────────────────────
    total_predictions  = Prediction.objects.count()
    verified_count     = PredictionResult.objects.filter(was_correct__isnull=False).count()
    correct_count      = PredictionResult.objects.filter(was_correct=True).count()
    overall_accuracy   = _safe_pct(correct_count, verified_count)

    week_total   = PredictionResult.objects.filter(created_at__gte=week_ago).count()
    week_correct = PredictionResult.objects.filter(created_at__gte=week_ago, was_correct=True).count()
    week_accuracy = _safe_pct(week_correct, week_total)

    month_total   = PredictionResult.objects.filter(created_at__gte=month_ago).count()
    month_correct = PredictionResult.objects.filter(created_at__gte=month_ago, was_correct=True).count()
    month_accuracy = _safe_pct(month_correct, month_total)

    # ── Engine breakdown ──────────────────────────────────────────────────────
    engine_stats = _engine_breakdown()

    # ── Recent weight adjustments ─────────────────────────────────────────────
    recent_adjustments = WeightAdjustment.objects.select_related().order_by('-applied_at')[:10]

    # ── User stats ────────────────────────────────────────────────────────────
    try:
        from accounts.models import User, Payment
        total_users  = User.objects.count()
        active_users = User.objects.filter(
            predictions__created_at__gte=week_ago
        ).distinct().count()
        total_revenue = (
            Payment.objects.filter(status='verified')
            .aggregate(total=Sum('amount'))['total'] or 0
        )
        month_revenue = (
            Payment.objects.filter(status='verified', created_at__gte=month_ago)
            .aggregate(total=Sum('amount'))['total'] or 0
        )
        plan_breakdown = (
            User.objects.values('plan')
            .annotate(count=Count('id'))
            .order_by('-count')
        )
    except Exception:
        total_users = active_users = total_revenue = month_revenue = 0
        plan_breakdown = []

    # ── Pattern stats ─────────────────────────────────────────────────────────
    total_patterns   = PatternMemory.objects.count()
    reliable_patterns = PatternMemory.objects.filter(
        occurrences__gte=5
    ).count()

    # ── Team / player counts ──────────────────────────────────────────────────
    total_teams   = TeamProfile.objects.count()
    total_players = PlayerProfile.objects.count()

    context = {
        'title': 'Learning System Dashboard',
        # KPIs
        'total_predictions':  total_predictions,
        'verified_count':     verified_count,
        'overall_accuracy':   overall_accuracy,
        'week_predictions':   week_total,
        'week_accuracy':      week_accuracy,
        'month_accuracy':     month_accuracy,
        # Engines
        'engine_stats':       engine_stats,
        # Adjustments
        'recent_adjustments': recent_adjustments,
        # Users / payments
        'total_users':        total_users,
        'active_users':       active_users,
        'total_revenue':      total_revenue,
        'month_revenue':      month_revenue,
        'plan_breakdown':     plan_breakdown,
        # Patterns / profiles
        'total_patterns':     total_patterns,
        'reliable_patterns':  reliable_patterns,
        'total_teams':        total_teams,
        'total_players':      total_players,
    }
    return render(request, 'admin/matchoracle/dashboard.html', context)


# ─── Engine performance ───────────────────────────────────────────────────────

@staff_member_required
def engine_performance(request):
    engine_accuracy = EngineAccuracy.objects.all().order_by('engine', 'match_type')

    # Build a nested dict: {engine: {match_type: EngineAccuracy}}
    by_engine = {}
    for ea in engine_accuracy:
        by_engine.setdefault(ea.engine, {})[ea.match_type] = ea

    # Recent weight adjustments per engine
    adjustments = (
        WeightAdjustment.objects
        .order_by('-applied_at')
        .values('engine', 'parameter', 'old_weight', 'new_weight', 'applied_at', 'reason')[:30]
    )

    context = {
        'title':          'Engine Performance',
        'engine_accuracy': engine_accuracy,
        'by_engine':       by_engine,
        'engine_labels':   ENGINE_LABELS,
        'adjustments':     adjustments,
        'live_stats':      _engine_breakdown(),
    }
    return render(request, 'admin/matchoracle/engine_performance.html', context)


# ─── User analytics ───────────────────────────────────────────────────────────

@staff_member_required
def user_analytics(request):
    try:
        from accounts.models import User, Payment

        now       = timezone.now()
        week_ago  = now - timedelta(days=7)
        month_ago = now - timedelta(days=30)

        users = (
            User.objects
            .annotate(pred_count=Count('predictions'))
            .order_by('-pred_count')
        )
        paginator = Paginator(users, 50)
        page_obj  = paginator.get_page(request.GET.get('page', 1))

        # Signup trend (last 30 days, grouped by day)
        signups_qs = (
            User.objects
            .filter(created_at__gte=month_ago)
            .extra(select={'day': "date(created_at)"})
            .values('day')
            .annotate(count=Count('id'))
            .order_by('day')
        )

        # Payment stats
        payments = Payment.objects.order_by('-created_at')[:50]
        revenue_by_plan = (
            Payment.objects
            .filter(status='verified')
            .values('plan')
            .annotate(total=Sum('amount'), count=Count('id'))
            .order_by('-total')
        )

        context = {
            'title':           'User Analytics',
            'page_obj':        page_obj,
            'total_users':     User.objects.count(),
            'active_users':    User.objects.filter(predictions__created_at__gte=week_ago).distinct().count(),
            'new_this_month':  User.objects.filter(created_at__gte=month_ago).count(),
            'signups_qs':      list(signups_qs),
            'payments':        payments,
            'revenue_by_plan': revenue_by_plan,
        }
    except Exception as exc:
        logger.warning('user_analytics view error: %s', exc)
        context = {'title': 'User Analytics', 'error': str(exc)}

    return render(request, 'admin/matchoracle/user_analytics.html', context)


# ─── Team profiles ────────────────────────────────────────────────────────────

@staff_member_required
def team_profiles(request):
    search = request.GET.get('q', '').strip()
    style  = request.GET.get('style', '').strip()

    qs = TeamProfile.objects.all()
    if search:
        qs = qs.filter(team_name__icontains=search)
    if style:
        qs = qs.filter(tactical_style=style)
    qs = qs.order_by('-sample_size')

    paginator = Paginator(qs, 50)
    page_obj  = paginator.get_page(request.GET.get('page', 1))

    styles = TeamProfile.objects.values_list('tactical_style', flat=True).distinct().order_by('tactical_style')

    context = {
        'title':    'Team Profiles',
        'page_obj': page_obj,
        'search':   search,
        'style':    style,
        'styles':   styles,
        'total':    TeamProfile.objects.count(),
    }
    return render(request, 'admin/matchoracle/team_profiles.html', context)


# ─── Pattern analysis ─────────────────────────────────────────────────────────

@staff_member_required
def patterns(request):
    ptype  = request.GET.get('type', '').strip()
    search = request.GET.get('q', '').strip()

    qs = PatternMemory.objects.all()
    if ptype:
        qs = qs.filter(pattern_type=ptype)
    if search:
        qs = qs.filter(pattern_key__icontains=search)
    qs = qs.order_by('-occurrences', '-accuracy')

    paginator = Paginator(qs, 50)
    page_obj  = paginator.get_page(request.GET.get('page', 1))

    # Summary stats per type
    type_stats = (
        PatternMemory.objects
        .values('pattern_type')
        .annotate(
            count=Count('id'),
            avg_accuracy=Avg('accuracy'),
            reliable=Count('id', filter=Q(occurrences__gte=5)),
        )
        .order_by('pattern_type')
    )

    context = {
        'title':      'Pattern Analysis',
        'page_obj':   page_obj,
        'ptype':      ptype,
        'search':     search,
        'type_stats': type_stats,
        'total':      PatternMemory.objects.count(),
        'reliable':   PatternMemory.objects.filter(occurrences__gte=5).count(),
        'pattern_types': PatternMemory.PATTERN_TYPE_CHOICES,
    }
    return render(request, 'admin/matchoracle/patterns.html', context)


# ─── Payment tracking ─────────────────────────────────────────────────────────

@staff_member_required
def payments(request):
    try:
        from accounts.models import Payment

        now       = timezone.now()
        month_ago = now - timedelta(days=30)

        status_filter = request.GET.get('status', '').strip()
        qs = Payment.objects.select_related('user').order_by('-created_at')
        if status_filter:
            qs = qs.filter(status=status_filter)

        paginator = Paginator(qs, 50)
        page_obj  = paginator.get_page(request.GET.get('page', 1))

        summary = (
            Payment.objects
            .values('status')
            .annotate(count=Count('id'), total=Sum('amount'))
            .order_by('status')
        )
        month_revenue = (
            Payment.objects
            .filter(status='verified', created_at__gte=month_ago)
            .aggregate(total=Sum('amount'))['total'] or 0
        )
        total_revenue = (
            Payment.objects
            .filter(status='verified')
            .aggregate(total=Sum('amount'))['total'] or 0
        )

        context = {
            'title':         'Payment Tracking',
            'page_obj':      page_obj,
            'status_filter': status_filter,
            'summary':       summary,
            'month_revenue': month_revenue,
            'total_revenue': total_revenue,
        }
    except Exception as exc:
        logger.warning('payments view error: %s', exc)
        context = {'title': 'Payment Tracking', 'error': str(exc)}

    return render(request, 'admin/matchoracle/payments.html', context)


# ─── API usage ────────────────────────────────────────────────────────────────

@staff_member_required
def api_usage(request):
    """
    Approximate API usage derived from Prediction records created via the
    API app (engine choices logged in Prediction.engine).
    """
    now       = timezone.now()
    week_ago  = now - timedelta(days=7)
    month_ago = now - timedelta(days=30)

    try:
        from accounts.models import User

        # Users with API keys who have made predictions
        api_users = (
            User.objects
            .exclude(api_key='')
            .annotate(pred_count=Count('predictions'))
            .filter(pred_count__gt=0)
            .order_by('-pred_count')[:20]
        )

        # Predictions per engine this week
        week_by_engine = (
            Prediction.objects
            .filter(created_at__gte=week_ago)
            .values('engine')
            .annotate(count=Count('id'))
            .order_by('-count')
        )

        # Daily prediction volume (last 30 days)
        daily_volume = (
            Prediction.objects
            .filter(created_at__gte=month_ago)
            .extra(select={'day': "date(created_at)"})
            .values('day')
            .annotate(count=Count('id'))
            .order_by('day')
        )

        context = {
            'title':         'API Usage',
            'api_users':     api_users,
            'week_by_engine': week_by_engine,
            'daily_volume':  list(daily_volume),
            'total_week':    Prediction.objects.filter(created_at__gte=week_ago).count(),
            'total_month':   Prediction.objects.filter(created_at__gte=month_ago).count(),
        }
    except Exception as exc:
        logger.warning('api_usage view error: %s', exc)
        context = {'title': 'API Usage', 'error': str(exc)}

    return render(request, 'admin/matchoracle/api_usage.html', context)


# ─── System health ────────────────────────────────────────────────────────────

@staff_member_required
def system_health(request):
    now = timezone.now()

    checks = []

    # 1. Database connectivity
    try:
        Prediction.objects.count()
        checks.append({'name': 'Database', 'status': 'ok', 'detail': 'PostgreSQL reachable'})
    except Exception as exc:
        checks.append({'name': 'Database', 'status': 'error', 'detail': str(exc)})

    # 2. Learning system — recent result checks
    try:
        last_result = PredictionResult.objects.order_by('-created_at').first()
        if last_result:
            age_hours = (now - last_result.created_at).total_seconds() / 3600
            status = 'ok' if age_hours < 12 else 'warn'
            detail = f'Last result check {age_hours:.1f}h ago'
        else:
            status = 'warn'
            detail = 'No results recorded yet'
        checks.append({'name': 'Result Checker', 'status': status, 'detail': detail})
    except Exception as exc:
        checks.append({'name': 'Result Checker', 'status': 'error', 'detail': str(exc)})

    # 3. Weight adjuster — last adjustment
    try:
        last_adj = WeightAdjustment.objects.order_by('-applied_at').first()
        if last_adj:
            age_days = (now - last_adj.applied_at).days
            status = 'ok' if age_days < 14 else 'warn'
            detail = f'Last adjustment {age_days}d ago ({last_adj.engine}/{last_adj.parameter})'
        else:
            status = 'warn'
            detail = 'No weight adjustments recorded yet'
        checks.append({'name': 'Weight Adjuster', 'status': status, 'detail': detail})
    except Exception as exc:
        checks.append({'name': 'Weight Adjuster', 'status': 'error', 'detail': str(exc)})

    # 4. Team profiles freshness
    try:
        stale = TeamProfile.objects.filter(
            updated_at__lt=now - timedelta(hours=48)
        ).count()
        total = TeamProfile.objects.count()
        status = 'ok' if stale == 0 else ('warn' if stale < total * 0.2 else 'error')
        detail = f'{stale}/{total} profiles stale (>48h)'
        checks.append({'name': 'Team Profiles', 'status': status, 'detail': detail})
    except Exception as exc:
        checks.append({'name': 'Team Profiles', 'status': 'error', 'detail': str(exc)})

    # 5. Pattern memory size
    try:
        pattern_count = PatternMemory.objects.count()
        reliable      = PatternMemory.objects.filter(occurrences__gte=5).count()
        status = 'ok' if pattern_count > 0 else 'warn'
        detail = f'{pattern_count} patterns ({reliable} reliable)'
        checks.append({'name': 'Pattern Memory', 'status': status, 'detail': detail})
    except Exception as exc:
        checks.append({'name': 'Pattern Memory', 'status': 'error', 'detail': str(exc)})

    # 6. Redis / Celery (best-effort)
    try:
        import redis
        from django.conf import settings
        r = redis.from_url(settings.REDIS_URL, socket_connect_timeout=2)
        r.ping()
        checks.append({'name': 'Redis / Celery', 'status': 'ok', 'detail': 'Redis reachable'})
    except Exception as exc:
        checks.append({'name': 'Redis / Celery', 'status': 'warn', 'detail': f'Redis unavailable: {exc}'})

    overall = 'ok'
    for c in checks:
        if c['status'] == 'error':
            overall = 'error'
            break
        if c['status'] == 'warn' and overall == 'ok':
            overall = 'warn'

    context = {
        'title':   'System Health',
        'checks':  checks,
        'overall': overall,
        'now':     now,
    }
    return render(request, 'admin/matchoracle/health.html', context)
