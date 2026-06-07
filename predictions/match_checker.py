"""
predictions/match_checker.py
─────────────────────────────
Internet match fetcher for post-match verification and self-learning.

Fetches real match results from multiple sources (Sportmonks API, ESPN,
API-Football, DuckDuckGo web search) and compares them against stored
predictions to calculate accuracy metrics and feed the learning system.

Public API
----------
MatchChecker.fetch_result(home_team, away_team, match_date=None)
    → {'found': bool, 'score': '2-1', 'winner': 'Arsenal', 'source': '...'}

MatchChecker.verify_prediction(prediction_id)
    → {'found': bool, 'was_correct': bool, 'score': '...', ...}

MatchChecker.run_batch(max_predictions=50)
    → {'checked': int, 'found': int, 'correct': int, 'errors': int}

AccuracyMetrics.calculate(engine=None, match_type=None)
    → {'total': int, 'correct': int, 'accuracy_pct': float, ...}
"""

import re
import logging
import requests
from datetime import date, timedelta
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

# ── Source priority order ─────────────────────────────────────────────────────
_SOURCES = ['sportmonks', 'api_football', 'espn', 'web_search']


class MatchChecker:
    """
    Fetches real match results and verifies stored predictions.

    Usage
    -----
    checker = MatchChecker()
    result  = checker.fetch_result('Arsenal', 'Chelsea')
    report  = checker.run_batch(max_predictions=50)
    """

    # ── Public: fetch a single result ────────────────────────────────────────

    def fetch_result(self, home_team, away_team, match_date=None):
        """
        Try each data source in priority order until a result is found.

        Parameters
        ----------
        home_team  : str
        away_team  : str
        match_date : date | None  — defaults to yesterday

        Returns
        -------
        dict with keys: found, score, home_goals, away_goals, winner, source
        or {'found': False, 'reason': '...'}
        """
        if match_date is None:
            match_date = date.today() - timedelta(days=1)

        for source in _SOURCES:
            try:
                result = getattr(self, f'_fetch_{source}')(
                    home_team, away_team, match_date
                )
                if result and result.get('found'):
                    logger.info(
                        f"MatchChecker: found {home_team} vs {away_team} "
                        f"via {source}: {result.get('score')}"
                    )
                    return result
            except Exception as e:
                logger.debug(f"MatchChecker._fetch_{source} failed: {e}")

        return {'found': False, 'reason': 'No result found in any source'}

    # ── Public: verify a single stored prediction ─────────────────────────────

    def verify_prediction(self, prediction_id):
        """
        Fetch the real result for a stored Prediction and update
        PredictionResult accordingly.

        Returns
        -------
        dict: {'found': bool, 'was_correct': bool, 'score': str, ...}
        """
        try:
            from .models import Prediction, PredictionResult
            from .learning_utils import score_margin_of_error

            pred = Prediction.objects.get(id=prediction_id)
            if not pred.home_team or not pred.away_team:
                return {'found': False, 'reason': 'Missing team names'}

            match_date = pred.created_at.date() + timedelta(days=1)
            result_data = self.fetch_result(
                pred.home_team, pred.away_team, match_date
            )

            if not result_data.get('found'):
                return result_data

            actual_winner = result_data['winner']
            actual_score = result_data['score']
            predicted_verdict = (
                pred.predicted_result
                or pred.output_data.get('verdict', '')
                or pred.output_data.get('prediction', '')
            )

            was_correct = (
                predicted_verdict.lower().strip() == actual_winner.lower().strip()
            )

            predicted_score = pred.output_data.get('predicted_score', '')
            margin = score_margin_of_error(predicted_score, actual_score)

            now = timezone.now()
            PredictionResult.objects.update_or_create(
                prediction=pred,
                defaults={
                    'actual_result': actual_winner,
                    'actual_score': actual_score,
                    'was_correct': was_correct,
                    'margin_of_error': margin,
                    'result_checked_at': now,
                    'result_source': result_data.get('source', 'web_search'),
                    'raw_data': result_data,
                },
            )

            pred.was_correct = was_correct
            pred.save(update_fields=['was_correct'])

            # Feed the pattern learner
            self._record_patterns(pred, was_correct, actual_score)

            return {
                'found': True,
                'was_correct': was_correct,
                'score': actual_score,
                'winner': actual_winner,
                'margin': margin,
                'source': result_data.get('source'),
            }

        except Exception as e:
            logger.warning(f"MatchChecker.verify_prediction({prediction_id}): {e}")
            return {'found': False, 'reason': str(e)}

    # ── Public: batch verification ────────────────────────────────────────────

    def run_batch(self, max_predictions=50, days_old_min=2, days_old_max=3):
        """
        Find unverified predictions from `days_old_min`–`days_old_max` days ago
        and attempt to verify each one.

        Returns
        -------
        {'checked': int, 'found': int, 'correct': int, 'errors': int}
        """
        try:
            from .models import Prediction

            now = timezone.now()
            window_start = now - timedelta(days=days_old_max)
            window_end = now - timedelta(days=days_old_min)

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

            checked = found = correct = errors = 0
            for pred in qs:
                checked += 1
                try:
                    outcome = self.verify_prediction(pred.id)
                    if outcome.get('found'):
                        found += 1
                        if outcome.get('was_correct'):
                            correct += 1
                    elif 'reason' in outcome and 'failed' in str(outcome.get('reason', '')).lower():
                        errors += 1
                except Exception as inner:
                    logger.warning(f"MatchChecker.run_batch inner error for {pred.id}: {inner}")
                    errors += 1

            logger.info(
                f"MatchChecker.run_batch: checked={checked}, found={found}, "
                f"correct={correct}, errors={errors}"
            )
            return {'checked': checked, 'found': found, 'correct': correct, 'errors': errors}

        except Exception as e:
            logger.error(f"MatchChecker.run_batch failed: {e}", exc_info=True)
            return {'checked': 0, 'found': 0, 'correct': 0, 'errors': 1}

    # ── Private: data source fetchers ─────────────────────────────────────────

    def _fetch_sportmonks(self, home_team, away_team, match_date):
        api_key = settings.MATCHORACLE.get('FOOTBALL_API_KEY', '')
        if not api_key:
            return None

        date_str = match_date.strftime('%Y-%m-%d')
        resp = requests.get(
            f'https://api.sportmonks.com/v3/football/fixtures/date/{date_str}',
            headers={'Authorization': api_key},
            params={'include': 'participants;scores;state', 'per_page': 100},
            timeout=10,
        )
        if resp.status_code != 200:
            return None

        fixtures = resp.json().get('data', [])
        return self._match_fixture_in_list(fixtures, home_team, away_team, 'sportmonks')

    def _fetch_api_football(self, home_team, away_team, match_date):
        """
        Try api-football.com (RapidAPI) if RAPIDAPI_KEY is configured.
        """
        api_key = settings.MATCHORACLE.get('RAPIDAPI_KEY', '')
        if not api_key:
            return None

        date_str = match_date.strftime('%Y-%m-%d')
        resp = requests.get(
            'https://api-football-v1.p.rapidapi.com/v3/fixtures',
            headers={
                'X-RapidAPI-Key': api_key,
                'X-RapidAPI-Host': 'api-football-v1.p.rapidapi.com',
            },
            params={'date': date_str},
            timeout=10,
        )
        if resp.status_code != 200:
            return None

        fixtures = resp.json().get('response', [])
        ht_lower = home_team.lower()
        at_lower = away_team.lower()

        for f in fixtures:
            teams = f.get('teams', {})
            h_name = teams.get('home', {}).get('name', '').lower()
            a_name = teams.get('away', {}).get('name', '').lower()
            if (ht_lower in h_name or h_name in ht_lower) and \
               (at_lower in a_name or a_name in at_lower):
                goals = f.get('goals', {})
                hg = goals.get('home') or 0
                ag = goals.get('away') or 0
                winner = home_team if hg > ag else (away_team if ag > hg else 'Draw')
                return {
                    'found': True,
                    'home_goals': hg,
                    'away_goals': ag,
                    'score': f'{hg}-{ag}',
                    'winner': winner,
                    'source': 'api_football',
                }
        return None

    def _fetch_espn(self, home_team, away_team, match_date):
        """
        Try ESPN's public scoreboard API (no key required).
        """
        date_str = match_date.strftime('%Y%m%d')
        try:
            resp = requests.get(
                f'https://site.api.espn.com/apis/site/v2/sports/soccer/all/scoreboard',
                params={'dates': date_str},
                timeout=8,
            )
            if resp.status_code != 200:
                return None

            events = resp.json().get('events', [])
            ht_lower = home_team.lower()
            at_lower = away_team.lower()

            for event in events:
                competitors = event.get('competitions', [{}])[0].get('competitors', [])
                names = [c.get('team', {}).get('displayName', '').lower() for c in competitors]
                if any(ht_lower in n or n in ht_lower for n in names) and \
                   any(at_lower in n or n in at_lower for n in names):
                    scores = {
                        c.get('homeAway'): int(c.get('score', 0) or 0)
                        for c in competitors
                    }
                    hg = scores.get('home', 0)
                    ag = scores.get('away', 0)
                    winner = home_team if hg > ag else (away_team if ag > hg else 'Draw')
                    return {
                        'found': True,
                        'home_goals': hg,
                        'away_goals': ag,
                        'score': f'{hg}-{ag}',
                        'winner': winner,
                        'source': 'espn',
                    }
        except Exception:
            pass
        return None

    def _fetch_web_search(self, home_team, away_team, match_date):
        """
        Fall back to DuckDuckGo web search result parsing.
        """
        from .learning_utils import fetch_match_result
        result = fetch_match_result(home_team, away_team)
        if result and result.get('found'):
            result['source'] = 'web_search'
        return result

    # ── Private: Sportmonks fixture matcher ───────────────────────────────────

    def _match_fixture_in_list(self, fixtures, home_team, away_team, source):
        ht_lower = home_team.lower()
        at_lower = away_team.lower()

        for fixture in fixtures:
            parts = fixture.get('participants', [])
            names = [p.get('name', '').lower() for p in parts]
            if (any(ht_lower in n or n in ht_lower for n in names) and
                    any(at_lower in n or n in at_lower for n in names)):
                scores = fixture.get('scores', [])
                hg = ag = 0
                for s in scores:
                    sc = s.get('score', {})
                    if sc.get('participant') == 'home':
                        hg = sc.get('goals', 0) or 0
                    elif sc.get('participant') == 'away':
                        ag = sc.get('goals', 0) or 0

                winner = home_team if hg > ag else (away_team if ag > hg else 'Draw')
                return {
                    'found': True,
                    'home_goals': hg,
                    'away_goals': ag,
                    'score': f'{hg}-{ag}',
                    'winner': winner,
                    'source': source,
                }
        return None

    # ── Private: pattern recording ────────────────────────────────────────────

    def _record_patterns(self, pred, was_correct, actual_score):
        """Feed verified result into the PatternLearner (silent on failure)."""
        try:
            from .learning import PatternLearner
            learner = PatternLearner()
            home_style = pred.input_data.get('home', {}).get('tactical_style', 'balanced')
            away_style = pred.input_data.get('away', {}).get('tactical_style', 'balanced')
            learner.record_team_pattern(pred.home_team, True, was_correct, actual_score)
            learner.record_team_pattern(pred.away_team, False, was_correct, actual_score)
            learner.record_matchup_pattern(home_style, away_style, was_correct)
        except Exception as e:
            logger.debug(f"MatchChecker._record_patterns failed: {e}")


