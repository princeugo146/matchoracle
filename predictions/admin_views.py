"""
admin_views.py
──────────────
Custom admin dashboard views for MatchOracle.

All views require staff login (is_staff=True).
URLs are registered in matchoracle/urls.py under /admin-dashboard/.

Views
-----
DashboardView          — main overview with key metrics
EnginePerformanceView  — per-engine accuracy and weight history
UserAnalyticsView      — user stats, plan breakdown, top users
PaymentTrackingView    — revenue, conversions, recent payments
APIUsageView           — API call volume and top consumers
SystemHealthView       — system status checks and learning metrics
ExportCSVView          — CSV export for any dataset
"""

import csv
import json
import logging
from datetime import timedelta

from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View

from .analytics import (
    get_engine_performance,
    get_user_analytics,
    get_team_analytics,
    get_payment_analytics,
    get_api_usage,
    get_system_health,
)

logger = logging.getLogger(__name__)


def _staff_required(view_func):
    """Shorthand decorator: login + is_staff check."""
    return staff_member_required(view_func, login_url='/accounts/login/')


# ─── Base mixin ───────────────────────────────────────────────────────────────

@method_decorator(staff_member_required(login_url='/accounts/login/'), name='dispatch')
class StaffView(View):
    """Base class — all subclasses inherit the staff_member_required guard."""
    pass


# ─── Dashboard ────────────────────────────────────────────────────────────────

class DashboardView(StaffView):
    template_name = 'admin_dashboard/dashboard.html'

    def get(self, request):
        health = get_system_health()
        engine_data = get_engine_performance()
        user_data = get_user_analytics()
        payment_data = get_payment_analytics()

        # Sparkline data for Chart.js (last 30 days registrations)
        reg_labels = [str(r['date']) for r in user_data['registrations_last_30']]
        reg_counts = [r['count'] for r in user_data['registrations_last_30']]

        # Monthly revenue labels/values
        rev_labels = [str(r['month'])[:7] for r in payment_data['monthly_revenue']]
        rev_values = [float(r['revenue']) for r in payment_data['monthly_revenue']]

        return render(request, self.template_name, {
            'health': health,
            'engines': engine_data['engines'],
            'user_totals': user_data['totals'],
            'plan_breakdown': user_data['plan_breakdown'],
            'payment_totals': payment_data['totals'],
            'recent_payments': payment_data['recent_payments'][:5],
            'recent_signups': user_data['recent_signups'][:5],
            'reg_labels_json': json.dumps(reg_labels),
            'reg_counts_json': json.dumps(reg_counts),
            'rev_labels_json': json.dumps(rev_labels),
            'rev_values_json': json.dumps(rev_values),
            'page': 'dashboard',
        })


# ─── Engine Performance ───────────────────────────────────────────────────────

class EnginePerformanceView(StaffView):
    template_name = 'admin_dashboard/engine_performance.html'

    def get(self, request):
        data = get_engine_performance()

        # Build chart data: accuracy per engine
        engine_labels = [e['label'] for e in data['engines']]
        engine_accuracy = [e['accuracy'] for e in data['engines']]
        engine_totals = [e['total'] for e in data['engines']]

        return render(request, self.template_name, {
            'engines': data['engines'],
            'ea_records': data['engine_accuracy_records'],
            'weight_log': data['weight_adjustments'],
            'engine_labels_json': json.dumps(engine_labels),
            'engine_accuracy_json': json.dumps(engine_accuracy),
            'engine_totals_json': json.dumps(engine_totals),
            'page': 'engine',
        })


# ─── User Analytics ───────────────────────────────────────────────────────────

class UserAnalyticsView(StaffView):
    template_name = 'admin_dashboard/user_analytics.html'

    def get(self, request):
        data = get_user_analytics()

        plan_labels = [p['plan'].title() for p in data['plan_breakdown']]
        plan_counts = [p['count'] for p in data['plan_breakdown']]

        reg_labels = [str(r['date']) for r in data['registrations_last_30']]
        reg_counts = [r['count'] for r in data['registrations_last_30']]

        return render(request, self.template_name, {
            'totals': data['totals'],
            'plan_breakdown': data['plan_breakdown'],
            'top_users': data['top_users'],
            'recent_signups': data['recent_signups'],
            'plan_labels_json': json.dumps(plan_labels),
            'plan_counts_json': json.dumps(plan_counts),
            'reg_labels_json': json.dumps(reg_labels),
            'reg_counts_json': json.dumps(reg_counts),
            'page': 'users',
        })


# ─── Payment Tracking ─────────────────────────────────────────────────────────

class PaymentTrackingView(StaffView):
    template_name = 'admin_dashboard/payment_tracking.html'

    def get(self, request):
        data = get_payment_analytics()

        rev_labels = [str(r['month'])[:7] for r in data['monthly_revenue']]
        rev_values = [float(r['revenue']) for r in data['monthly_revenue']]
        rev_counts = [r['count'] for r in data['monthly_revenue']]

        plan_labels = [p['plan'].title() for p in data['by_plan']]
        plan_revenue = [float(p['revenue']) for p in data['by_plan']]

        return render(request, self.template_name, {
            'totals': data['totals'],
            'by_plan': data['by_plan'],
            'by_currency': data['by_currency'],
            'recent_payments': data['recent_payments'],
            'status_breakdown': data['status_breakdown'],
            'rev_labels_json': json.dumps(rev_labels),
            'rev_values_json': json.dumps(rev_values),
            'rev_counts_json': json.dumps(rev_counts),
            'plan_labels_json': json.dumps(plan_labels),
            'plan_revenue_json': json.dumps(plan_revenue),
            'page': 'payments',
        })


