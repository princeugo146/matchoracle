"""
predictions/news.py
───────────────────
Real-time news and standings fetcher for Smart AI.
Uses DuckDuckGo web search (no API key required) and Sportmonks API
to pull current team news, standings, and recent results.
"""

import re
import logging
from datetime import date, datetime

import requests
from django.conf import settings

from .engine import search_web, _cache_get, _cache_set

logger = logging.getLogger(__name__)


# ─── Team News ────────────────────────────────────────────────────────────────

def fetch_team_news(team_name, max_results=3):
    """
    Fetch the latest news about a football team via DuckDuckGo.
    Returns a list of dicts: [{title, snippet, url}, …]
    """
    today_year = datetime.now().year
    query = f"{team_name} football news latest {today_year}"
    cached = _cache_get(f"news:{team_name}")
    if cached is not None:
        return cached

    results = search_web(query, max_results=max_results + 2)
    # Filter out irrelevant results
    filtered = [
        r for r in results
        if team_name.lower().split()[0] in (r.get('title', '') + r.get('snippet', '')).lower()
    ][:max_results]

    _cache_set(f"news:{team_name}", filtered)
    return filtered


# ─── Recent Results ───────────────────────────────────────────────────────────

def fetch_recent_results(team_name, max_results=3):
    """
    Fetch a team's recent match results via web search.
    Returns a list of result snippet strings.
    """
    today_year = datetime.now().year
    query = f"{team_name} recent results last 5 matches {today_year}"
    cached = _cache_get(f"results:{team_name}")
    if cached is not None:
        return cached

    results = search_web(query, max_results=max_results + 2)
    snippets = [r.get('snippet', '') for r in results if r.get('snippet')][:max_results]
    _cache_set(f"results:{team_name}", snippets)
    return snippets


# ─── Competition Standings ────────────────────────────────────────────────────

def fetch_competition_standings(competition_name):
    """
    Fetch current standings for a competition via web search.
    Returns a list of snippet strings describing the table.
    """
    today_year = datetime.now().year
    query = f"{competition_name} standings table {today_year} current"
    cached = _cache_get(f"standings:{competition_name}")
    if cached is not None:
        return cached

    results = search_web(query, max_results=3)
    snippets = [r.get('snippet', '') for r in results if r.get('snippet')][:3]
    _cache_set(f"standings:{competition_name}", snippets)
    return snippets


def fetch_champions_league_standings():
    """Fetch current Champions League table."""
    return fetch_competition_standings("UEFA Champions League")


def fetch_premier_league_standings():
    """Fetch current Premier League table."""
    return fetch_competition_standings("Premier League")


def fetch_la_liga_standings():
    """Fetch current La Liga table."""
    return fetch_competition_standings("La Liga")


# ─── Sportmonks Live Matches ──────────────────────────────────────────────────

def fetch_live_matches():
    """
    Fetch live matches from Sportmonks API.
    Uses SPORTMONKS_API_KEY (stored as FOOTBALL_API_KEY in settings).
    Returns a list of match dicts.
    """
    api_key = settings.MATCHORACLE.get('FOOTBALL_API_KEY', '')
    if not api_key:
        logger.debug("No Sportmonks API key — skipping live matches fetch")
        return []

    cached = _cache_get('live_matches_sportmonks')
    if cached is not None:
        return cached

    try:
        resp = requests.get(
            'https://api.sportmonks.com/v3/football/livescores/inplay',
            headers={'Authorization': api_key},
            params={'include': 'participants;scores;state;league', 'per_page': 50},
            timeout=10,
        )
        if resp.status_code != 200:
            logger.warning(f"Sportmonks live matches returned {resp.status_code}")
            return []

        raw = resp.json().get('data', [])
        matches = []
        for m in raw:
            try:
                parts = m.get('participants', [])
                home = next((p for p in parts if p.get('meta', {}).get('location') == 'home'), {})
                away = next((p for p in parts if p.get('meta', {}).get('location') == 'away'), {})
                scores = m.get('scores', [])
                hs = next(
                    (s.get('score', {}).get('goals')
                     for s in scores
                     if s.get('description') == 'CURRENT'
                     and s.get('score', {}).get('participant') == 'home'),
                    None
                )
                as_ = next(
                    (s.get('score', {}).get('goals')
                     for s in scores
                     if s.get('description') == 'CURRENT'
                     and s.get('score', {}).get('participant') == 'away'),
                    None
                )
                state = m.get('state', {})
                matches.append({
                    'id': m.get('id'),
                    'home_team': home.get('name', 'Home'),
                    'away_team': away.get('name', 'Away'),
                    'home_logo': home.get('image_path', ''),
                    'away_logo': away.get('image_path', ''),
                    'home_score': hs,
                    'away_score': as_,
                    'minute': m.get('minute'),
                    'status': state.get('short_name', 'LIVE'),
                    'status_long': state.get('name', 'Live'),
                    'league': m.get('league', {}).get('name', ''),
                })
            except Exception:
                continue

        _cache_set('live_matches_sportmonks', matches)
        return matches

    except Exception as e:
        logger.error(f"Sportmonks live matches error: {e}")
        return []


# ─── Todays Fixtures ──────────────────────────────────────────────────────────

