"""
Admin backend views for MatchOracle.

All endpoints require the requesting user to be authenticated AND a superuser.
Responses are JSON so the admin frontend (or any HTTP client) can consume them.

URL prefix: /admin-api/
"""
import json
import logging
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q, Sum, Count
from django.http import JsonResponse
from datetime import timedelta

from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .models import User, Payment
from .admin_serializers import (
    serialize_user,
    serialize_user_list,
    serialize_payment,
    serialize_payment_list,
    serialize_revenue_stats,
    serialize_tip,
    serialize_tip_list,
    serialize_analytics,
    serialize_forecast,
    serialize_forecast_list,
)

logger = logging.getLogger(__name__)


# ─── Permission Decorator ──────────────────────────────────────────────────────

def superuser_required(view_func):
    """
    Decorator that enforces superuser access.
    Returns 401 if not authenticated, 403 if not a superuser.
    """
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({'error': 'Authentication required.'}, status=401)
        if not request.user.is_superuser:
            return JsonResponse({'error': 'Superuser access required.'}, status=403)
        return view_func(request, *args, **kwargs)
    return _wrapped


def _json_body(request):
    """Parse JSON request body; return empty dict on failure."""
    try:
        return json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return {}


def _ok(data=None, **kwargs):
    payload = {'success': True}
    if data is not None:
        payload['data'] = data
    payload.update(kwargs)
    return JsonResponse(payload)


def _err(message, status=400):
    return JsonResponse({'success': False, 'error': message}, status=status)


# ─── Dashboard Overview ────────────────────────────────────────────────────────

@superuser_required
def admin_overview(request):
    """
    GET /admin-api/
    High-level dashboard stats: users, revenue, predictions, tips.
    """
    from predictions.models import Prediction, WeeklyTip

    users_qs = User.objects.all()
    payments_qs = Payment.objects.all()
    predictions_qs = Prediction.objects.all()

    total_revenue = float(
        payments_qs.filter(status='success').aggregate(t=Sum('amount'))['t'] or 0
    )
    total_users = users_qs.count()
    paid_users = users_qs.exclude(plan='free').count()
    total_predictions = predictions_qs.count()
    total_tips = WeeklyTip.objects.count()

    # Recent activity (last 7 days)
    seven_days_ago = timezone.now() - timedelta(days=7)
    new_users_week = users_qs.filter(date_joined__gte=seven_days_ago).count()
    new_payments_week = payments_qs.filter(
        status='success', created_at__gte=seven_days_ago
    ).count()
    revenue_week = float(
        payments_qs.filter(status='success', created_at__gte=seven_days_ago)
        .aggregate(t=Sum('amount'))['t'] or 0
    )

    return _ok({
        'total_users': total_users,
        'paid_users': paid_users,
        'free_users': total_users - paid_users,
        'total_revenue': total_revenue,
        'total_revenue_display': f'NGN {total_revenue:,.2f}',
        'total_predictions': total_predictions,
        'total_tips': total_tips,
        'last_7_days': {
            'new_users': new_users_week,
            'new_payments': new_payments_week,
            'revenue': revenue_week,
            'revenue_display': f'NGN {revenue_week:,.2f}',
        },
    })


# ─── User Management ───────────────────────────────────────────────────────────

