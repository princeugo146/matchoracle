"""
predictions/views_analytics.py
───────────────────────────────
Phase 4: Analytics views.

All views require staff login (is_staff=True).  Non-staff users are
redirected to the login page.  Data is pulled from the analytics module
which caches results for 1 hour.
"""

import csv
import json
import logging
from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import render
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_GET

from .analytics import (
    AccuracyAnalytics,
    EnginePerformance,
    UserAnalytics,
    TeamAnalytics,
    PaymentAnalytics,
)

logger = logging.getLogger(__name__)

_staff_required = user_passes_test(lambda u: u.is_staff, login_url='/accounts/login/')


def staff_login_required(view_fn):
    return login_required(_staff_required(view_fn))


# ─── Dashboard ────────────────────────────────────────────────────────────────

@staff_login_required
def analytics_dashboard(request):
    """Main analytics overview page."""
    trend_30 = AccuracyAnalytics.trend(30)
    trend_7  = AccuracyAnalytics.trend(7)
    by_engine = AccuracyAnalytics.by_engine()
    user_summary = UserAnalytics.summary()
    ctx = {
        'page': 'dashboard',
        'overall': AccuracyAnalytics.overall(),
        'trend_30': trend_30,
        'trend_7': trend_7,
        'by_engine': by_engine,
        'home_away_draw': AccuracyAnalytics.home_away_draw(),
        'engine_comparison': EnginePerformance.comparison(),
        'best_worst': EnginePerformance.best_worst(),
        'user_summary': user_summary,
        'mrr': PaymentAnalytics.mrr(),
        'payment_success': PaymentAnalytics.payment_success_rate(),
        'now': timezone.now(),
        # Pre-serialised JSON for Chart.js
        'trend_30_json': json.dumps(trend_30),
        'trend_7_json': json.dumps(trend_7),
        'by_engine_json': json.dumps(by_engine),
    }
    return render(request, 'analytics/dashboard.html', ctx)


# ─── Engine Comparison ────────────────────────────────────────────────────────

@staff_login_required
def engine_comparison(request):
    """Side-by-side engine performance comparison."""
    comparison = EnginePerformance.comparison()
    calibration = EnginePerformance.confidence_calibration()
    ctx = {
        'page': 'engines',
        'comparison': comparison,
        'calibration': calibration,
        'best_worst': EnginePerformance.best_worst(),
        'weight_history': EnginePerformance.weight_history(limit=30),
        'by_match_type': AccuracyAnalytics.by_match_type(),
        'tactical_matchups': AccuracyAnalytics.by_tactical_matchup(),
        # Pre-serialised JSON for Chart.js
        'comparison_json': json.dumps(comparison),
        'calibration_json': json.dumps(calibration),
    }
    return render(request, 'analytics/engine_comparison.html', ctx)


# ─── User Analytics ───────────────────────────────────────────────────────────

@staff_login_required
def user_analytics(request):
    """User engagement and conversion metrics."""
    summary = UserAnalytics.summary()
    accuracy_dist = UserAnalytics.accuracy_distribution()
    ctx = {
        'page': 'users',
        'summary': summary,
        'top_users': UserAnalytics.top_users(limit=20),
        'accuracy_dist': accuracy_dist,
        'api_usage': UserAnalytics.api_usage(limit=10),
        # Pre-serialised JSON for Chart.js
        'summary_json': json.dumps(summary),
        'accuracy_dist_json': json.dumps(accuracy_dist),
    }
    return render(request, 'analytics/user_analytics.html', ctx)


# ─── Team Analytics ───────────────────────────────────────────────────────────

@staff_login_required
def team_analytics(request):
    """Team performance and form analysis."""
    home_away = TeamAnalytics.home_away_accuracy(limit=20)
    ctx = {
        'page': 'teams',
        'home_away': home_away,
        'tactical_styles': TeamAnalytics.tactical_style_accuracy(),
        'form_trends': TeamAnalytics.form_trends(limit=15),
        'player_impact': TeamAnalytics.key_player_impact(limit=15),
        # Pre-serialised JSON for Chart.js
        'home_away_json': json.dumps(home_away),
    }
    return render(request, 'analytics/team_analytics.html', ctx)


# ─── Revenue Analytics ────────────────────────────────────────────────────────

@staff_login_required
def revenue_analytics(request):
    """Payment and revenue metrics."""
    revenue_trend = PaymentAnalytics.revenue_trend(30)
    success_rate = PaymentAnalytics.payment_success_rate()
    ctx = {
        'page': 'revenue',
        'by_plan': PaymentAnalytics.revenue_by_plan(),
        'mrr': PaymentAnalytics.mrr(),
        'success_rate': success_rate,
        'churn_30': PaymentAnalytics.churn(30),
        'revenue_trend': revenue_trend,
        # Pre-serialised JSON for Chart.js
        'revenue_trend_json': json.dumps(revenue_trend),
        'success_rate_json': json.dumps(success_rate),
    }
    return render(request, 'analytics/revenue_analytics.html', ctx)


# ─── JSON API endpoints (for Chart.js AJAX) ───────────────────────────────────

@staff_login_required
@require_GET
def api_accuracy_trend(request):
    days = int(request.GET.get('days', 30))
    days = min(max(days, 7), 365)
    return JsonResponse({'data': AccuracyAnalytics.trend(days)})


@staff_login_required
@require_GET
def api_engine_stats(request):
    return JsonResponse({
        'comparison': EnginePerformance.comparison(),
        'calibration': EnginePerformance.confidence_calibration(),
    })


@staff_login_required
@require_GET
def api_revenue_trend(request):
    days = int(request.GET.get('days', 30))
    days = min(max(days, 7), 365)
    return JsonResponse({'data': PaymentAnalytics.revenue_trend(days)})


# ─── CSV Export ───────────────────────────────────────────────────────────────

@staff_login_required
def export_analytics(request):
    """Export analytics data as CSV."""
    dataset = request.GET.get('dataset', 'accuracy')

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="matchoracle_{dataset}.csv"'
    writer = csv.writer(response)

    if dataset == 'accuracy':
        writer.writerow(['Date', 'Total', 'Correct', 'Accuracy %'])
        for row in AccuracyAnalytics.trend(90):
            writer.writerow([row['date'], row['total'], row['correct'], row['accuracy_pct']])

    elif dataset == 'engines':
        writer.writerow(['Engine', 'Avg Accuracy %', 'Sample Size', 'Home %', 'Away %', 'Draw %'])
        for row in EnginePerformance.comparison():
            writer.writerow([
                row['engine'], row['avg_accuracy'], row['sample_size'],
                row['home_accuracy'], row['away_accuracy'], row['draw_accuracy'],
            ])

    elif dataset == 'users':
        writer.writerow(['Email', 'Plan', 'Total Predictions', 'Correct Predictions'])
        for row in UserAnalytics.top_users(limit=500):
            writer.writerow([row['email'], row['plan'], row['total_predictions'], row['correct_predictions']])

    elif dataset == 'revenue':
        writer.writerow(['Date', 'Revenue (NGN)', 'Payments'])
        for row in PaymentAnalytics.revenue_trend(90):
            writer.writerow([row['date'], row['revenue'], row['count']])

    else:
        writer.writerow(['Error'])
        writer.writerow([f'Unknown dataset: {dataset}'])

    return response
