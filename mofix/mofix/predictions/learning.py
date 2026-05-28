"""
learning.py
───────────
High-level service classes for the MatchOracle self-learning system.

These classes wrap the lower-level Celery tasks and utility functions,
providing a clean, testable interface that can be called from views,
management commands, or the Celery tasks themselves.

Classes
-------
ResultChecker   — fetches real match results from the web / Sportmonks
WeightAdjuster  — adjusts EngineAccuracy weight multipliers and logs changes
PatternLearner  — extracts and stores patterns from verified predictions
AccuracyTracker — calculates and summarises accuracy metrics on demand

All classes are designed to fail silently: if the learning system is
unavailable or disabled, the main prediction flow is never interrupted.
"""

import logging
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

LEARNING_ENABLED = getattr(settings, 'LEARNING_ENABLED', False)


# ─── ResultChecker ────────────────────────────────────────────────────────────

class ResultChecker:
    """
    Fetches real match results and stores them as PredictionResult records.

    Usage
    -----
    checker = ResultChecker()
    result  = checker.check_prediction(prediction_id)
    count   = checker.check_pending(max_predictions=50)
    """

    def check_prediction(self, prediction_id):
        """
        Fetch and store the real result for a single Prediction.

        Returns a dict:
            {'found': True, 'was_correct': bool, 'score': '2-1', ...}
        or
            {'found': False, 'reason': '...'}
        """
        if not LEARNING_ENABLED:
            return {'found': False, 'reason': 'LEARNING_ENABLED is False'}

        try:
            from .models import Prediction, PredictionResult
            from .learning_utils import fetch_match_result, score_margin_of_error

            pred = Prediction.objects.get(id=prediction_id)
            if not pred.home_team or not pred.away_team:
                return {'found': False, 'reason': 'Missing team names'}

            result_data = fetch_match_result(pred.home_team, pred.away_team)
            if not result_data or not result_data.get('found'):
                return {'found': False, 'reason': 'Result not found in web search'}

            actual_winner = result_data['winner']
            actual_score  = result_data['score']
            predicted_verdict = pred.predicted_result or pred.output_data.get('verdict', '')

            was_correct = (
                predicted_verdict.lower().strip() == actual_winner.lower().strip()
            )

            predicted_score = pred.output_data.get('predicted_score', '')
            margin = score_margin_of_error(predicted_score, actual_score)

            now = timezone.now()
            pr, created = PredictionResult.objects.update_or_create(
                prediction=pred,
                defaults={
                    'actual_result':      actual_winner,
                    'actual_score':       actual_score,
                    'was_correct':        was_correct,
                    'margin_of_error':    margin,
                    'result_checked_at':  now,
                    'result_source':      result_data.get('source', 'web_search'),
                    'raw_data':           result_data,
                },
            )

            # Mirror correctness onto the Prediction row for quick queries
            pred.was_correct = was_correct
            pred.save(update_fields=['was_correct'])

            logger.info(
                f"ResultChecker: prediction {prediction_id} checked — "
                f"{'correct' if was_correct else 'wrong'} ({actual_score})"
            )
            return {
                'found':       True,
                'was_correct': was_correct,
                'score':       actual_score,
                'winner':      actual_winner,
                'margin':      margin,
                'created':     created,
            }

        except Exception as exc:
            logger.warning(f"ResultChecker.check_prediction({prediction_id}) failed: {exc}")
            return {'found': False, 'reason': str(exc)}

    def check_pending(self, max_predictions=50, days_old_min=2, days_old_max=3):
        """
        Scan for predictions made `days_old_min`–`days_old_max` days ago that
        have no result record yet, and attempt to fill them in.

        Returns {'checked': int, 'found': int, 'errors': int}
        """
        if not LEARNING_ENABLED:
            return {'checked': 0, 'found': 0, 'errors': 0, 'skipped': True}

        try:
            from .models import Prediction
            from django.utils import timezone
            from datetime import timedelta

            now = timezone.now()
            window_start = now - timedelta(days=days_old_max)
            window_end   = now - timedelta(days=days_old_min)

            qs = (
                Prediction.objects
                .filter(
                    created_at__range=(window_start, window_end),
                    engine__in=['A', 'NL'],
                    home_team__gt='',
                    away_team__gt='',
                )
                .exclude(result_record__isnull=False)
                [:max_predictions]
            )

            checked = found = errors = 0
            for pred in qs:
                checked += 1
                outcome = self.check_prediction(pred.id)
                if outcome.get('found'):
                    found += 1
                elif 'reason' in outcome and 'failed' in outcome['reason'].lower():
                    errors += 1

            logger.info(
                f"ResultChecker.check_pending: checked={checked}, found={found}, errors={errors}"
            )
            return {'checked': checked, 'found': found, 'errors': errors}

        except Exception as exc:
            logger.error(f"ResultChecker.check_pending failed: {exc}", exc_info=True)
            return {'checked': 0, 'found': 0, 'errors': 1}

    def check_via_sportmonks(self, home_team, away_team, match_date=None):
        """
        Attempt to fetch a result directly from the Sportmonks API.
        Falls back to web search if the API key is not configured.

        Returns the same dict shape as fetch_match_result.
        """
        api_key = settings.MATCHORACLE.get('FOOTBALL_API_KEY', '')
        if not api_key:
            from .learning_utils import fetch_match_result
            return fetch_match_result(home_team, away_team)

        try:
            import requests as _requests
            from datetime import date, timedelta

            search_date = (
                match_date.strftime('%Y-%m-%d')
                if match_date
                else (date.today() - timedelta(days=2)).strftime('%Y-%m-%d')
            )

            resp = _requests.get(
                f'https://api.sportmonks.com/v3/football/fixtures/date/{search_date}',
                headers={'Authorization': api_key},
                params={'include': 'participants;scores;state', 'per_page': 100},
                timeout=10,
            )
            if resp.status_code != 200:
                raise ValueError(f"Sportmonks returned {resp.status_code}")

            fixtures = resp.json().get('data', [])
            ht_lower = home_team.lower()
            at_lower = away_team.lower()

            for fixture in fixtures:
                parts = fixture.get('participants', [])
                names = [p.get('name', '').lower() for p in parts]
                if (
                    any(ht_lower in n or n in ht_lower for n in names)
                    and any(at_lower in n or n in at_lower for n in names)
                ):
                    scores = fixture.get('scores', [])
                    # Sportmonks score structure: [{score: {participant: 'home', goals: 2}}, ...]
                    hg = ag = 0
                    for s in scores:
                        sc = s.get('score', {})
                        if sc.get('participant') == 'home':
                            hg = sc.get('goals', 0) or 0
                        elif sc.get('participant') == 'away':
                            ag = sc.get('goals', 0) or 0

                    if hg > ag:
                        winner = home_team
                    elif ag > hg:
                        winner = away_team
                    else:
                        winner = 'Draw'

                    return {
                        'found':      True,
                        'home_goals': hg,
                        'away_goals': ag,
                        'score':      f'{hg}-{ag}',
                        'winner':     winner,
                        'source':     'sportmonks',
                    }

        except Exception as exc:
            logger.warning(
                f"ResultChecker.check_via_sportmonks failed for "
                f"{home_team} vs {away_team}: {exc}"
            )

        # Fall back to web search
        from .learning_utils import fetch_match_result
        return fetch_match_result(home_team, away_team)