@superuser_required
def admin_users_list(request):
    """
    GET /admin-api/users/
    Query params:
      - page (int, default 1)
      - per_page (int, default 25, max 100)
      - search (str) — filters email, username, first_name
      - plan (str) — free | basic | pro
      - is_active (bool str) — true | false
      - ordering (str) — date_joined | -date_joined | email | plan | total_predictions
    """
    qs = User.objects.all()

    # Search
    search = request.GET.get('search', '').strip()
    if search:
        qs = qs.filter(
            Q(email__icontains=search) |
            Q(username__icontains=search) |
            Q(first_name__icontains=search) |
            Q(last_name__icontains=search)
        )

    # Plan filter
    plan = request.GET.get('plan', '').strip()
    if plan in ('free', 'basic', 'pro'):
        qs = qs.filter(plan=plan)

    # Active filter
    is_active = request.GET.get('is_active', '').strip().lower()
    if is_active == 'true':
        qs = qs.filter(is_active=True)
    elif is_active == 'false':
        qs = qs.filter(is_active=False)

    # Ordering
    ordering = request.GET.get('ordering', '-date_joined')
    allowed_orderings = [
        'date_joined', '-date_joined', 'email', '-email',
        'plan', '-plan', 'total_predictions', '-total_predictions',
    ]
    if ordering not in allowed_orderings:
        ordering = '-date_joined'
    qs = qs.order_by(ordering)

    # Pagination
    try:
        per_page = min(int(request.GET.get('per_page', 25)), 100)
        page = int(request.GET.get('page', 1))
    except (ValueError, TypeError):
        per_page, page = 25, 1

    paginator = Paginator(qs, per_page)
    page_obj = paginator.get_page(page)

    return _ok(
        serialize_user_list(page_obj.object_list),
        pagination={
            'page': page_obj.number,
            'per_page': per_page,
            'total': paginator.count,
            'total_pages': paginator.num_pages,
            'has_next': page_obj.has_next(),
            'has_previous': page_obj.has_previous(),
        },
    )


@superuser_required
def admin_user_detail(request, user_id):
    """
    GET  /admin-api/users/<user_id>/  — retrieve user detail with payments
    PATCH /admin-api/users/<user_id>/ — update user fields
    """
    try:
        user = User.objects.get(pk=user_id)
    except User.DoesNotExist:
        return _err('User not found.', status=404)

    if request.method == 'GET':
        return _ok(serialize_user(user, include_payments=True))

    if request.method == 'PATCH':
        data = _json_body(request)
        allowed_fields = {
            'first_name', 'last_name', 'phone', 'plan',
            'is_active', 'subscription_start', 'subscription_end',
        }
        updated = []
        for field, value in data.items():
            if field not in allowed_fields:
                continue
            if field == 'plan' and value not in ('free', 'basic', 'pro'):
                return _err(f'Invalid plan: {value}')
            if field in ('subscription_start', 'subscription_end') and value:
                from django.utils.dateparse import parse_datetime
                value = parse_datetime(value)
                if value is None:
                    return _err(f'Invalid datetime for {field}')
            setattr(user, field, value)
            updated.append(field)

        if updated:
            user.save(update_fields=updated)
            logger.info(
                f'Admin {request.user.email} updated user {user.email}: {updated}'
            )

        return _ok(serialize_user(user, include_payments=True))

    return _err('Method not allowed.', status=405)


@superuser_required
@require_http_methods(['POST'])
def admin_user_action(request, user_id):
    """
    POST /admin-api/users/<user_id>/action/
    Body: {"action": "activate" | "deactivate" | "reset_plan" | "change_plan", "plan": "basic"}
    """
    try:
        user = User.objects.get(pk=user_id)
    except User.DoesNotExist:
        return _err('User not found.', status=404)

    data = _json_body(request)
    action = data.get('action', '').strip()

    if action == 'activate':
        user.is_active = True
        user.save(update_fields=['is_active'])
        msg = f'User {user.email} activated.'

    elif action == 'deactivate':
        if user.is_superuser:
            return _err('Cannot deactivate a superuser.')
        user.is_active = False
        user.save(update_fields=['is_active'])
        msg = f'User {user.email} deactivated.'

    elif action == 'reset_plan':
        user.plan = 'free'
        user.subscription_start = None
        user.subscription_end = None
        user.save(update_fields=['plan', 'subscription_start', 'subscription_end'])
        msg = f'User {user.email} reset to Free plan.'

    elif action == 'change_plan':
        new_plan = data.get('plan', '').strip()
        if new_plan not in ('free', 'basic', 'pro'):
            return _err('Invalid plan. Choose: free, basic, pro.')
        from django.conf import settings
        user.plan = new_plan
        if new_plan != 'free':
            duration = settings.MATCHORACLE['PLANS'][new_plan]['duration_days']
            user.subscription_start = timezone.now()
            user.subscription_end = timezone.now() + timedelta(days=duration)
        else:
            user.subscription_start = None
            user.subscription_end = None
        user.save(update_fields=['plan', 'subscription_start', 'subscription_end'])
        msg = f'User {user.email} plan changed to {new_plan}.'

    else:
        return _err(f'Unknown action: {action}')

    logger.info(f'Admin {request.user.email} performed action "{action}" on user {user.email}')
    return _ok({'message': msg, 'user': serialize_user(user)})


