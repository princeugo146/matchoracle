"""
predictions/analytics.py
─────────────────────────
Phase 4: Advanced Analytics classes.

All classes are safe to import even when the DB is empty — every method
returns sensible defaults and never raises.  Results are cached for 1 hour
using Django's cache framework (falls back to LocMemCache if Redis is absent).
"""

import logging
from datetime import timedelta
from django.utils import timezone
from django.db.models import Count, Avg, Sum, Q, F, FloatField, ExpressionWrapper
from django.core.cache import cache

logger = logging.getLogger(__name__)

# Cache TTL: 1 hour
_TTL = 3600


def _safe(fn, default=None):
    """Execute fn(); return default on any exception."""
    try:
        return fn()
    except Exception as exc:
        logger.debug('analytics._safe: %s', exc)
        return default


# ─── AccuracyAnalytics ────────────────────────────────────────────────────────

class AccuracyAnalytics:
    """Overall and segmented accuracy statistics."""

    # ── helpers ──────────────────────────────────────────────────────────────

    @staticmethod
    def _base_qs():
        from .models import Prediction
        return Prediction.objects.filter(was_correct__isnull=False)

    @staticmethod
    def _pct(correct, total):
        return round(correct / total * 100, 1) if total else 0.0

    # ── public API ────────────────────────────────────────────────────────────

    @classmethod
    def overall(cls):
        """Return {total, correct, accuracy_pct} for all verified predictions."""
        key = 'analytics:accuracy:overall'
        cached = cache.get(key)
        if cached is not None:
            return cached

        def _compute():
            qs = cls._base_qs()
            total = qs.count()
            correct = qs.filter(was_correct=True).count()
            return {'total': total, 'correct': correct, 'accuracy_pct': cls._pct(correct, total)}

        result = _safe(_compute, {'total': 0, 'correct': 0, 'accuracy_pct': 0.0})
        cache.set(key, result, _TTL)
        return result

    @classmethod
    def trend(cls, days=30):
        """
        Return a list of {date, total, correct, accuracy_pct} dicts,
        one per day for the last `days` days.
        """
        key = f'analytics:accuracy:trend:{days}'
        cached = cache.get(key)
        if cached is not None:
            return cached

        def _compute():
            from .models import Prediction
            from django.db.models.functions import TruncDate
            cutoff = timezone.now() - timedelta(days=days)
            rows = (
                Prediction.objects
                .filter(created_at__gte=cutoff, was_correct__isnull=False)
                .annotate(date=TruncDate('created_at'))
                .values('date')
                .annotate(total=Count('id'), correct=Count('id', filter=Q(was_correct=True)))
                .order_by('date')
            )
            return [
                {
                    'date': str(r['date']),
                    'total': r['total'],
                    'correct': r['correct'],
                    'accuracy_pct': cls._pct(r['correct'], r['total']),
                }
                for r in rows
            ]

        result = _safe(_compute, [])
        cache.set(key, result, _TTL)
        return result

    @classmethod
    def by_engine(cls):
        """Return per-engine accuracy breakdown."""
        key = 'analytics:accuracy:by_engine'
        cached = cache.get(key)
        if cached is not None:
            return cached

        def _compute():
            qs = cls._base_qs()
            rows = (
                qs.values('engine')
                .annotate(total=Count('id'), correct=Count('id', filter=Q(was_correct=True)))
                .order_by('engine')
            )
            return [
                {
                    'engine': r['engine'],
                    'total': r['total'],
                    'correct': r['correct'],
                    'accuracy_pct': cls._pct(r['correct'], r['total']),
                }
                for r in rows
            ]

        result = _safe(_compute, [])
        cache.set(key, result, _TTL)
        return result

    @classmethod
    def by_match_type(cls):
        """Return per-match-type accuracy using EngineAccuracy records."""
        key = 'analytics:accuracy:by_match_type'
        cached = cache.get(key)
        if cached is not None:
            return cached

        def _compute():
            from .models import EngineAccuracy
            rows = (
                EngineAccuracy.objects
                .values('match_type')
                .annotate(avg_acc=Avg('accuracy_pct'), total_samples=Sum('sample_size'))
                .order_by('match_type')
            )
            return [
                {
                    'match_type': r['match_type'],
                    'avg_accuracy_pct': round(r['avg_acc'] or 0, 1),
                    'total_samples': r['total_samples'] or 0,
                }
                for r in rows
            ]

        result = _safe(_compute, [])
        cache.set(key, result, _TTL)
        return result

    @classmethod
    def home_away_draw(cls):
        """Return accuracy split by predicted result type (home/away/draw)."""
        key = 'analytics:accuracy:had'
        cached = cache.get(key)
        if cached is not None:
            return cached

        def _compute():
            from .models import EngineAccuracy
            agg = EngineAccuracy.objects.aggregate(
                avg_home=Avg('home_accuracy'),
                avg_away=Avg('away_accuracy'),
                avg_draw=Avg('draw_accuracy'),
            )
            return {
                'home': round(agg['avg_home'] or 0, 1),
                'away': round(agg['avg_away'] or 0, 1),
                'draw': round(agg['avg_draw'] or 0, 1),
            }

        result = _safe(_compute, {'home': 0.0, 'away': 0.0, 'draw': 0.0})
        cache.set(key, result, _TTL)
        return result

    @classmethod
    def by_tactical_matchup(cls):
        """Return accuracy per tactical matchup from PatternMemory."""
        key = 'analytics:accuracy:tactical'
        cached = cache.get(key)
        if cached is not None:
            return cached

        def _compute():
            from .models import PatternMemory
            rows = (
                PatternMemory.objects
                .filter(pattern_type='matchup', occurrences__gte=5)
                .values('pattern_key', 'accuracy', 'occurrences')
                .order_by('-accuracy')[:20]
            )
            return list(rows)

        result = _safe(_compute, [])
        cache.set(key, result, _TTL)
        return result