# ─── WeightAdjuster ───────────────────────────────────────────────────────────

class WeightAdjuster:
    """
    Analyses EngineAccuracy records and adjusts weight multipliers.
    Logs every change to WeightAdjustment for full auditability.

    Usage
    -----
    adjuster = WeightAdjuster()
    report   = adjuster.run()          # full adjustment pass
    adjuster.apply(engine, param, old, new, reason, match_type)
    """

    # Minimum sample size before we trust the accuracy figure
    MIN_SAMPLE = 10

    # How much to shift the weight per accuracy tier
    WEIGHT_MAP = {
        'excellent':  1.08,   # >= 75%
        'good':       1.04,   # >= 65%
        'neutral':    1.00,   # >= 55%
        'poor':       0.96,   # >= 45%
        'bad':        0.92,   # < 45%
    }

    def _accuracy_tier(self, pct):
        if pct >= 75:
            return 'excellent'
        elif pct >= 65:
            return 'good'
        elif pct >= 55:
            return 'neutral'
        elif pct >= 45:
            return 'poor'
        return 'bad'

    def apply(self, engine, parameter, old_weight, new_weight, reason,
              match_type='league', accuracy_before=None):
        """
        Persist a weight change to WeightAdjustment and update EngineAccuracy.
        Returns the WeightAdjustment instance, or None on failure.
        """
        if not LEARNING_ENABLED:
            return None

        try:
            from .models import WeightAdjustment, EngineAccuracy

            wa = WeightAdjustment.objects.create(
                engine=engine,
                parameter=parameter,
                old_weight=old_weight,
                new_weight=new_weight,
                reason=reason,
                match_type=match_type,
                accuracy_before=accuracy_before,
            )

            # Also update the live weight on EngineAccuracy
            ea, _ = EngineAccuracy.objects.get_or_create(
                engine=engine, match_type=match_type
            )
            ea.weight_adjustment = new_weight
            ea.save(update_fields=['weight_adjustment', 'updated_at'])

            logger.info(
                f"WeightAdjuster.apply: {engine}/{parameter} "
                f"{old_weight:.3f} → {new_weight:.3f} ({reason})"
            )
            return wa

        except Exception as exc:
            logger.warning(f"WeightAdjuster.apply failed: {exc}")
            return None

    def run(self):
        """
        Full adjustment pass: reads all EngineAccuracy records with enough
        data and updates their weight_adjustment multiplier.

        Returns {'adjusted': int, 'skipped': int, 'log': [str, ...]}
        """
        if not LEARNING_ENABLED:
            return {'adjusted': 0, 'skipped': 0, 'log': [], 'skipped_reason': 'LEARNING_ENABLED is False'}

        try:
            from .models import EngineAccuracy
            from .learning_utils import compute_weight_adjustment

            records = EngineAccuracy.objects.all()
            adjusted = skipped = 0
            log = []

            for ea in records:
                if ea.sample_size < self.MIN_SAMPLE:
                    skipped += 1
                    continue

                new_weight = compute_weight_adjustment(ea.accuracy_pct)
                old_weight = ea.weight_adjustment

                if abs(new_weight - old_weight) < 0.001:
                    skipped += 1
                    continue

                tier = self._accuracy_tier(ea.accuracy_pct)
                reason = (
                    f"Accuracy {ea.accuracy_pct:.1f}% ({tier}) over "
                    f"{ea.sample_size} predictions for engine {ea.engine}/{ea.match_type}"
                )

                self.apply(
                    engine=ea.engine,
                    parameter='weight_adjustment',
                    old_weight=old_weight,
                    new_weight=new_weight,
                    reason=reason,
                    match_type=ea.match_type,
                    accuracy_before=ea.accuracy_pct,
                )
                adjusted += 1
                log.append(
                    f"{ea.engine}/{ea.match_type}: {old_weight:.3f} → {new_weight:.3f} "
                    f"(acc={ea.accuracy_pct:.1f}%)"
                )

            logger.info(f"WeightAdjuster.run: adjusted={adjusted}, skipped={skipped}")
            return {'adjusted': adjusted, 'skipped': skipped, 'log': log}

        except Exception as exc:
            logger.error(f"WeightAdjuster.run failed: {exc}", exc_info=True)
            return {'adjusted': 0, 'skipped': 0, 'log': [], 'error': str(exc)}

    def get_current_weights(self):
        """
        Return a dict of current weight multipliers keyed by (engine, match_type).
        Falls back to 1.0 for any engine/match_type not yet in the database.
        """
        try:
            from .models import EngineAccuracy
            return {
                (ea.engine, ea.match_type): ea.weight_adjustment
                for ea in EngineAccuracy.objects.all()
            }
        except Exception:
            return {}

    def get_adjustment_history(self, engine=None, limit=50):
        """
        Return recent WeightAdjustment records, optionally filtered by engine.
        Returns a list of dicts.
        """
        try:
            from .models import WeightAdjustment
            qs = WeightAdjustment.objects.all()
            if engine:
                qs = qs.filter(engine=engine.upper())
            return list(
                qs.values(
                    'engine', 'parameter', 'old_weight', 'new_weight',
                    'reason', 'accuracy_before', 'accuracy_after',
                    'match_type', 'applied_at',
                )[:limit]
            )
        except Exception as exc:
            logger.warning(f"WeightAdjuster.get_adjustment_history failed: {exc}")
            return []