# ─── Revenue Dashboard ─────────────────────────────────────────────────────────

@superuser_required
def admin_revenue(request):
    """
    GET /admin-api/revenue/
    Query params:
      - plan (str) — filter by plan
      - status (str) — filter by payment status (success | pending | failed)
      - from_date (YYYY-MM-DD)
      - to_date (YYYY-MM-DD)
      - page (int)
      - per_page (int, max 100)
    """
    payments_qs = Payment.objects.select_related('user').all()
    users_qs = User.objects.all()

    # Filters
    plan = request.GET.get('plan', '').strip()
    if plan:
        payments_qs = payments_qs.filter(plan=plan)

    status = request.GET.get('status', '').strip()
    if status:
        payments_qs = payments_qs.filter(status=status)

    from_date = request.GET.get('from_date', '').strip()
    to_date = request.GET.get('to_date', '').strip()
    if from_date:
        payments_qs = payments_qs.filter(created_at__date__gte=from_date)
    if to_date:
        payments_qs = payments_qs.filter(created_at__date__lte=to_date)

    # Stats (always computed on the full filtered set, before pagination)
    stats = serialize_revenue_stats(payments_qs, users_qs)

    # Paginated transaction list
    try:
        per_page = min(int(request.GET.get('per_page', 25)), 100)
        page = int(request.GET.get('page', 1))
    except (ValueError, TypeError):
        per_page, page = 25, 1

    payments_qs = payments_qs.order_by('-created_at')
    paginator = Paginator(payments_qs, per_page)
    page_obj = paginator.get_page(page)

    return _ok({
        'stats': stats,
        'transactions': serialize_payment_list(page_obj.object_list),
        'pagination': {
            'page': page_obj.number,
            'per_page': per_page,
            'total': paginator.count,
            'total_pages': paginator.num_pages,
            'has_next': page_obj.has_next(),
            'has_previous': page_obj.has_previous(),
        },
    })


# ─── Weekly Tips Management ────────────────────────────────────────────────────

@superuser_required
def admin_tips_list(request):
    """
    GET  /admin-api/tips/  — list all tips (paginated)
    POST /admin-api/tips/  — create a new tip
    """
    from predictions.models import WeeklyTip

    if request.method == 'GET':
        qs = WeeklyTip.objects.all()

        # Filters
        is_pro = request.GET.get('is_pro_only', '').strip().lower()
        if is_pro == 'true':
            qs = qs.filter(is_pro_only=True)
        elif is_pro == 'false':
            qs = qs.filter(is_pro_only=False)

        search = request.GET.get('search', '').strip()
        if search:
            qs = qs.filter(
                Q(home_team__icontains=search) |
                Q(away_team__icontains=search) |
                Q(competition__icontains=search) |
                Q(tip__icontains=search)
            )

        try:
            per_page = min(int(request.GET.get('per_page', 25)), 100)
            page = int(request.GET.get('page', 1))
        except (ValueError, TypeError):
            per_page, page = 25, 1

        paginator = Paginator(qs, per_page)
        page_obj = paginator.get_page(page)

        return _ok(
            serialize_tip_list(page_obj.object_list),
            pagination={
                'page': page_obj.number,
                'per_page': per_page,
                'total': paginator.count,
                'total_pages': paginator.num_pages,
            },
        )

    if request.method == 'POST':
        data = _json_body(request)
        required = ['home_team', 'away_team', 'competition', 'match_date', 'tip']
        for field in required:
            if not data.get(field):
                return _err(f'Field "{field}" is required.')

        from django.utils.dateparse import parse_datetime
        match_date = parse_datetime(data['match_date'])
        if match_date is None:
            return _err('Invalid match_date. Use ISO 8601 format (e.g. 2025-06-15T15:00:00).')

        try:
            confidence = int(data.get('confidence', 70))
            confidence = max(0, min(100, confidence))
        except (ValueError, TypeError):
            confidence = 70

        tip = WeeklyTip.objects.create(
            home_team=data['home_team'].strip(),
            away_team=data['away_team'].strip(),
            competition=data['competition'].strip(),
            match_date=match_date,
            tip=data['tip'].strip(),
            confidence=confidence,
            is_pro_only=bool(data.get('is_pro_only', False)),
        )
        logger.info(f'Admin {request.user.email} created tip #{tip.id}: {tip}')
        return _ok(serialize_tip(tip))

    return _err('Method not allowed.', status=405)


