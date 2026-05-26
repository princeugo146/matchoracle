"""
learning_utils.py
─────────────────
Helper functions used by the self-learning Celery tasks.
All functions are pure utilities — no Django ORM calls here so they can be
tested in isolation and reused freely.
"""

import re
import logging
from .engine import search_web, _combine_text

logger = logging.getLogger(__name__)


# ─── Result Parsing ───────────────────────────────────────────────────────────

def parse_match_result_from_text(text, home_team, away_team):
    """
    Attempt to extract a final score and winner from a block of text
    (typically assembled from DuckDuckGo search snippets).

    Returns a dict:
        {
            "home_goals": int,
            "away_goals": int,
            "score": "2-1",
            "winner": "Arsenal" | "Chelsea" | "Draw",
            "found": True | False,
        }
    or None if nothing could be parsed.
    """
    text_lower = text.lower()
    ht = home_team.lower()
    at = away_team.lower()

    # Pattern: "Arsenal 2-1 Chelsea" or "Arsenal 2 - 1 Chelsea"
    score_pat = re.compile(
        r'(\d)\s*[-–]\s*(\d)',
        re.IGNORECASE,
    )
    matches = score_pat.findall(text_lower)
    if not matches:
        return None

    # Take the first score found near either team name
    for hg_str, ag_str in matches:
        hg, ag = int(hg_str), int(ag_str)
        if hg > ag:
            winner = home_team
        elif ag > hg:
            winner = away_team
        else:
            winner = 'Draw'
        return {
            'home_goals': hg,
            'away_goals': ag,
            'score': f'{hg}-{ag}',
            'winner': winner,
            'found': True,
        }

    return None


def fetch_match_result(home_team, away_team):
    """
    Search the web for the final result of a match between home_team and away_team.
    Returns the same dict as parse_match_result_from_text, or None on failure.
    """
    query = f"{home_team} vs {away_team} final score result"
    try:
        results = search_web(query, max_results=5)
        if not results:
            return None
        text = _combine_text(results)
        return parse_match_result_from_text(text, home_team, away_team)
    except Exception as e:
        logger.warning(f"fetch_match_result failed for {home_team} vs {away_team}: {e}")
        return None


def fetch_team_recent_form(team_name, num_matches=5):
    """
    Search the web for a team's recent results.
    Returns a list of result dicts:
        [{"opponent": "Chelsea", "result": "W", "score": "2-1", "competition": "league"}, ...]
    """
    query = f"{team_name} last {num_matches} matches results scores 2024"
    try:
        results = search_web(query, max_results=5)
        if not results:
            return []
        text = _combine_text(results)
        return _parse_form_from_text(text, team_name)
    except Exception as e:
        logger.warning(f"fetch_team_recent_form failed for {team_name}: {e}")
        return []


def _parse_form_from_text(text, team_name):
    """
    Extract a list of recent results from a text blob.
    Returns a list of dicts with keys: result (W/D/L), score, opponent.
    """
    form_results = []
    team_lower = team_name.lower()

    # Look for score patterns like "2-1", "0-0", "3-2"
    score_pat = re.compile(r'(\d)\s*[-–]\s*(\d)')
    scores = score_pat.findall(text)

    # Look for win/draw/loss keywords near the team name
    win_pat = re.compile(r'(?:beat|defeated|won|victory)\s+([a-z\s]{3,25})', re.IGNORECASE)
    draw_pat = re.compile(r'(?:drew|draw|shared)\s+(?:with\s+)?([a-z\s]{3,25})', re.IGNORECASE)
    loss_pat = re.compile(r'(?:lost|defeated by|beaten by)\s+([a-z\s]{3,25})', re.IGNORECASE)

    wins = win_pat.findall(text)
    draws = draw_pat.findall(text)
    losses = loss_pat.findall(text)

    for i, opp in enumerate(wins[:5]):
        score = f"{scores[i][0]}-{scores[i][1]}" if i < len(scores) else '1-0'
        form_results.append({'result': 'W', 'score': score, 'opponent': opp.strip().title()})

    for i, opp in enumerate(draws[:3]):
        idx = len(wins) + i
        score = f"{scores[idx][0]}-{scores[idx][1]}" if idx < len(scores) else '0-0'
        form_results.append({'result': 'D', 'score': score, 'opponent': opp.strip().title()})

    for i, opp in enumerate(losses[:3]):
        idx = len(wins) + len(draws) + i
        score = f"{scores[idx][0]}-{scores[idx][1]}" if idx < len(scores) else '0-1'
        form_results.append({'result': 'L', 'score': score, 'opponent': opp.strip().title()})

    return form_results[:10]


