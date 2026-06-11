"""
learning_tasks.py
─────────────────
Celery background tasks for the MatchOracle self-learning system.

All tasks are fully async and isolated from the main request/response cycle.
If a task fails, predictions continue to work normally — learning is additive,
never a hard dependency.

Schedule (configured in settings.py CELERY_BEAT_SCHEDULE):
  check_match_results   — every 6 hours
  update_team_profiles  — daily at 03:00
  adjust_engine_weights — weekly on Sunday at 04:00
  build_tactical_profiles — weekly on Sunday at 05:00
"""

import logging
from datetime import timedelta
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

# ─── Guard: only import Celery machinery when learning is enabled ─────────────
# This prevents import errors on deployments that don't have Celery/Redis.

LEARNING_ENABLED = getattr(settings, 'LEARNING_ENABLED', False)

try:
    from celery import shared_task
    _CELERY_AVAILABLE = True
except ImportError:
    _CELERY_AVAILABLE = False
    # Provide a no-op decorator so the module still imports cleanly
    def shared_task(*args, **kwargs):  # noqa: F811
        def decorator(fn):
            return fn
        if args and callable(args[0]):
            return args[0]
        return decorator


# ─── Task 1: Check match results ─────────────────────────────────────────────

@shared_task(bind=True, max_retries=3, default_retry_delay=300)
def check_match_results(self, prediction_id=None):
    """
    Runs every 30 minutes.  Finds predictions from 1 hour–24 hours ago that
    haven't been verified yet, searches the web for the real result, and
    stores it in PredictionResult.  Also triggers downstream accuracy updates.

    If prediction_id is supplied, only that prediction is checked (used when
    a prediction is first saved so we can queue a deferred check).
    """
    if not LEARNING_ENABLED:
        return {'skipped': True, 'reason': 'LEARNING_ENABLED is False'}

    try:
        from .models import Prediction, PredictionResult
        from .learning_utils import fetch_match_result, score_margin_of_error

        now = timezone.now()

        if prediction_id:
            qs = Prediction.objects.filter(
                id=prediction_id,
                engine__in=['A', 'NL'],
                home_team__gt='',
                away_team__gt='',
            ).exclude(result_record__isnull=False)
        else:
            # Predictions made 1 hour–24 hours ago that still have no result record
            window_start = now - timedelta(hours=24)
            window_end = now - timedelta(hours=1)
            qs = Prediction.objects.filter(
                created_at__range=(window_start, window_end),
                engine__in=['A', 'NL'],
                home_team__gt='',
                away_team__gt='',
            ).exclude(result_record__isnull=False)

        checked = 0
        for pred in qs[:50]:  # cap at 50 per run to avoid overloading the web search
            try:
                result_data = fetch_match_result(pred.home_team, pred.away_team)
                if not result_data or not result_data.get('found'):
                    continue

                actual_winner = result_data['winner']
                actual_score = result_data['score']
                predicted_verdict = pred.predicted_result or pred.output_data.get('verdict', '')

                # Determine correctness: compare winner strings case-insensitively
                was_correct = (
                    predicted_verdict.lower().strip() == actual_winner.lower().strip()
                )

                # Score margin of error
                predicted_score = pred.output_data.get('predicted_score', '')
                margin = score_margin_of_error(predicted_score, actual_score)

                pr, created = PredictionResult.objects.update_or_create(
                    prediction=pred,
                    defaults={
                        'actual_result': actual_winner,
                        'actual_score': actual_score,
                        'was_correct': was_correct,
                        'margin_of_error': margin,
                        'result_checked_at': now,
                        'result_source': 'web_search',
                        'raw_data': result_data,
                    },
                )

                # Mirror correctness back onto the Prediction row for quick queries
                pred.was_correct = was_correct
                pred.save(update_fields=['was_correct'])

                checked += 1

                # Trigger downstream updates asynchronously
                if _CELERY_AVAILABLE:
                    _update_accuracy_for_prediction.delay(pred.id)

            except Exception as inner_exc:
                logger.warning(
                    f"check_match_results: failed for prediction {pred.id}: {inner_exc}"
                )

        logger.info(f"check_match_results: checked {checked} predictions")
        return {'checked': checked}

    except Exception as exc:
        logger.error(f"check_match_results task error: {exc}", exc_info=True)
        raise self.retry(exc=exc)


# ─── Task 2: Update team profiles ────────────────────────────────────────────