@superuser_required
def admin_tip_detail(request, tip_id):
    """
    GET    /admin-api/tips/<tip_id>/  — retrieve tip
    PATCH  /admin-api/tips/<tip_id>/  — update tip
    DELETE /admin-api/tips/<tip_id>/  — delete tip
    """
    from predictions.models import WeeklyTip

    try:
        tip = WeeklyTip.objects.get(pk=tip_id)
    except WeeklyTip.DoesNotExist:
        return _err('Tip not found.', status=404)

    if request.method == 'GET':
        return _ok(serialize_tip(tip))

    if request.method in ('PATCH', 'PUT'):
        data = _json_body(request)
        allowed = {
            'home_team', 'away_team', 'competition', 'match_date',
            'tip', 'confidence', 'is_pro_only',
        }
        updated = []
        for field, value in data.items():
            if field not in allowed:
                continue
            if field == 'match_date':
                from django.utils.dateparse import parse_datetime
                value = parse_datetime(value)
                if value is None:
                    return _err('Invalid match_date format.')
            if field == 'confidence':
                try:
                    value = max(0, min(100, int(value)))
                except (ValueError, TypeError):
                    continue
            setattr(tip, field, value)
            updated.append(field)
        if updated:
            tip.save(update_fields=updated)
            logger.info(f'Admin {request.user.email} updated tip #{tip.id}: {updated}')
        return _ok(serialize_tip(tip))

    if request.method == 'DELETE':
        tip_repr = str(tip)
        tip.delete()
        logger.info(f'Admin {request.user.email} deleted tip: {tip_repr}')
        return _ok({'message': f'Tip "{tip_repr}" deleted.'})

    return _err('Method not allowed.', status=405)


# ─── Weekly Forecasts Management ───────────────────────────────────────────────

@superuser_required
def admin_forecasts_list(request):
    """
    GET  /admin-api/forecasts/  — list all weekly forecasts
    POST /admin-api/forecasts/  — create a new forecast
    """
    from core.models import WeeklyForecast

    if request.method == 'GET':
        qs = WeeklyForecast.objects.all()

        is_published = request.GET.get('is_published', '').strip().lower()
        if is_published == 'true':
            qs = qs.filter(is_published=True)
        elif is_published == 'false':
            qs = qs.filter(is_published=False)

        search = request.GET.get('search', '').strip()
        if search:
            qs = qs.filter(
                Q(home_team__icontains=search) |
                Q(away_team__icontains=search) |
                Q(competition__icontains=search)
            )

        try:
            per_page = min(int(request.GET.get('per_page', 25)), 100)
            page = int(request.GET.get('page', 1))
        except (ValueError, TypeError):
            per_page, page = 25, 1

        paginator = Paginator(qs, per_page)
        page_obj = paginator.get_page(page)

        return _ok(
            serialize_forecast_list(page_obj.object_list),
            pagination={
                'page': page_obj.number,
                'per_page': per_page,
                'total': paginator.count,
                'total_pages': paginator.num_pages,
            },
        )

    if request.method == 'POST':
        data = _json_body(request)
        required = ['home_team', 'away_team', 'match_date']
        for field in required:
            if not data.get(field):
                return _err(f'Field "{field}" is required.')

        from django.utils.dateparse import parse_datetime
        match_date = parse_datetime(data['match_date'])
        if match_date is None:
            return _err('Invalid match_date. Use ISO 8601 format.')

        forecast = WeeklyForecast.objects.create(
            home_team=data['home_team'].strip(),
            away_team=data['away_team'].strip(),
            match_date=match_date,
            competition=data.get('competition', 'Premier League').strip(),
            home_win_pct=float(data.get('home_win_pct', 0)),
            draw_pct=float(data.get('draw_pct', 0)),
            away_win_pct=float(data.get('away_win_pct', 0)),
            predicted_score=data.get('predicted_score', '1-1').strip(),
            confidence=int(data.get('confidence', 70)),
            ai_insight=data.get('ai_insight', '').strip(),
            is_published=bool(data.get('is_published', True)),
        )
        logger.info(f'Admin {request.user.email} created forecast #{forecast.id}: {forecast}')
        return _ok(serialize_forecast(forecast))

    return _err('Method not allowed.', status=405)


