"""
predictions/tasks.py
────────────────────
Public Celery task interface for the MatchOracle self-learning system.

This module re-exports the canonical tasks from learning_tasks.py and adds
convenience wrappers so external callers (management commands, views, tests)
have a single stable import path:

    from predictions.tasks import check_match_results, verify_predictions, ...

All tasks are safe to call even when Celery / Redis is not configured —
they degrade gracefully and log a warning instead of raising.

Scheduled tasks (configured in settings.CELERY_BEAT_SCHEDULE):
  check_match_results    — every 6 hours
  update_team_profiles   — daily at 03:00
  adjust_engine_weights  — weekly Sunday 04:00
  build_tactical_profiles — weekly Sunday 05:00
  reset_daily_counters   — daily at midnight
"""

import logging
from django.conf import settings

logger = logging.getLogger(__name__)

LEARNING_ENABLED = getattr(settings, 'LEARNING_ENABLED', False)

# ── Re-export canonical tasks ─────────────────────────────────────────────────
try:
    from .learning_tasks import (
        check_match_results,
        update_team_profiles,
        adjust_engine_weights,
        build_tactical_profiles,
        reset_daily_counters,
        queue_result_check,
        _update_accuracy_for_prediction,
    )
except ImportError as _e:
    logger.warning(f"predictions.tasks: could not import learning_tasks — {_e}")

    # Provide no-op stubs so imports never fail
    def check_match_results(*a, **kw):
        return {'skipped': True, 'reason': 'learning_tasks unavailable'}

    def update_team_profiles(*a, **kw):
        return {'skipped': True, 'reason': 'learning_tasks unavailable'}

    def adjust_engine_weights(*a, **kw):
        return {'skipped': True, 'reason': 'learning_tasks unavailable'}

    def build_tactical_profiles(*a, **kw):
        return {'skipped': True, 'reason': 'learning_tasks unavailable'}

    def reset_daily_counters(*a, **kw):
        return {'skipped': True, 'reason': 'learning_tasks unavailable'}

    def queue_result_check(prediction_id, delay_seconds=172800):
        pass

    def _update_accuracy_for_prediction(prediction_id):
        pass


# ── Additional convenience wrappers ──────────────────────────────────────────

def verify_predictions(max_predictions=50):
    """
    Alias for check_match_results().check_pending().
    Finds unverified predictions from 2-3 days ago and fetches real results.

    Returns {'checked': int, 'found': int, 'errors': int}
    """
    if not LEARNING_ENABLED:
        return {'checked': 0, 'found': 0, 'errors': 0, 'skipped': True}
    try:
        from .learning import ResultChecker
        checker = ResultChecker()
        return checker.check_pending(max_predictions=max_predictions)
    except Exception as e:
        logger.error(f"verify_predictions failed: {e}", exc_info=True)
        return {'checked': 0, 'found': 0, 'errors': 1}


def update_engine_accuracy():
    """
    Recalculate accuracy per engine per match type from all verified results.
    Wraps adjust_engine_weights() for a more descriptive name.

    Returns {'updated': int}
    """
    if not LEARNING_ENABLED:
        return {'updated': 0, 'skipped': True}
    try:
        from .learning import WeightAdjuster
        adjuster = WeightAdjuster()
        return adjuster.run()
    except Exception as e:
        logger.error(f"update_engine_accuracy failed: {e}", exc_info=True)
        return {'updated': 0, 'error': str(e)}


def extract_patterns():
    """
    Learn successful tactical patterns from all verified predictions.
    Wraps PatternLearner.run().

    Returns {'processed': int, 'errors': int}
    """
    if not LEARNING_ENABLED:
        return {'processed': 0, 'errors': 0, 'skipped': True}
    try:
        from .learning import PatternLearner
        learner = PatternLearner()
        return learner.run()
    except Exception as e:
        logger.error(f"extract_patterns failed: {e}", exc_info=True)
        return {'processed': 0, 'errors': 1}


def adjust_weights():
    """
    Automatically adjust engine weights based on accuracy.
    Alias for update_engine_accuracy() with a more intuitive name.
    """
    return update_engine_accuracy()


def get_accuracy_summary():
    """
    Return a summary of prediction accuracy across all engines.
    Read-only — does not modify any data.

    Returns {'total': int, 'correct': int, 'accuracy_pct': float, 'by_engine': dict}
    """
    try:
        from .learning import AccuracyTracker
        tracker = AccuracyTracker()
        return tracker.summary()
    except Exception as e:
        logger.warning(f"get_accuracy_summary failed: {e}")
        return {'total': 0, 'correct': 0, 'accuracy_pct': 0.0, 'by_engine': {}}