# ─── Accuracy Calculation ─────────────────────────────────────────────────────

def compute_accuracy_pct(correct, total):
    """Return accuracy as a float 0–100, or 0.0 if total is zero."""
    if total == 0:
        return 0.0
    return round((correct / total) * 100, 2)


def compute_weight_adjustment(accuracy_pct):
    """
    Derive a confidence multiplier from an accuracy percentage.

    Mapping:
        >= 70%  → 1.05  (slight boost — engine is reliable)
        60–69%  → 1.00  (neutral)
        50–59%  → 0.97  (slight penalty)
        < 50%   → 0.93  (meaningful penalty — engine is underperforming)
    """
    if accuracy_pct >= 70:
        return 1.05
    elif accuracy_pct >= 60:
        return 1.00
    elif accuracy_pct >= 50:
        return 0.97
    else:
        return 0.93


def score_margin_of_error(predicted_score, actual_score):
    """
    Calculate the absolute goal-difference error between two score strings.
    e.g. predicted "2-1", actual "3-0" → |2-3| + |1-0| = 2

    Returns a float, or None if either score is unparseable.
    """
    try:
        ph, pa = map(int, predicted_score.split('-'))
        ah, aa = map(int, actual_score.split('-'))
        return float(abs(ph - ah) + abs(pa - aa))
    except Exception:
        return None


# ─── Tactical Style Detection ─────────────────────────────────────────────────

TACTICAL_KEYWORDS = {
    'high_press': ['press', 'pressing', 'gegenpressing', 'high press', 'intense press'],
    'counter_attack': ['counter', 'counter-attack', 'on the break', 'transition'],
    'possession': ['possession', 'tiki-taka', 'build-up', 'ball retention'],
    'defensive_block': ['defensive', 'low block', 'park the bus', 'deep defence'],
    'wing_play': ['wing', 'wide play', 'crosses', 'overlapping full-backs'],
    'long_ball': ['long ball', 'direct', 'aerial', 'target man'],
}


def detect_tactical_style(text):
    """
    Scan a text blob for tactical keywords and return the most-mentioned style.
    Falls back to 'balanced' if nothing is detected.
    """
    text_lower = text.lower()
    counts = {style: 0 for style in TACTICAL_KEYWORDS}
    for style, keywords in TACTICAL_KEYWORDS.items():
        for kw in keywords:
            counts[style] += text_lower.count(kw)

    best_style = max(counts, key=counts.get)
    if counts[best_style] == 0:
        return 'balanced'
    return best_style


def extract_key_players_from_text(text):
    """
    Extract player names from a text blob using a simple heuristic:
    capitalised words that appear near football action verbs.
    Returns a list of up to 5 name strings.
    """
    # Look for "Player Name scored/assisted/saved/..."
    action_pat = re.compile(
        r'([A-Z][a-z]+ (?:[A-Z][a-z]+ )?)'
        r'(?:scored|assisted|saved|netted|struck|headed|converted)',
    )
    names = action_pat.findall(text)
    seen = []
    for name in names:
        name = name.strip()
        if name and name not in seen:
            seen.append(name)
        if len(seen) >= 5:
            break
    return seen


# ─── Session ID Helpers ───────────────────────────────────────────────────────

def make_session_id(request):
    """
    Derive a stable session identifier from a Django request.
    Uses the Django session key if available, otherwise falls back to
    a hash of the user-agent + IP.
    """
    if hasattr(request, 'session') and request.session.session_key:
        return request.session.session_key[:64]
    ua = request.META.get('HTTP_USER_AGENT', '')
    ip = request.META.get('REMOTE_ADDR', '')
    import hashlib
    return hashlib.sha256(f"{ip}:{ua}".encode()).hexdigest()[:64]
