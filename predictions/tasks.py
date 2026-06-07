"""
predictions/tasks.py
────────────────────
Public re-export of all Celery background tasks for the MatchOracle
self-learning system.  Import from here for a stable public API;
the implementation lives in learning_tasks.py.

Tasks
-----
check_match_results      — runs every 6 h; verifies prediction outcomes
update_team_profiles     — runs daily; refreshes team form & tactical style
adjust_engine_weights    — runs weekly; tunes engine accuracy multipliers
build_tactical_profiles  — runs weekly; computes per-style accuracy per team
reset_daily_counters     — runs daily at midnight; resets prediction quotas
queue_result_check       — helper: schedules a deferred result check

Usage
-----
    from predictions.tasks import check_match_results
    check_match_results.delay()                        # async via Celery
    check_match_results(prediction_id=42)              # sync (testing)
"""

from .learning_tasks import (  # noqa: F401  (re-export)
    check_match_results,
    update_team_profiles,
    adjust_engine_weights,
    build_tactical_profiles,
    reset_daily_counters,
    queue_result_check,
    _update_accuracy_for_prediction,
)

__all__ = [
    "check_match_results",
    "update_team_profiles",
    "adjust_engine_weights",
    "build_tactical_profiles",
    "reset_daily_counters",
    "queue_result_check",
    "_update_accuracy_for_prediction",
]
