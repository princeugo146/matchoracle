"""
Analytics calculation functions for the MatchOracle dashboard.

All functions are safe to call even when the database is empty — they
return sensible zero/empty defaults rather than raising exceptions.
"""

import logging
from datetime import date, timedelta
from django.utils import timezone

logger = logging.getLogger(__name__)


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _get_model():
    """Lazy import to avoid circular imports at module load time."""
    from .models import PredictionResult
    return PredictionResult


def _get_prediction_model():
    from .models import Prediction
    return Prediction


# ─── Core Accuracy Metrics ────────────────────────────────────────────────────

def get_accuracy_percentage():
    """
    Return the overall prediction accuracy as a float (0–100).
    Only counts PredictionResult rows where is_correct is not None.
    """
    try:
        PredictionResult = _get_model()
        total = PredictionResult.objects.filter(is_correct__isnull=False).count()
        if total == 0:
            return 0.0
        correct = PredictionResult.objects.filter(is_correct=True).count()
        return round(correct / total * 100, 1)
    except Exception as e:
        logger.warning(f"get_accuracy_percentage error: {e}")
        return 0.0


def get_win_count():
    """Return the number of correct predictions."""
    try:
        PredictionResult = _get_model()
        return PredictionResult.objects.filter(is_correct=True).count()
    except Exception as e:
        logger.warning(f"get_win_count error: {e}")
        return 0


def get_loss_count():
    """Return the number of incorrect predictions."""
    try:
        PredictionResult = _get_model()
        return PredictionResult.objects.filter(is_correct=False).count()
    except Exception as e:
        logger.warning(f"get_loss_count error: {e}")
        return 0


def get_total_predictions():
    """Return the total number of PredictionResult rows."""
    try:
        PredictionResult = _get_model()
        return PredictionResult.objects.count()
    except Exception as e:
        logger.warning(f"get_total_predictions error: {e}")
        return 0


# ─── Trend Analysis ───────────────────────────────────────────────────────────

def get_accuracy_trend_30_days():
    """
    Return a list of 30 daily accuracy data points (7-day rolling average).

    Each item is a dict: {date: str, accuracy: float, count: int}
    Days with no predictions get accuracy=0 and count=0.
    """
    try:
        PredictionResult = _get_model()
        today = timezone.now().date()
        start = today - timedelta(days=29)

        # Fetch all resolved results in the window
        results = list(
            PredictionResult.objects.filter(
                created_at__date__gte=start,
                is_correct__isnull=False,
            ).values('created_at', 'is_correct')
        )

        # Build a day-keyed dict: {date: [is_correct, ...]}
        day_map = {}
        for r in results:
            d = r['created_at'].date() if hasattr(r['created_at'], 'date') else r['created_at']
            day_map.setdefault(d, []).append(r['is_correct'])

        # Build 30-day series with 7-day rolling average
        series = []
        for i in range(30):
            day = start + timedelta(days=i)
            # 7-day window ending on this day
            window_start = day - timedelta(days=6)
            window_correct = 0
            window_total = 0
            for j in range(7):
                wd = window_start + timedelta(days=j)
                day_results = day_map.get(wd, [])
                window_correct += sum(1 for x in day_results if x)
                window_total += len(day_results)

            day_results = day_map.get(day, [])
            accuracy = round(window_correct / window_total * 100, 1) if window_total else 0.0
            series.append({
                'date': day.strftime('%d %b'),
                'accuracy': accuracy,
                'count': len(day_results),
            })

        return series
    except Exception as e:
        logger.warning(f"get_accuracy_trend_30_days error: {e}")
        return []


# ─── Engine Comparison ────────────────────────────────────────────────────────