@shared_task(bind=True, max_retries=2, default_retry_delay=600)
def update_team_profiles(self):
    """
    Runs daily.  For every TeamProfile that hasn't been updated in 24 hours,
    searches the web for recent results and refreshes the stored stats.
    """
    if not LEARNING_ENABLED:
        return {'skipped': True, 'reason': 'LEARNING_ENABLED is False'}

    try:
        from .models import TeamProfile
        from .learning_utils import (
            fetch_team_recent_form,
            detect_tactical_style,
            extract_key_players_from_text,
        )
        from .engine import search_web, _combine_text

        stale_profiles = [p for p in TeamProfile.objects.all() if p.needs_update()]
        updated = 0

        for profile in stale_profiles[:30]:  # cap per run
            try:
                team = profile.team_name
                recent_form = fetch_team_recent_form(team, num_matches=5)

                if recent_form:
                    # Merge new results at the front, keep last 20
                    combined = recent_form + profile.last_20_results
                    profile.last_20_results = combined[:20]

                    # Recompute rolling averages from stored results
                    goals_scored = []
                    goals_conceded = []
                    for r in profile.last_20_results:
                        score = r.get('score', '')
                        if '-' in score:
                            try:
                                hg, ag = map(int, score.split('-'))
                                goals_scored.append(hg)
                                goals_conceded.append(ag)
                            except ValueError:
                                pass

                    if goals_scored:
                        profile.avg_goals_scored = round(
                            sum(goals_scored) / len(goals_scored), 2
                        )
                    if goals_conceded:
                        profile.avg_goals_conceded = round(
                            sum(goals_conceded) / len(goals_conceded), 2
                        )

                # Refresh tactical style from a fresh web search
                tactic_query = f"{team} tactical style formation playing style 2024"
                tactic_results = search_web(tactic_query, max_results=3)
                if tactic_results:
                    tactic_text = _combine_text(tactic_results)
                    detected_style = detect_tactical_style(tactic_text)
                    if detected_style != 'balanced':
                        profile.tactical_style = detected_style

                    # Extract key players
                    players = extract_key_players_from_text(
                        ' '.join(r.get('snippet', '') for r in tactic_results)
                    )
                    if players:
                        profile.key_players = players

                profile.save()
                updated += 1

            except Exception as inner_exc:
                logger.warning(
                    f"update_team_profiles: failed for {profile.team_name}: {inner_exc}"
                )

        logger.info(f"update_team_profiles: updated {updated} profiles")
        return {'updated': updated}

    except Exception as exc:
        logger.error(f"update_team_profiles task error: {exc}", exc_info=True)
        raise self.retry(exc=exc)


# ─── Task 3: Adjust engine weights ───────────────────────────────────────────

@shared_task(bind=True, max_retries=2, default_retry_delay=600)
def adjust_engine_weights(self):
    """
    Runs weekly.  Analyses PredictionResult records grouped by engine and
    match_type, then updates EngineAccuracy.weight_adjustment.

    The adjustment factor is stored but NOT applied to the engine code —
    it is available as a multiplier for callers that opt in via
    LEARNING_ENABLED=True.
    """
    if not LEARNING_ENABLED:
        return {'skipped': True, 'reason': 'LEARNING_ENABLED is False'}

    try:
        from .models import Prediction, PredictionResult, EngineAccuracy
        from .learning_utils import compute_accuracy_pct, compute_weight_adjustment

        # Gather all verified results
        verified = PredictionResult.objects.filter(
            was_correct__isnull=False
        ).select_related('prediction')

        # Group by (engine, match_type)
        groups = {}
        for pr in verified:
            pred = pr.prediction
            engine = pred.engine
            match_type = (
                pred.input_data.get('match_context', {}).get('match_type', 'league')
                or pred.input_data.get('match_type', 'league')
            )
            key = (engine, match_type)
            if key not in groups:
                groups[key] = {'correct': 0, 'total': 0, 'home_c': 0, 'home_t': 0,
                               'away_c': 0, 'away_t': 0, 'draw_c': 0, 'draw_t': 0}
            g = groups[key]
            g['total'] += 1
            if pr.was_correct:
                g['correct'] += 1

            # Break down by home/away/draw
            actual = pr.actual_result.lower()
            home_team = pred.home_team.lower()
            away_team = pred.away_team.lower()
            if actual == home_team:
                g['home_t'] += 1
                if pr.was_correct:
                    g['home_c'] += 1
            elif actual == away_team:
                g['away_t'] += 1
                if pr.was_correct:
                    g['away_c'] += 1
            else:
                g['draw_t'] += 1
                if pr.was_correct:
                    g['draw_c'] += 1

        updated = 0
        for (engine, match_type), g in groups.items():
            # Only update when we have enough data
            if g['total'] < 10:
                continue

            acc = compute_accuracy_pct(g['correct'], g['total'])
            weight = compute_weight_adjustment(acc)

            ea, _ = EngineAccuracy.objects.get_or_create(
                engine=engine, match_type=match_type
            )
            ea.accuracy_pct = acc
            ea.weight_adjustment = weight
            ea.sample_size = g['total']
            ea.home_accuracy = compute_accuracy_pct(g['home_c'], g['home_t'])
            ea.away_accuracy = compute_accuracy_pct(g['away_c'], g['away_t'])
            ea.draw_accuracy = compute_accuracy_pct(g['draw_c'], g['draw_t'])
            ea.save()
            updated += 1

        logger.info(f"adjust_engine_weights: updated {updated} EngineAccuracy records")
        return {'updated': updated}

    except Exception as exc:
        logger.error(f"adjust_engine_weights task error: {exc}", exc_info=True)
        raise self.retry(exc=exc)


# ─── Task 4: Build tactical profiles ─────────────────────────────────────────