@superuser_required
def admin_forecast_detail(request, forecast_id):
    """
    GET    /admin-api/forecasts/<forecast_id>/
    PATCH  /admin-api/forecasts/<forecast_id>/
    DELETE /admin-api/forecasts/<forecast_id>/
    """
    from core.models import WeeklyForecast

    try:
        forecast = WeeklyForecast.objects.get(pk=forecast_id)
    except WeeklyForecast.DoesNotExist:
        return _err('Forecast not found.', status=404)

    if request.method == 'GET':
        return _ok(serialize_forecast(forecast))

    if request.method in ('PATCH', 'PUT'):
        data = _json_body(request)
        allowed = {
            'home_team', 'away_team', 'competition', 'match_date',
            'home_win_pct', 'draw_pct', 'away_win_pct',
            'predicted_score', 'confidence', 'ai_insight', 'is_published',
        }
        updated = []
        for field, value in data.items():
            if field not in allowed:
                continue
            if field == 'match_date':
                from django.utils.dateparse import parse_datetime
                value = parse_datetime(value)
                if value is None:
                    return _err('Invalid match_date format.')
            setattr(forecast, field, value)
            updated.append(field)
        if updated:
            forecast.save(update_fields=updated)
            logger.info(f'Admin {request.user.email} updated forecast #{forecast.id}: {updated}')
        return _ok(serialize_forecast(forecast))

    if request.method == 'DELETE':
        forecast_repr = str(forecast)
        forecast.delete()
        logger.info(f'Admin {request.user.email} deleted forecast: {forecast_repr}')
        return _ok({'message': f'Forecast "{forecast_repr}" deleted.'})

    return _err('Method not allowed.', status=405)


# ─── Analytics ─────────────────────────────────────────────────────────────────

@superuser_required
def admin_analytics(request):
    """
    GET /admin-api/analytics/
    Returns aggregated analytics: user growth, prediction stats, engine breakdown.
    """
    from predictions.models import Prediction

    users_qs = User.objects.all()
    predictions_qs = Prediction.objects.all()

    data = serialize_analytics(users_qs, predictions_qs)
    return _ok(data)