# ─── API Usage ────────────────────────────────────────────────────────────────

class APIUsageView(StaffView):
    template_name = 'admin_dashboard/api_usage.html'

    def get(self, request):
        data = get_api_usage()

        engine_labels = [r['engine'] for r in data['by_engine']]
        engine_counts = [r['count'] for r in data['by_engine']]

        daily_labels = [str(r['date']) for r in data['daily_calls_last_30']]
        daily_counts = [r['count'] for r in data['daily_calls_last_30']]

        return render(request, self.template_name, {
            'totals': data['totals'],
            'by_engine': data['by_engine'],
            'top_api_users': data['top_api_users'],
            'engine_labels_json': json.dumps(engine_labels),
            'engine_counts_json': json.dumps(engine_counts),
            'daily_labels_json': json.dumps(daily_labels),
            'daily_counts_json': json.dumps(daily_counts),
            'page': 'api',
        })


# ─── System Health ────────────────────────────────────────────────────────────

class SystemHealthView(StaffView):
    template_name = 'admin_dashboard/system_health.html'

    def get(self, request):
        data = get_system_health()
        team_data = get_team_analytics()

        return render(request, self.template_name, {
            'health': data,
            'pattern_summary': team_data['pattern_summary'],
            'team_profiles': team_data['team_profiles'][:20],
            'player_profiles': team_data['player_profiles'][:20],
            'page': 'health',
        })


# ─── JSON API endpoints (for live refresh) ────────────────────────────────────

@_staff_required
def health_json(request):
    """Returns system health as JSON — used for auto-refresh on the dashboard."""
    return JsonResponse(get_system_health())


@_staff_required
def engine_json(request):
    return JsonResponse(get_engine_performance())


# ─── CSV Export ───────────────────────────────────────────────────────────────

@_staff_required
def export_csv(request, dataset):
    """
    Generic CSV export endpoint.
    dataset: predictions | users | payments | engine_accuracy | patterns | players
    """
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{dataset}_{timezone.now().date()}.csv"'
    writer = csv.writer(response)

    if dataset == 'predictions':
        from .models import Prediction
        writer.writerow(['id', 'user', 'engine', 'home_team', 'away_team',
                         'predicted_result', 'confidence', 'was_correct', 'created_at'])
        for p in Prediction.objects.select_related('user').order_by('-created_at')[:5000]:
            writer.writerow([
                p.id, p.user.email, p.engine, p.home_team, p.away_team,
                p.predicted_result, p.confidence, p.was_correct, p.created_at,
            ])

    elif dataset == 'users':
        from accounts.models import User
        writer.writerow(['id', 'email', 'plan', 'total_predictions',
                         'correct_predictions', 'created_at', 'subscription_end'])
        for u in User.objects.order_by('-created_at'):
            writer.writerow([
                u.id, u.email, u.plan, u.total_predictions,
                u.correct_predictions, u.created_at, u.subscription_end,
            ])

    elif dataset == 'payments':
        from accounts.models import Payment
        writer.writerow(['id', 'user', 'plan', 'amount', 'currency',
                         'status', 'reference', 'created_at', 'verified_at'])
        for p in Payment.objects.select_related('user').order_by('-created_at'):
            writer.writerow([
                p.id, p.user.email, p.plan, p.amount, p.currency,
                p.status, p.reference, p.created_at, p.verified_at,
            ])

    elif dataset == 'engine_accuracy':
        from .models import EngineAccuracy
        writer.writerow(['engine', 'match_type', 'accuracy_pct', 'home_accuracy',
                         'away_accuracy', 'draw_accuracy', 'weight_adjustment',
                         'sample_size', 'updated_at'])
        for ea in EngineAccuracy.objects.all():
            writer.writerow([
                ea.engine, ea.match_type, ea.accuracy_pct, ea.home_accuracy,
                ea.away_accuracy, ea.draw_accuracy, ea.weight_adjustment,
                ea.sample_size, ea.updated_at,
            ])

    elif dataset == 'patterns':
        from .models import PatternMemory
        writer.writerow(['id', 'pattern_type', 'pattern_key', 'accuracy',
                         'occurrences', 'min_sample', 'last_seen_at'])
        for pm in PatternMemory.objects.order_by('-occurrences'):
            writer.writerow([
                pm.id, pm.pattern_type, pm.pattern_key, pm.accuracy,
                pm.occurrences, pm.min_sample, pm.last_seen_at,
            ])

    elif dataset == 'players':
        from .models import PlayerProfile
        writer.writerow(['id', 'name', 'team', 'position', 'overall_rating',
                         'injury_status', 'goals_this_season', 'assists_this_season',
                         'appearances_this_season', 'prediction_impact', 'updated_at'])
        for pp in PlayerProfile.objects.order_by('-overall_rating'):
            writer.writerow([
                pp.id, pp.name, pp.team, pp.position, pp.overall_rating,
                pp.injury_status, pp.goals_this_season, pp.assists_this_season,
                pp.appearances_this_season, pp.prediction_impact, pp.updated_at,
            ])

    else:
        writer.writerow(['error'])
        writer.writerow([f'Unknown dataset: {dataset}'])

    return response