# ─── PatternLearner ───────────────────────────────────────────────────────────

class PatternLearner:
    """
    Extracts recurring patterns from verified PredictionResult records and
    stores them in PatternMemory.

    Patterns extracted
    ------------------
    - team:    home/away win rates per team
    - matchup: accuracy per tactical style matchup
    - h2h:     head-to-head historical accuracy
    - condition: match-type-specific accuracy

    Usage
    -----
    learner = PatternLearner()
    report  = learner.run()
    learner.record_team_pattern(team_name, is_home, was_correct)
    learner.record_matchup_pattern(home_style, away_style, was_correct)
    """

    def record_team_pattern(self, team_name, is_home, was_correct, score=None):
        """
        Update the team home/away pattern for a single verified result.
        """
        if not LEARNING_ENABLED or not team_name:
            return

        try:
            from .models import PatternMemory

            venue = 'home' if is_home else 'away'
            key = f"{team_name}_{venue}"
            accuracy_signal = 100.0 if was_correct else 0.0

            pm, created = PatternMemory.objects.get_or_create(
                pattern_type='team',
                pattern_key=key,
                defaults={
                    'pattern_value': {'team': team_name, 'venue': venue, 'wins': 0, 'total': 0},
                    'accuracy': accuracy_signal,
                    'occurrences': 0,
                },
            )

            # Update win/total counters in pattern_value
            pv = pm.pattern_value
            pv['total'] = pv.get('total', 0) + 1
            if was_correct:
                pv['wins'] = pv.get('wins', 0) + 1
            if score:
                pv['last_score'] = score

            pm.merge(new_accuracy=accuracy_signal, new_value=pv)

        except Exception as exc:
            logger.warning(f"PatternLearner.record_team_pattern failed: {exc}")

    def record_matchup_pattern(self, home_style, away_style, was_correct):
        """
        Update the tactical matchup pattern for a single verified result.
        """
        if not LEARNING_ENABLED:
            return

        try:
            from .models import PatternMemory

            key = f"{home_style}_vs_{away_style}"
            accuracy_signal = 100.0 if was_correct else 0.0

            pm, created = PatternMemory.objects.get_or_create(
                pattern_type='matchup',
                pattern_key=key,
                defaults={
                    'pattern_value': {
                        'home_style': home_style,
                        'away_style': away_style,
                        'correct': 0,
                        'total': 0,
                    },
                    'accuracy': accuracy_signal,
                    'occurrences': 0,
                },
            )

            pv = pm.pattern_value
            pv['total'] = pv.get('total', 0) + 1
            if was_correct:
                pv['correct'] = pv.get('correct', 0) + 1

            pm.merge(new_accuracy=accuracy_signal, new_value=pv)

        except Exception as exc:
            logger.warning(f"PatternLearner.record_matchup_pattern failed: {exc}")

    def record_h2h_pattern(self, home_team, away_team, was_correct, actual_winner):
        """
        Update the head-to-head pattern between two specific teams.
        """
        if not LEARNING_ENABLED:
            return

        try:
            from .models import PatternMemory

            # Canonical key: alphabetical order so Arsenal_vs_Chelsea == Chelsea_vs_Arsenal
            teams_sorted = sorted([home_team, away_team])
            key = f"{teams_sorted[0]}_vs_{teams_sorted[1]}"
            accuracy_signal = 100.0 if was_correct else 0.0

            pm, created = PatternMemory.objects.get_or_create(
                pattern_type='h2h',
                pattern_key=key,
                defaults={
                    'pattern_value': {
                        'team_a': teams_sorted[0],
                        'team_b': teams_sorted[1],
                        'results': [],
                    },
                    'accuracy': accuracy_signal,
                    'occurrences': 0,
                },
            )

            pv = pm.pattern_value
            results = pv.get('results', [])
            results.append({'winner': actual_winner, 'correct': was_correct})
            pv['results'] = results[-20:]  # keep last 20

            pm.merge(new_accuracy=accuracy_signal, new_value=pv)

        except Exception as exc:
            logger.warning(f"PatternLearner.record_h2h_pattern failed: {exc}")

    def record_condition_pattern(self, match_type, was_correct):
        """
        Update the match-condition (league/cup/champions/etc.) pattern.
        """
        if not LEARNING_ENABLED:
            return

        try:
            from .models import PatternMemory

            accuracy_signal = 100.0 if was_correct else 0.0

            pm, created = PatternMemory.objects.get_or_create(
                pattern_type='condition',
                pattern_key=f"match_type_{match_type}",
                defaults={
                    'pattern_value': {'match_type': match_type, 'correct': 0, 'total': 0},
                    'accuracy': accuracy_signal,
                    'occurrences': 0,
                },
            )

            pv = pm.pattern_value
            pv['total'] = pv.get('total', 0) + 1
            if was_correct:
                pv['correct'] = pv.get('correct', 0) + 1

            pm.merge(new_accuracy=accuracy_signal, new_value=pv)

        except Exception as exc:
            logger.warning(f"PatternLearner.record_condition_pattern failed: {exc}")

    def run(self, max_records=500):
        """
        Full pattern extraction pass over all verified PredictionResult records.

        Returns {'processed': int, 'patterns_updated': int, 'errors': int}
        """
        if not LEARNING_ENABLED:
            return {'processed': 0, 'patterns_updated': 0, 'errors': 0,
                    'skipped_reason': 'LEARNING_ENABLED is False'}

        try:
            from .models import PredictionResult

            verified = (
                PredictionResult.objects
                .filter(was_correct__isnull=False)
                .select_related('prediction')
                [:max_records]
            )

            processed = errors = 0

            for pr in verified:
                try:
                    pred = pr.prediction
                    was_correct = pr.was_correct

                    # Team patterns
                    if pred.home_team:
                        self.record_team_pattern(
                            pred.home_team, is_home=True,
                            was_correct=was_correct, score=pr.actual_score,
                        )
                    if pred.away_team:
                        self.record_team_pattern(
                            pred.away_team, is_home=False,
                            was_correct=was_correct, score=pr.actual_score,
                        )

                    # Tactical matchup pattern
                    h_style = pred.input_data.get('home', {}).get('tactical_style', 'balanced')
                    a_style = pred.input_data.get('away', {}).get('tactical_style', 'balanced')
                    self.record_matchup_pattern(h_style, a_style, was_correct)

                    # H2H pattern
                    if pred.home_team and pred.away_team:
                        self.record_h2h_pattern(
                            pred.home_team, pred.away_team,
                            was_correct, pr.actual_result,
                        )

                    # Condition pattern
                    match_type = (
                        pred.input_data.get('match_context', {}).get('match_type', 'league')
                        or pred.input_data.get('match_type', 'league')
                    )
                    self.record_condition_pattern(match_type, was_correct)

                    processed += 1

                except Exception as inner_exc:
                    logger.warning(
                        f"PatternLearner.run: error on result {pr.id}: {inner_exc}"
                    )
                    errors += 1

            from .models import PatternMemory
            patterns_updated = PatternMemory.objects.count()

            logger.info(
                f"PatternLearner.run: processed={processed}, "
                f"patterns_updated={patterns_updated}, errors={errors}"
            )
            return {
                'processed': processed,
                'patterns_updated': patterns_updated,
                'errors': errors,
            }

        except Exception as exc:
            logger.error(f"PatternLearner.run failed: {exc}", exc_info=True)
            return {'processed': 0, 'patterns_updated': 0, 'errors': 1, 'error': str(exc)}

    def get_patterns_for_match(self, home_team, away_team,
                               home_style='balanced', away_style='balanced'):
        """
        Retrieve all relevant PatternMemory records for an upcoming match.
        Returns a dict of pattern hints that can be merged into engine input.

        Only returns patterns that have reached their min_sample threshold.
        """
        hints = {}
        try:
            from .models import PatternMemory

            # Team home pattern
            for team, venue in [(home_team, 'home'), (away_team, 'away')]:
                key = f"{team}_{venue}"
                try:
                    pm = PatternMemory.objects.get(pattern_type='team', pattern_key=key)
                    if pm.is_reliable():
                        hints[f"{venue}_team_accuracy"] = pm.accuracy
                        hints[f"{venue}_team_pattern"] = pm.pattern_value
                except PatternMemory.DoesNotExist:
                    pass

            # Tactical matchup
            matchup_key = f"{home_style}_vs_{away_style}"
            try:
                pm = PatternMemory.objects.get(pattern_type='matchup', pattern_key=matchup_key)
                if pm.is_reliable():
                    hints['matchup_accuracy'] = pm.accuracy
                    hints['matchup_pattern'] = pm.pattern_value
            except PatternMemory.DoesNotExist:
                pass

            # H2H
            teams_sorted = sorted([home_team, away_team])
            h2h_key = f"{teams_sorted[0]}_vs_{teams_sorted[1]}"
            try:
                pm = PatternMemory.objects.get(pattern_type='h2h', pattern_key=h2h_key)
                if pm.is_reliable():
                    hints['h2h_accuracy'] = pm.accuracy
                    hints['h2h_pattern'] = pm.pattern_value
            except PatternMemory.DoesNotExist:
                pass

        except Exception as exc:
            logger.warning(f"PatternLearner.get_patterns_for_match failed: {exc}")

        return hints