@superuser_required
def admin_predictions_list(request):
    """
    GET /admin-api/predictions/
    List all predictions with filters.
    Query params: user_id, engine, was_correct, page, per_page
    """
    from predictions.models import Prediction

    qs = Prediction.objects.select_related('user').all()

    user_id = request.GET.get('user_id', '').strip()
    if user_id:
        qs = qs.filter(user_id=user_id)

    engine = request.GET.get('engine', '').strip().upper()
    if engine:
        qs = qs.filter(engine=engine)

    was_correct = request.GET.get('was_correct', '').strip().lower()
    if was_correct == 'true':
        qs = qs.filter(was_correct=True)
    elif was_correct == 'false':
        qs = qs.filter(was_correct=False)
    elif was_correct == 'null':
        qs = qs.filter(was_correct__isnull=True)

    try:
        per_page = min(int(request.GET.get('per_page', 25)), 100)
        page = int(request.GET.get('page', 1))
    except (ValueError, TypeError):
        per_page, page = 25, 1

    qs = qs.order_by('-created_at')
    paginator = Paginator(qs, per_page)
    page_obj = paginator.get_page(page)

    def _serialize_pred(p):
        return {
            'id': p.id,
            'user_id': p.user_id,
            'user_email': p.user.email,
            'engine': p.engine,
            'home_team': p.home_team,
            'away_team': p.away_team,
            'predicted_result': p.predicted_result,
            'confidence': p.confidence,
            'was_correct': p.was_correct,
            'created_at': p.created_at.isoformat(),
        }

    return _ok(
        [_serialize_pred(p) for p in page_obj.object_list],
        pagination={
            'page': page_obj.number,
            'per_page': per_page,
            'total': paginator.count,
            'total_pages': paginator.num_pages,
            'has_next': page_obj.has_next(),
            'has_previous': page_obj.has_previous(),
        },
    )


# ─── Admin Settings ────────────────────────────────────────────────────────────

@superuser_required
def admin_settings(request):
    """
    GET  /admin-api/settings/  — retrieve current plan config and site settings
    POST /admin-api/settings/  — (placeholder) update runtime settings
    """
    from django.conf import settings as django_settings

    cfg = django_settings.MATCHORACLE

    if request.method == 'GET':
        plans = {}
        for plan_key, plan_data in cfg.get('PLANS', {}).items():
            plans[plan_key] = {
                'name': plan_data.get('name', plan_key.title()),
                'price': plan_data.get('price', 0),
                'duration_days': plan_data.get('duration_days'),
                'predictions_per_day': plan_data.get('predictions_per_day', 3),
                'api_access': plan_data.get('api_access', False),
            }

        return _ok({
            'currency': cfg.get('CURRENCY', 'NGN'),
            'currency_symbol': cfg.get('CURRENCY_SYMBOL', 'NGN'),
            'plans': plans,
            'version': cfg.get('VERSION', '2.0.0'),
            'learning_enabled': django_settings.LEARNING_ENABLED,
            'debug': django_settings.DEBUG,
            'paystack_configured': bool(cfg.get('PAYSTACK_SECRET_KEY')),
            'anthropic_configured': bool(cfg.get('ANTHROPIC_API_KEY')),
            'football_api_configured': bool(cfg.get('FOOTBALL_API_KEY')),
        })

    return _err('Settings are read-only via this endpoint.', status=405)


# ─── Activity Log ──────────────────────────────────────────────────────────────

@superuser_required
def admin_activity_log(request):
    """
    GET /admin-api/activity/
    Returns recent user activity: latest predictions, payments, and sign-ups.
    """
    from predictions.models import Prediction

    limit = min(int(request.GET.get('limit', 20)), 100)

    recent_predictions = Prediction.objects.select_related('user').order_by('-created_at')[:limit]
    recent_payments = Payment.objects.select_related('user').order_by('-created_at')[:limit]
    recent_signups = User.objects.order_by('-date_joined')[:limit]

    def _pred(p):
        return {
            'type': 'prediction',
            'id': p.id,
            'user_email': p.user.email,
            'engine': p.engine,
            'home_team': p.home_team,
            'away_team': p.away_team,
            'predicted_result': p.predicted_result,
            'confidence': p.confidence,
            'created_at': p.created_at.isoformat(),
        }

    def _pay(p):
        return {
            'type': 'payment',
            'id': p.id,
            'user_email': p.user.email,
            'plan': p.plan,
            'amount': float(p.amount),
            'status': p.status,
            'created_at': p.created_at.isoformat(),
        }

    def _signup(u):
        return {
            'type': 'signup',
            'id': u.id,
            'email': u.email,
            'plan': u.plan,
            'date_joined': u.date_joined.isoformat(),
        }

    return _ok({
        'recent_predictions': [_pred(p) for p in recent_predictions],
        'recent_payments': [_pay(p) for p in recent_payments],
        'recent_signups': [_signup(u) for u in recent_signups],
    })