# ─── EnginePerformance ────────────────────────────────────────────────────────

class EnginePerformance:
    """Engine-level performance metrics and calibration."""

    @classmethod
    def comparison(cls):
        """Return side-by-side stats for all engines."""
        key = 'analytics:engine:comparison'
        cached = cache.get(key)
        if cached is not None:
            return cached

        def _compute():
            from .models import EngineAccuracy, Prediction
            engines = {}
            for ea in EngineAccuracy.objects.all():
                e = ea.engine
                if e not in engines:
                    engines[e] = {
                        'engine': e,
                        'accuracy_pct': [],
                        'sample_size': 0,
                        'home_accuracy': [],
                        'away_accuracy': [],
                        'draw_accuracy': [],
                    }
                engines[e]['accuracy_pct'].append(ea.accuracy_pct)
                engines[e]['sample_size'] += ea.sample_size
                engines[e]['home_accuracy'].append(ea.home_accuracy)
                engines[e]['away_accuracy'].append(ea.away_accuracy)
                engines[e]['draw_accuracy'].append(ea.draw_accuracy)

            result = []
            for e, d in engines.items():
                avg = lambda lst: round(sum(lst) / len(lst), 1) if lst else 0.0
                result.append({
                    'engine': e,
                    'avg_accuracy': avg(d['accuracy_pct']),
                    'sample_size': d['sample_size'],
                    'home_accuracy': avg(d['home_accuracy']),
                    'away_accuracy': avg(d['away_accuracy']),
                    'draw_accuracy': avg(d['draw_accuracy']),
                })
            result.sort(key=lambda x: x['avg_accuracy'], reverse=True)
            return result

        result = _safe(_compute, [])
        cache.set(key, result, _TTL)
        return result

    @classmethod
    def weight_history(cls, engine=None, limit=50):
        """Return recent weight adjustments, optionally filtered by engine."""
        key = f'analytics:engine:weights:{engine}:{limit}'
        cached = cache.get(key)
        if cached is not None:
            return cached

        def _compute():
            from .models import WeightAdjustment
            qs = WeightAdjustment.objects.order_by('-applied_at')
            if engine:
                qs = qs.filter(engine=engine)
            return list(
                qs[:limit].values(
                    'id', 'engine', 'parameter', 'old_weight', 'new_weight',
                    'reason', 'accuracy_before', 'accuracy_after', 'match_type', 'applied_at',
                )
            )

        result = _safe(_compute, [])
        cache.set(key, result, _TTL)
        return result

    @classmethod
    def confidence_calibration(cls):
        """
        Check whether stated confidence matches actual accuracy.
        Groups predictions into confidence buckets (0-49, 50-69, 70-89, 90-100)
        and returns actual accuracy per bucket.
        """
        key = 'analytics:engine:calibration'
        cached = cache.get(key)
        if cached is not None:
            return cached

        def _compute():
            from .models import Prediction
            buckets = [
                ('0–49%',  0,  49),
                ('50–69%', 50, 69),
                ('70–89%', 70, 89),
                ('90–100%', 90, 100),
            ]
            result = []
            for label, lo, hi in buckets:
                qs = Prediction.objects.filter(
                    confidence__gte=lo, confidence__lte=hi, was_correct__isnull=False
                )
                total = qs.count()
                correct = qs.filter(was_correct=True).count()
                result.append({
                    'bucket': label,
                    'stated_confidence_mid': (lo + hi) // 2,
                    'total': total,
                    'actual_accuracy': round(correct / total * 100, 1) if total else 0.0,
                })
            return result

        result = _safe(_compute, [])
        cache.set(key, result, _TTL)
        return result

    @classmethod
    def best_worst(cls):
        """Return the best and worst performing engine/match_type combos."""
        key = 'analytics:engine:best_worst'
        cached = cache.get(key)
        if cached is not None:
            return cached

        def _compute():
            from .models import EngineAccuracy
            qs = EngineAccuracy.objects.filter(sample_size__gte=10).order_by('-accuracy_pct')
            best = list(qs[:3].values('engine', 'match_type', 'accuracy_pct', 'sample_size'))
            worst = list(qs.reverse()[:3].values('engine', 'match_type', 'accuracy_pct', 'sample_size'))
            return {'best': best, 'worst': worst}

        result = _safe(_compute, {'best': [], 'worst': []})
        cache.set(key, result, _TTL)
        return result