# ─── AccuracyTracker ──────────────────────────────────────────────────────────

class AccuracyTracker:
    """
    Calculates and summarises accuracy metrics across the system.

    Usage
    -----
    tracker = AccuracyTracker()
    summary = tracker.overall_summary()
    by_eng  = tracker.by_engine('A')
    by_team = tracker.by_team('Arsenal')
    """

    def overall_summary(self):
        """
        Return a high-level accuracy summary across all engines and match types.

        Returns a dict:
            {
                'total_predictions': int,
                'verified_predictions': int,
                'overall_accuracy_pct': float,
                'by_engine': {engine: {'accuracy_pct': float, 'sample': int}, ...},
                'best_engine': str,
                'worst_engine': str,
            }
        """
        try:
            from .models import PredictionResult, Prediction

            total = Prediction.objects.count()
            verified_qs = PredictionResult.objects.filter(was_correct__isnull=False)
            verified = verified_qs.count()

            if verified == 0:
                return {
                    'total_predictions': total,
                    'verified_predictions': 0,
                    'overall_accuracy_pct': 0.0,
                    'by_engine': {},
                    'best_engine': None,
                    'worst_engine': None,
                    'message': 'No verified predictions yet.',
                }

            correct = verified_qs.filter(was_correct=True).count()
            overall_acc = round(correct / verified * 100, 2)

            # Per-engine breakdown
            by_engine = {}
            for pr in verified_qs.select_related('prediction'):
                eng = pr.prediction.engine
                if eng not in by_engine:
                    by_engine[eng] = {'correct': 0, 'total': 0}
                by_engine[eng]['total'] += 1
                if pr.was_correct:
                    by_engine[eng]['correct'] += 1

            engine_summary = {
                eng: {
                    'accuracy_pct': round(d['correct'] / d['total'] * 100, 2),
                    'sample': d['total'],
                }
                for eng, d in by_engine.items()
            }

            best = max(engine_summary, key=lambda e: engine_summary[e]['accuracy_pct'], default=None)
            worst = min(engine_summary, key=lambda e: engine_summary[e]['accuracy_pct'], default=None)

            return {
                'total_predictions':    total,
                'verified_predictions': verified,
                'overall_accuracy_pct': overall_acc,
                'by_engine':            engine_summary,
                'best_engine':          best,
                'worst_engine':         worst,
            }

        except Exception as exc:
            logger.error(f"AccuracyTracker.overall_summary failed: {exc}", exc_info=True)
            return {'error': str(exc)}

    def by_engine(self, engine):
        """
        Return detailed accuracy stats for a single engine, broken down by
        match type, home/away/draw, and recent trend (last 20 predictions).

        Returns a dict or {'error': str} on failure.
        """
        try:
            from .models import EngineAccuracy, PredictionResult

            engine = engine.upper()
            records = list(EngineAccuracy.objects.filter(engine=engine))

            if not records:
                return {
                    'engine': engine,
                    'message': 'No accuracy data yet.',
                    'records': [],
                }

            # Recent trend: last 20 verified predictions for this engine
            recent = (
                PredictionResult.objects
                .filter(was_correct__isnull=False, prediction__engine=engine)
                .order_by('-created_at')
                [:20]
            )
            recent_correct = sum(1 for r in recent if r.was_correct)
            recent_acc = round(recent_correct / max(len(recent), 1) * 100, 2)

            return {
                'engine': engine,
                'recent_accuracy_pct': recent_acc,
                'recent_sample': len(recent),
                'records': [
                    {
                        'match_type':              r.match_type,
                        'accuracy_pct':            r.accuracy_pct,
                        'home_accuracy':           r.home_accuracy,
                        'away_accuracy':           r.away_accuracy,
                        'draw_accuracy':           r.draw_accuracy,
                        'weight_adjustment':       r.weight_adjustment,
                        'tactical_matchup_accuracy': r.tactical_matchup_accuracy,
                        'sample_size':             r.sample_size,
                        'updated_at':              r.updated_at.isoformat(),
                    }
                    for r in records
                ],
            }

        except Exception as exc:
            logger.warning(f"AccuracyTracker.by_engine({engine}) failed: {exc}")
            return {'error': str(exc)}

    def by_team(self, team_name):
        """
        Return accuracy stats for predictions involving a specific team.

        Returns a dict with home/away accuracy and recent form.
        """
        try:
            from .models import TeamProfile, PredictionResult

            try:
                profile = TeamProfile.objects.get(team_name__iexact=team_name)
                profile_data = {
                    'home_accuracy':    profile.home_accuracy,
                    'away_accuracy':    profile.away_accuracy,
                    'vs_style_accuracy': profile.vs_style_accuracy,
                    'sample_size':      profile.sample_size,
                    'tactical_style':   profile.tactical_style,
                    'avg_goals_scored': profile.avg_goals_scored,
                    'avg_goals_conceded': profile.avg_goals_conceded,
                }
            except TeamProfile.DoesNotExist:
                profile_data = None

            # Live calculation from PredictionResult
            home_results = (
                PredictionResult.objects
                .filter(
                    was_correct__isnull=False,
                    prediction__home_team__iexact=team_name,
                )
            )
            away_results = (
                PredictionResult.objects
                .filter(
                    was_correct__isnull=False,
                    prediction__away_team__iexact=team_name,
                )
            )

            home_total   = home_results.count()
            home_correct = home_results.filter(was_correct=True).count()
            away_total   = away_results.count()
            away_correct = away_results.filter(was_correct=True).count()

            return {
                'team_name':       team_name,
                'home_accuracy':   round(home_correct / max(home_total, 1) * 100, 2),
                'away_accuracy':   round(away_correct / max(away_total, 1) * 100, 2),
                'home_sample':     home_total,
                'away_sample':     away_total,
                'total_sample':    home_total + away_total,
                'profile':         profile_data,
            }

        except Exception as exc:
            logger.warning(f"AccuracyTracker.by_team({team_name}) failed: {exc}")
            return {'error': str(exc)}

    def recent_trend(self, days=7, engine=None):
        """
        Return accuracy for predictions made in the last `days` days.
        Optionally filter by engine.

        Returns {'accuracy_pct': float, 'correct': int, 'total': int, 'period_days': int}
        """
        try:
            from .models import PredictionResult
            from datetime import timedelta

            since = timezone.now() - timedelta(days=days)
            qs = PredictionResult.objects.filter(
                was_correct__isnull=False,
                created_at__gte=since,
            )
            if engine:
                qs = qs.filter(prediction__engine=engine.upper())

            total   = qs.count()
            correct = qs.filter(was_correct=True).count()

            return {
                'accuracy_pct': round(correct / max(total, 1) * 100, 2),
                'correct':      correct,
                'total':        total,
                'period_days':  days,
                'engine':       engine,
            }

        except Exception as exc:
            logger.warning(f"AccuracyTracker.recent_trend failed: {exc}")
            return {'error': str(exc)}