@shared_task(bind=True, max_retries=2, default_retry_delay=600)
def build_tactical_profiles(self):
    """
    Runs weekly.  For each team that has at least 5 verified predictions,
    computes per-opponent-style accuracy and stores it in
    TeamProfile.vs_style_accuracy.

    Example output:
        {"high_press": 0.78, "possession": 0.65, "counter_attack": 0.55}
    """
    if not LEARNING_ENABLED:
        return {'skipped': True, 'reason': 'LEARNING_ENABLED is False'}

    try:
        from .models import Prediction, PredictionResult, TeamProfile
        from .learning_utils import compute_accuracy_pct

        verified = PredictionResult.objects.filter(
            was_correct__isnull=False
        ).select_related('prediction')

        # Aggregate per team
        team_stats = {}
        for pr in verified:
            pred = pr.prediction
            for team_name in [pred.home_team, pred.away_team]:
                if not team_name:
                    continue
                if team_name not in team_stats:
                    team_stats[team_name] = {
                        'home': {'c': 0, 't': 0},
                        'away': {'c': 0, 't': 0},
                        'styles': {},
                    }
                ts = team_stats[team_name]

                is_home = team_name == pred.home_team
                bucket = ts['home'] if is_home else ts['away']
                bucket['t'] += 1
                if pr.was_correct:
                    bucket['c'] += 1

                # Opponent tactical style
                opp_style = (
                    pred.input_data.get('away' if is_home else 'home', {})
                    .get('tactical_style', 'balanced')
                )
                if opp_style not in ts['styles']:
                    ts['styles'][opp_style] = {'c': 0, 't': 0}
                ts['styles'][opp_style]['t'] += 1
                if pr.was_correct:
                    ts['styles'][opp_style]['c'] += 1

        updated = 0
        for team_name, stats in team_stats.items():
            total = stats['home']['t'] + stats['away']['t']
            if total < 5:
                continue

            profile, _ = TeamProfile.objects.get_or_create(team_name=team_name)
            profile.home_accuracy = compute_accuracy_pct(
                stats['home']['c'], stats['home']['t']
            )
            profile.away_accuracy = compute_accuracy_pct(
                stats['away']['c'], stats['away']['t']
            )
            profile.vs_style_accuracy = {
                style: compute_accuracy_pct(d['c'], d['t'])
                for style, d in stats['styles'].items()
                if d['t'] >= 3
            }
            profile.sample_size = total
            profile.save()
            updated += 1

        logger.info(f"build_tactical_profiles: updated {updated} TeamProfile records")
        return {'updated': updated}

    except Exception as exc:
        logger.error(f"build_tactical_profiles task error: {exc}", exc_info=True)
        raise self.retry(exc=exc)


# ─── Task 5: Reset daily prediction counters ─────────────────────────────────

@shared_task
def reset_daily_counters():
    """
    Runs daily at midnight.  Resets predictions_today for any user whose
    predictions_date is not today, so their daily quota refreshes.
    """
    try:
        from accounts.models import User
        today = timezone.now().date()
        updated = User.objects.exclude(predictions_date=today).update(predictions_today=0)
        logger.info(f"reset_daily_counters: reset {updated} user counters")
        return {'reset': updated}
    except Exception as exc:
        logger.error(f"reset_daily_counters task error: {exc}", exc_info=True)
        return {'reset': 0, 'error': str(exc)}


# ─── Internal helper task ─────────────────────────────────────────────────────

@shared_task
def _update_accuracy_for_prediction(prediction_id):
    """
    Lightweight task triggered after a PredictionResult is saved.
    Increments the relevant EngineAccuracy sample counter so the weekly
    adjust_engine_weights task has fresh data to work with.
    """
    if not LEARNING_ENABLED:
        return

    try:
        from .models import Prediction, PredictionResult, EngineAccuracy

        pred = Prediction.objects.get(id=prediction_id)
        pr = pred.result_record  # OneToOne reverse accessor

        match_type = (
            pred.input_data.get('match_context', {}).get('match_type', 'league')
            or pred.input_data.get('match_type', 'league')
        )

        ea, _ = EngineAccuracy.objects.get_or_create(
            engine=pred.engine, match_type=match_type
        )
        ea.sample_size += 1
        ea.save(update_fields=['sample_size', 'updated_at'])

    except Exception as e:
        logger.warning(f"_update_accuracy_for_prediction failed: {e}")


# ─── Convenience: queue a deferred result check ───────────────────────────────

def queue_result_check(prediction_id, delay_seconds=3600):
    """
    Queue check_match_results for a specific prediction after `delay_seconds`
    (default 1 hour).  Called from views.py after saving a new prediction.

    Safe to call even when Celery is not available — fails silently.
    """
    if not LEARNING_ENABLED or not _CELERY_AVAILABLE:
        return
    try:
        check_match_results.apply_async(
            kwargs={'prediction_id': prediction_id},
            countdown=delay_seconds,
        )
    except Exception as e:
        logger.warning(f"queue_result_check failed for prediction {prediction_id}: {e}")