# ─── UserAnalytics ────────────────────────────────────────────────────────────

class UserAnalytics:
    """User-level engagement and conversion metrics."""

    @classmethod
    def summary(cls):
        """Return high-level user counts and averages."""
        key = 'analytics:user:summary'
        cached = cache.get(key)
        if cached is not None:
            return cached

        def _compute():
            from accounts.models import User
            total = User.objects.count()
            active_week = User.objects.filter(
                predictions__created_at__gte=timezone.now() - timedelta(days=7)
            ).distinct().count()
            paid = User.objects.exclude(plan='free').count()
            conversion = round(paid / total * 100, 1) if total else 0.0
            avg_preds = User.objects.aggregate(avg=Avg('total_predictions'))['avg'] or 0
            return {
                'total_users': total,
                'active_last_7d': active_week,
                'paid_users': paid,
                'free_users': total - paid,
                'conversion_rate': conversion,
                'avg_predictions_per_user': round(avg_preds, 1),
            }

        result = _safe(_compute, {})
        cache.set(key, result, _TTL)
        return result

    @classmethod
    def top_users(cls, limit=10):
        """Return the most active users by prediction count."""
        key = f'analytics:user:top:{limit}'
        cached = cache.get(key)
        if cached is not None:
            return cached

        def _compute():
            from accounts.models import User
            return list(
                User.objects
                .annotate(pred_count=Count('predictions'))
                .order_by('-pred_count')
                [:limit]
                .values('email', 'plan', 'pred_count', 'correct_predictions', 'total_predictions')
            )

        result = _safe(_compute, [])
        cache.set(key, result, _TTL)
        return result

    @classmethod
    def accuracy_distribution(cls):
        """Return how many users fall into each accuracy bucket."""
        key = 'analytics:user:accuracy_dist'
        cached = cache.get(key)
        if cached is not None:
            return cached

        def _compute():
            from accounts.models import User
            buckets = {'0–25%': 0, '26–50%': 0, '51–75%': 0, '76–100%': 0}
            for u in User.objects.filter(total_predictions__gt=0):
                acc = u.accuracy_rate
                if acc <= 25:
                    buckets['0–25%'] += 1
                elif acc <= 50:
                    buckets['26–50%'] += 1
                elif acc <= 75:
                    buckets['51–75%'] += 1
                else:
                    buckets['76–100%'] += 1
            return [{'bucket': k, 'count': v} for k, v in buckets.items()]

        result = _safe(_compute, [])
        cache.set(key, result, _TTL)
        return result

    @classmethod
    def api_usage(cls, limit=10):
        """Return top API users by prediction count (users with api_access plans)."""
        key = f'analytics:user:api:{limit}'
        cached = cache.get(key)
        if cached is not None:
            return cached

        def _compute():
            from accounts.models import User
            from django.conf import settings
            api_plans = [
                p for p, cfg in settings.MATCHORACLE['PLANS'].items()
                if cfg.get('api_access')
            ]
            return list(
                User.objects
                .filter(plan__in=api_plans)
                .annotate(pred_count=Count('predictions'))
                .order_by('-pred_count')
                [:limit]
                .values('email', 'plan', 'pred_count')
            )

        result = _safe(_compute, [])
        cache.set(key, result, _TTL)
        return result