def fetch_todays_fixtures():
    """
    Fetch today's scheduled fixtures from Sportmonks.
    Returns a list of fixture dicts.
    """
    api_key = settings.MATCHORACLE.get('FOOTBALL_API_KEY', '')
    if not api_key:
        return []

    cached = _cache_get('todays_fixtures')
    if cached is not None:
        return cached

    try:
        today = date.today().strftime('%Y-%m-%d')
        resp = requests.get(
            f'https://api.sportmonks.com/v3/football/fixtures/date/{today}',
            headers={'Authorization': api_key},
            params={'include': 'participants;scores;state;league', 'per_page': 100},
            timeout=10,
        )
        if resp.status_code != 200:
            return []

        raw = resp.json().get('data', [])
        fixtures = []
        for f in raw:
            try:
                parts = f.get('participants', [])
                home = next((p for p in parts if p.get('meta', {}).get('location') == 'home'), {})
                away = next((p for p in parts if p.get('meta', {}).get('location') == 'away'), {})
                scores = f.get('scores', [])
                hs = next(
                    (s.get('score', {}).get('goals')
                     for s in scores
                     if s.get('description') == 'CURRENT'
                     and s.get('score', {}).get('participant') == 'home'),
                    None
                )
                as_ = next(
                    (s.get('score', {}).get('goals')
                     for s in scores
                     if s.get('description') == 'CURRENT'
                     and s.get('score', {}).get('participant') == 'away'),
                    None
                )
                state = f.get('state', {})
                fixtures.append({
                    'id': f.get('id'),
                    'home_team': home.get('name', 'Home'),
                    'away_team': away.get('name', 'Away'),
                    'home_logo': home.get('image_path', ''),
                    'away_logo': away.get('image_path', ''),
                    'home_score': hs,
                    'away_score': as_,
                    'minute': f.get('minute'),
                    'status': state.get('short_name', 'NS'),
                    'status_long': state.get('name', 'Not Started'),
                    'league': f.get('league', {}).get('name', ''),
                    'starting_at': f.get('starting_at', ''),
                })
            except Exception:
                continue

        _cache_set('todays_fixtures', fixtures)
        return fixtures

    except Exception as e:
        logger.error(f"Todays fixtures error: {e}")
        return []


# ─── Context Builder ──────────────────────────────────────────────────────────

def build_match_context(home_team, away_team, competition=''):
    """
    Build a rich context string for a match by fetching:
    - Latest news about both teams
    - Recent results for both teams
    - Competition standings (if competition provided)

    Returns a formatted string ready to inject into an AI prompt.
    """
    today = datetime.now().strftime('%B %d, %Y')
    lines = [f"=== CURRENT INFORMATION (as of {today}) ===\n"]

    # Home team news
    home_news = fetch_team_news(home_team)
    if home_news:
        lines.append(f"📰 {home_team} latest news:")
        for n in home_news:
            snippet = n.get('snippet', '')
            if snippet:
                lines.append(f"  • {snippet[:200]}")
        lines.append("")

    # Away team news
    away_news = fetch_team_news(away_team)
    if away_news:
        lines.append(f"📰 {away_team} latest news:")
        for n in away_news:
            snippet = n.get('snippet', '')
            if snippet:
                lines.append(f"  • {snippet[:200]}")
        lines.append("")

    # Recent results
    home_results = fetch_recent_results(home_team)
    if home_results:
        lines.append(f"📊 {home_team} recent form:")
        for r in home_results:
            lines.append(f"  • {r[:200]}")
        lines.append("")

    away_results = fetch_recent_results(away_team)
    if away_results:
        lines.append(f"📊 {away_team} recent form:")
        for r in away_results:
            lines.append(f"  • {r[:200]}")
        lines.append("")

    # Competition standings
    if competition:
        standings = fetch_competition_standings(competition)
        if standings:
            lines.append(f"🏆 {competition} current standings:")
            for s in standings:
                lines.append(f"  • {s[:200]}")
            lines.append("")

    return '\n'.join(lines)


def build_general_context(question):
    """
    Build context for a general football question by extracting
    team/competition names and fetching relevant current information.
    """
    today = datetime.now().strftime('%B %d, %Y')
    lines = [f"=== CURRENT INFORMATION (as of {today}) ===\n"]

    # Detect competitions mentioned
    competitions = []
    q_lower = question.lower()
    comp_map = {
        'champions league': 'UEFA Champions League',
        'premier league': 'Premier League',
        'la liga': 'La Liga',
        'bundesliga': 'Bundesliga',
        'serie a': 'Serie A',
        'ligue 1': 'Ligue 1',
        'world cup': 'FIFA World Cup',
        'euro': 'UEFA European Championship',
    }
    for key, name in comp_map.items():
        if key in q_lower:
            competitions.append(name)

    for comp in competitions[:2]:
        standings = fetch_competition_standings(comp)
        if standings:
            lines.append(f"🏆 {comp} current standings:")
            for s in standings:
                lines.append(f"  • {s[:200]}")
            lines.append("")

    # Detect team names mentioned
    known_clubs = [
        'Arsenal', 'Chelsea', 'Liverpool', 'Manchester City', 'Manchester United',
        'Tottenham', 'Newcastle', 'Aston Villa', 'West Ham', 'Brighton',
        'Real Madrid', 'Barcelona', 'Atletico Madrid', 'Bayern Munich', 'Dortmund',
        'PSG', 'Juventus', 'Inter Milan', 'AC Milan', 'Napoli',
        'Ajax', 'Porto', 'Benfica', 'Celtic', 'Rangers',
    ]
    mentioned_teams = [c for c in known_clubs if c.lower() in q_lower][:2]

    for team in mentioned_teams:
        news = fetch_team_news(team, max_results=2)
        if news:
            lines.append(f"📰 {team} latest news:")
            for n in news:
                snippet = n.get('snippet', '')
                if snippet:
                    lines.append(f"  • {snippet[:200]}")
            lines.append("")

    return '\n'.join(lines) if len(lines) > 2 else ""