def get_engine_accuracy_comparison():
    """
    Return per-engine accuracy stats derived from PredictionResult rows
    that have engine-specific verdicts stored.

    Returns a dict: {
        'engine_a': {'accuracy': float, 'count': int},
        'engine_d': {'accuracy': float, 'count': int},
        'smart_ai': {'accuracy': float, 'count': int},
    }
    """
    try:
        PredictionResult = _get_model()
        stats = {}

        for engine_key, verdict_field in [
            ('engine_a', 'engine_a_verdict'),
            ('engine_d', 'engine_d_verdict'),
            ('smart_ai', 'smart_ai_verdict'),
        ]:
            qs = PredictionResult.objects.filter(
                is_correct__isnull=False,
                **{f"{verdict_field}__gt": ''},
            )
            total = qs.count()
            correct = qs.filter(is_correct=True).count()
            stats[engine_key] = {
                'accuracy': round(correct / total * 100, 1) if total else 0.0,
                'count': total,
            }

        return stats
    except Exception as e:
        logger.warning(f"get_engine_accuracy_comparison error: {e}")
        return {
            'engine_a': {'accuracy': 0.0, 'count': 0},
            'engine_d': {'accuracy': 0.0, 'count': 0},
            'smart_ai': {'accuracy': 0.0, 'count': 0},
        }


# ─── Today's Predictions ──────────────────────────────────────────────────────

def get_top_predictions_today():
    """
    Return the top 3 PredictionResult rows created today, ordered by
    confidence_level descending.

    Each item is a PredictionResult instance.
    """
    try:
        PredictionResult = _get_model()
        today = timezone.now().date()
        return list(
            PredictionResult.objects.filter(
                created_at__date=today,
            ).order_by('-confidence_level')[:3]
        )
    except Exception as e:
        logger.warning(f"get_top_predictions_today error: {e}")
        return []


# ─── Prediction History ───────────────────────────────────────────────────────

def get_prediction_history(limit=10):
    """
    Return the most recent `limit` PredictionResult rows.
    """
    try:
        PredictionResult = _get_model()
        return list(PredictionResult.objects.all()[:limit])
    except Exception as e:
        logger.warning(f"get_prediction_history error: {e}")
        return []


# ─── Store / Update ───────────────────────────────────────────────────────────

def store_prediction_result(
    home_team='',
    away_team='',
    match_date=None,
    predicted_verdict='',
    predicted_score='',
    confidence_level=0,
    engine_a_verdict='',
    engine_d_verdict='',
    smart_ai_verdict='',
    prediction_instance=None,
):
    """
    Persist a new PredictionResult row.

    Returns the created PredictionResult instance, or None on error.
    """
    try:
        PredictionResult = _get_model()
        obj = PredictionResult.objects.create(
            home_team=home_team,
            away_team=away_team,
            match_date=match_date or timezone.now().date(),
            predicted_verdict=predicted_verdict,
            predicted_score=predicted_score,
            confidence_level=confidence_level,
            engine_a_verdict=engine_a_verdict,
            engine_d_verdict=engine_d_verdict,
            smart_ai_verdict=smart_ai_verdict,
            prediction=prediction_instance,
        )
        return obj
    except Exception as e:
        logger.error(f"store_prediction_result error: {e}")
        return None


def update_prediction_result(result_id, actual_result='', actual_score='', is_correct=None):
    """
    Update an existing PredictionResult with the real-world outcome.

    Returns the updated instance, or None if not found / on error.
    """
    try:
        PredictionResult = _get_model()
        obj = PredictionResult.objects.get(pk=result_id)
        if actual_result:
            obj.actual_result = actual_result
        if actual_score:
            obj.actual_score = actual_score
        if is_correct is not None:
            obj.is_correct = is_correct
        obj.save(update_fields=['actual_result', 'actual_score', 'is_correct', 'updated_at'])
        return obj
    except Exception as e:
        logger.error(f"update_prediction_result error: {e}")
        return None


# ─── Dashboard Summary ────────────────────────────────────────────────────────

def get_dashboard_analytics():
    """
    Convenience function that returns all analytics data needed by the
    dashboard in a single dict, so the view only needs one call.
    """
    return {
        'accuracy_pct': get_accuracy_percentage(),
        'win_count': get_win_count(),
        'loss_count': get_loss_count(),
        'total_predictions': get_total_predictions(),
        'trend_30_days': get_accuracy_trend_30_days(),
        'engine_comparison': get_engine_accuracy_comparison(),
        'top_predictions_today': get_top_predictions_today(),
        'prediction_history': get_prediction_history(limit=10),
    }