# ─── TeamAnalytics ────────────────────────────────────────────────────────────

class TeamAnalytics:
    """Team-level performance and form analytics."""

    @classmethod
    def home_away_accuracy(cls, limit=20):
        """Return teams ranked by home accuracy."""
        key = f'analytics:team:home_away:{limit}'
        cached = cache.get(key)
        if cached is not None:
            return cached

        def _compute():
            from .models import TeamProfile
            return list(
                TeamProfile.objects
                .filter(sample_size__gte=5)
                .order_by('-home_accuracy')
                [:limit]
                .values('team_name', 'home_accuracy', 'away_accuracy', 'sample_size', 'tactical_style')
            )

        result = _safe(_compute, [])
        cache.set(key, result, _TTL)
        return result

    @classmethod
    def tactical_style_accuracy(cls):
        """Return average accuracy grouped by tactical style."""
        key = 'analytics:team:tactical_style'
        cached = cache.get(key)
        if cached is not None:
            return cached

        def _compute():
            from .models import TeamProfile
            rows = (
                TeamProfile.objects
                .filter(sample_size__gte=5)
                .values('tactical_style')
                .annotate(
                    avg_home=Avg('home_accuracy'),
                    avg_away=Avg('away_accuracy'),
                    team_count=Count('id'),
                )
                .order_by('-avg_home')
            )
            return [
                {
                    'style': r['tactical_style'],
                    'avg_home_accuracy': round(r['avg_home'] or 0, 1),
                    'avg_away_accuracy': round(r['avg_away'] or 0, 1),
                    'team_count': r['team_count'],
                }
                for r in rows
            ]

        result = _safe(_compute, [])
        cache.set(key, result, _TTL)
        return result

    @classmethod
    def form_trends(cls, limit=10):
        """Return teams with the best recent form (last 5 results)."""
        key = f'analytics:team:form:{limit}'
        cached = cache.get(key)
        if cached is not None:
            return cached

        def _compute():
            from .models import TeamProfile
            teams = TeamProfile.objects.filter(sample_size__gte=3).order_by('-home_accuracy')[:50]
            result = []
            for t in teams:
                recent = t.last_20_results[:5]
                wins = sum(1 for r in recent if r.get('result') == 'W')
                result.append({
                    'team_name': t.team_name,
                    'recent_wins': wins,
                    'form_string': ''.join(r.get('result', '?') for r in recent),
                    'avg_goals_scored': t.avg_goals_scored,
                    'avg_goals_conceded': t.avg_goals_conceded,
                })
            result.sort(key=lambda x: x['recent_wins'], reverse=True)
            return result[:limit]

        result = _safe(_compute, [])
        cache.set(key, result, _TTL)
        return result

    @classmethod
    def key_player_impact(cls, limit=15):
        """Return players with the highest prediction_impact."""
        key = f'analytics:team:player_impact:{limit}'
        cached = cache.get(key)
        if cached is not None:
            return cached

        def _compute():
            from .models import PlayerProfile
            return list(
                PlayerProfile.objects
                .filter(appearances_this_season__gte=5)
                .order_by('-prediction_impact')
                [:limit]
                .values('name', 'team', 'position', 'overall_rating', 'prediction_impact', 'injury_status')
            )

        result = _safe(_compute, [])
        cache.set(key, result, _TTL)
        return result


# ─── PaymentAnalytics ─────────────────────────────────────────────────────────