# ── Accuracy Metrics ──────────────────────────────────────────────────────────

class AccuracyMetrics:
    """
    Read-only accuracy calculator.  Does not write to the database.

    Usage
    -----
    metrics = AccuracyMetrics()
    summary = metrics.calculate()
    engine_stats = metrics.calculate(engine='A')
    wc_stats = metrics.calculate(match_type='worldcup')
    """

    def calculate(self, engine=None, match_type=None):
        """
        Calculate accuracy metrics, optionally filtered by engine and/or match_type.

        Returns
        -------
        {
            'total': int,
            'correct': int,
            'accuracy_pct': float,
            'home_accuracy': float,
            'away_accuracy': float,
            'draw_accuracy': float,
            'by_engine': dict,          # only when engine is None
            'by_match_type': dict,      # only when match_type is None
        }
        """
        try:
            from .models import PredictionResult

            qs = PredictionResult.objects.filter(was_correct__isnull=False)
            if engine:
                qs = qs.filter(prediction__engine=engine.upper())
            if match_type:
                qs = qs.filter(
                    prediction__input_data__match_context__match_type=match_type
                )

            qs = qs.select_related('prediction')
            total = qs.count()
            correct = qs.filter(was_correct=True).count()
            accuracy = round(correct / total * 100, 2) if total else 0.0

            # Home / away / draw breakdown
            home_c = home_t = away_c = away_t = draw_c = draw_t = 0
            by_engine = {}
            by_match_type = {}

            for pr in qs:
                pred = pr.prediction
                actual = pr.actual_result.lower()
                ht = pred.home_team.lower()
                at = pred.away_team.lower()

                if actual == ht:
                    home_t += 1
                    if pr.was_correct:
                        home_c += 1
                elif actual == at:
                    away_t += 1
                    if pr.was_correct:
                        away_c += 1
                else:
                    draw_t += 1
                    if pr.was_correct:
                        draw_c += 1

                # By engine
                eng = pred.engine
                if eng not in by_engine:
                    by_engine[eng] = {'total': 0, 'correct': 0}
                by_engine[eng]['total'] += 1
                if pr.was_correct:
                    by_engine[eng]['correct'] += 1

                # By match type
                mt = (
                    pred.input_data.get('match_context', {}).get('match_type')
                    or pred.input_data.get('match_type', 'league')
                )
                if mt not in by_match_type:
                    by_match_type[mt] = {'total': 0, 'correct': 0}
                by_match_type[mt]['total'] += 1
                if pr.was_correct:
                    by_match_type[mt]['correct'] += 1

            def _pct(c, t):
                return round(c / t * 100, 2) if t else 0.0

            for d in list(by_engine.values()) + list(by_match_type.values()):
                d['accuracy_pct'] = _pct(d['correct'], d['total'])

            result = {
                'total': total,
                'correct': correct,
                'accuracy_pct': accuracy,
                'home_accuracy': _pct(home_c, home_t),
                'away_accuracy': _pct(away_c, away_t),
                'draw_accuracy': _pct(draw_c, draw_t),
            }
            if not engine:
                result['by_engine'] = by_engine
            if not match_type:
                result['by_match_type'] = by_match_type

            return result

        except Exception as e:
            logger.warning(f"AccuracyMetrics.calculate failed: {e}")
            return {
                'total': 0, 'correct': 0, 'accuracy_pct': 0.0,
                'home_accuracy': 0.0, 'away_accuracy': 0.0, 'draw_accuracy': 0.0,
            }

    def world_cup_accuracy(self):
        """Shortcut: accuracy for World Cup / knockout / final match types."""
        results = {}
        for mt in ('worldcup', 'knockout', 'semifinal', 'final', 'group'):
            results[mt] = self.calculate(match_type=mt)
        return results

    def tactical_matchup_accuracy(self):
        """
        Return accuracy grouped by tactical matchup (home_style vs away_style).
        Reads from PatternMemory for efficiency.
        """
        try:
            from .models import PatternMemory
            patterns = PatternMemory.objects.filter(
                pattern_type='matchup'
            ).order_by('-occurrences')
            return [
                {
                    'matchup': p.pattern_key,
                    'accuracy': p.accuracy,
                    'occurrences': p.occurrences,
                    'reliable': p.is_reliable(),
                    'value': p.pattern_value,
                }
                for p in patterns
            ]
        except Exception as e:
            logger.warning(f"AccuracyMetrics.tactical_matchup_accuracy failed: {e}")
            return []