class PaymentAnalytics:
    """Revenue and subscription metrics."""

    @classmethod
    def revenue_by_plan(cls):
        """Return total revenue and payment count per plan."""
        key = 'analytics:payment:by_plan'
        cached = cache.get(key)
        if cached is not None:
            return cached

        def _compute():
            from accounts.models import Payment
            rows = (
                Payment.objects
                .filter(status='success')
                .values('plan')
                .annotate(total_revenue=Sum('amount'), payment_count=Count('id'))
                .order_by('-total_revenue')
            )
            return [
                {
                    'plan': r['plan'],
                    'total_revenue': float(r['total_revenue'] or 0),
                    'payment_count': r['payment_count'],
                }
                for r in rows
            ]

        result = _safe(_compute, [])
        cache.set(key, result, _TTL)
        return result

    @classmethod
    def mrr(cls):
        """
        Approximate Monthly Recurring Revenue.
        Counts active paid subscribers × their plan price.
        """
        key = 'analytics:payment:mrr'
        cached = cache.get(key)
        if cached is not None:
            return cached

        def _compute():
            from accounts.models import User
            from django.conf import settings
            now = timezone.now()
            plans = settings.MATCHORACLE['PLANS']
            total = 0.0
            breakdown = []
            for plan_key, cfg in plans.items():
                if plan_key == 'free':
                    continue
                price = cfg.get('price', 0)
                duration = cfg.get('duration_days', 30) or 30
                # Monthly equivalent
                monthly_price = price * (30 / duration)
                active = User.objects.filter(
                    plan=plan_key,
                    subscription_end__gt=now,
                ).count()
                revenue = round(active * monthly_price, 2)
                total += revenue
                breakdown.append({'plan': plan_key, 'active_subscribers': active, 'mrr': revenue})
            return {'total_mrr': round(total, 2), 'breakdown': breakdown}

        result = _safe(_compute, {'total_mrr': 0.0, 'breakdown': []})
        cache.set(key, result, _TTL)
        return result

    @classmethod
    def payment_success_rate(cls):
        """Return overall payment success/failure/pending counts."""
        key = 'analytics:payment:success_rate'
        cached = cache.get(key)
        if cached is not None:
            return cached

        def _compute():
            from accounts.models import Payment
            agg = Payment.objects.values('status').annotate(count=Count('id'))
            counts = {r['status']: r['count'] for r in agg}
            total = sum(counts.values())
            success = counts.get('success', 0)
            return {
                'total': total,
                'success': success,
                'failed': counts.get('failed', 0),
                'pending': counts.get('pending', 0),
                'success_rate': round(success / total * 100, 1) if total else 0.0,
            }

        result = _safe(_compute, {'total': 0, 'success': 0, 'failed': 0, 'pending': 0, 'success_rate': 0.0})
        cache.set(key, result, _TTL)
        return result

    @classmethod
    def churn(cls, days=30):
        """
        Approximate churn: users whose subscription_end fell within the last
        `days` days (i.e. they didn't renew).
        """
        key = f'analytics:payment:churn:{days}'
        cached = cache.get(key)
        if cached is not None:
            return cached

        def _compute():
            from accounts.models import User
            now = timezone.now()
            cutoff = now - timedelta(days=days)
            churned = User.objects.filter(
                subscription_end__gte=cutoff,
                subscription_end__lt=now,
            ).exclude(plan='free').count()
            return {'churned_last_n_days': churned, 'days': days}

        result = _safe(_compute, {'churned_last_n_days': 0, 'days': days})
        cache.set(key, result, _TTL)
        return result

    @classmethod
    def revenue_trend(cls, days=30):
        """Return daily revenue for the last `days` days."""
        key = f'analytics:payment:trend:{days}'
        cached = cache.get(key)
        if cached is not None:
            return cached

        def _compute():
            from accounts.models import Payment
            from django.db.models.functions import TruncDate
            cutoff = timezone.now() - timedelta(days=days)
            rows = (
                Payment.objects
                .filter(status='success', created_at__gte=cutoff)
                .annotate(date=TruncDate('created_at'))
                .values('date')
                .annotate(revenue=Sum('amount'), count=Count('id'))
                .order_by('date')
            )
            return [
                {'date': str(r['date']), 'revenue': float(r['revenue'] or 0), 'count': r['count']}
                for r in rows
            ]

        result = _safe(_compute, [])
        cache.set(key, result, _TTL)
        return result
