"""
Sportmonks API client for MatchOracle Smart AI.
Fetches live matches, league standings, and team information.
All functions return empty lists/None gracefully when the API key is absent
or the request fails — the rest of the app is never affected.
"""
import requests
import logging
from django.conf import settings

logger = logging.getLogger(__name__)

_BASE = 'https://api.sportmonks.com/v3/football'


def _key():
    return settings.MATCHORACLE.get('FOOTBALL_API_KEY', '')


def get_live_matches():
    """
    Fetch currently live fixtures from Sportmonks.
    Returns a list of simplified match dicts, or [] on any failure.
    """
    api_key = _key()
    if not api_key:
        return []

    try:
        resp = requests.get(
            f'{_BASE}/livescores/now',
            params={
                'api_token': api_key,
                'include': 'participants;scores;state;league',
                'per_page': 25,
            },
            timeout=10,
        )
        if resp.status_code == 200:
            raw = resp.json().get('data', [])
            matches = []
            for f in raw:
                parts = f.get('participants', [])
                home = next((p for p in parts if p.get('meta', {}).get('location') == 'home'), None)
                away = next((p for p in parts if p.get('meta', {}).get('location') == 'away'), None)
                scores = f.get('scores', [])
                home_score = None
                away_score = None
                for s in scores:
                    if s.get('description') == 'CURRENT':
                        goals = s.get('score', {})
                        home_score = goals.get('participant') if s.get('type_id') == 1 else home_score
                        away_score = goals.get('participant') if s.get('type_id') == 2 else away_score
                state = f.get('state', {})
                matches.append({
                    'id': f.get('id'),
                    'home': home.get('name', 'Home') if home else 'Home',
                    'away': away.get('name', 'Away') if away else 'Away',
                    'home_score': home_score,
                    'away_score': away_score,
                    'minute': state.get('clock', {}).get('minute') if state else None,
                    'status': state.get('state', 'LIVE') if state else 'LIVE',
                    'league': f.get('league', {}).get('name', '') if f.get('league') else '',
                })
            return matches
        else:
            logger.warning(f"Sportmonks live scores: HTTP {resp.status_code}")
    except Exception as e:
        logger.error(f"Sportmonks live matches error: {e}")
    return []


def get_todays_fixtures():
    """
    Fetch today's fixtures (including upcoming and finished) from Sportmonks.
    Returns a list of simplified fixture dicts, or [] on any failure.
    """
    api_key = _key()
    if not api_key:
        return []

    try:
        from datetime import date
        today = date.today().strftime('%Y-%m-%d')
        resp = requests.get(
            f'{_BASE}/fixtures/date/{today}',
            params={
                'api_token': api_key,
                'include': 'participants;scores;state;league',
                'per_page': 50,
            },
            timeout=10,
        )
        if resp.status_code == 200:
            raw = resp.json().get('data', [])
            fixtures = []
            for f in raw:
                parts = f.get('participants', [])
                home = next((p for p in parts if p.get('meta', {}).get('location') == 'home'), None)
                away = next((p for p in parts if p.get('meta', {}).get('location') == 'away'), None)
                state = f.get('state', {})
                scores = f.get('scores', [])
                home_score = None
                away_score = None
                for s in scores:
                    if s.get('description') in ('CURRENT', 'FT'):
                        goals = s.get('score', {})
                        if s.get('type_id') == 1:
                            home_score = goals.get('participant')
                        elif s.get('type_id') == 2:
                            away_score = goals.get('participant')
                fixtures.append({
                    'id': f.get('id'),
                    'home': home.get('name', 'Home') if home else 'Home',
                    'away': away.get('name', 'Away') if away else 'Away',
                    'home_score': home_score,
                    'away_score': away_score,
                    'minute': state.get('clock', {}).get('minute') if state else None,
                    'status': state.get('state', '') if state else '',
                    'league': f.get('league', {}).get('name', '') if f.get('league') else '',
                    'starting_at': f.get('starting_at', ''),
                })
            return fixtures
        else:
            logger.warning(f"Sportmonks today fixtures: HTTP {resp.status_code}")
    except Exception as e:
        logger.error(f"Sportmonks today fixtures error: {e}")
    return []


def get_league_standings(league_id):
    """
    Fetch current standings for a given league ID.
    Returns a list of standing row dicts, or [] on any failure.
    """
    api_key = _key()
    if not api_key:
        return []

    try:
        resp = requests.get(
            f'{_BASE}/standings/seasons',
            params={
                'api_token': api_key,
                'filters': f'leagueId:{league_id}',
                'include': 'participant',
                'per_page': 25,
            },
            timeout=10,
        )
        if resp.status_code == 200:
            raw = resp.json().get('data', [])
            rows = []
            for entry in raw:
                team = entry.get('participant', {})
                rows.append({
                    'position': entry.get('position'),
                    'team': team.get('name', ''),
                    'played': entry.get('details', {}).get('games_played', entry.get('games_played', 0)),
                    'won': entry.get('details', {}).get('won', entry.get('won', 0)),
                    'drawn': entry.get('details', {}).get('draw', entry.get('draw', 0)),
                    'lost': entry.get('details', {}).get('lost', entry.get('lost', 0)),
                    'gf': entry.get('details', {}).get('goals_scored', entry.get('goals_scored', 0)),
                    'ga': entry.get('details', {}).get('goals_against', entry.get('goals_against', 0)),
                    'gd': entry.get('details', {}).get('goal_difference', entry.get('goal_difference', 0)),
                    'points': entry.get('points', 0),
                })
            return sorted(rows, key=lambda x: x.get('position') or 99)
        else:
            logger.warning(f"Sportmonks standings: HTTP {resp.status_code}")
    except Exception as e:
        logger.error(f"Sportmonks standings error: {e}")
    return []


# Common league IDs for quick lookup
LEAGUE_IDS = {
    'premier league': 8,
    'la liga': 564,
    'bundesliga': 82,
    'serie a': 384,
    'ligue 1': 301,
    'champions league': 2,
    'europa league': 5,
    'fa cup': 24,
    'copa del rey': 570,
}


def get_league_id_for_question(question):
    """
    Attempt to detect which league a question is about and return its Sportmonks ID.
    Returns None if no match found.
    """
    q = question.lower()
    for name, lid in LEAGUE_IDS.items():
        if name in q:
            return lid
    return None


def get_team_recent_fixtures(team_name, limit=5):
    """
    Search for a team and return its recent fixtures.
    Returns a list of fixture dicts, or [] on any failure.
    """
    api_key = _key()
    if not api_key:
        return []

    try:
        # First search for the team
        resp = requests.get(
            f'{_BASE}/teams/search/{team_name}',
            params={'api_token': api_key},
            timeout=8,
        )
        if resp.status_code != 200:
            return []
        teams = resp.json().get('data', [])
        if not teams:
            return []
        team_id = teams[0].get('id')
        if not team_id:
            return []

        # Fetch recent fixtures for that team
        resp2 = requests.get(
            f'{_BASE}/fixtures',
            params={
                'api_token': api_key,
                'filters': f'teamId:{team_id}',
                'include': 'participants;scores;state;league',
                'sort': '-starting_at',
                'per_page': limit,
            },
            timeout=10,
        )
        if resp2.status_code == 200:
            raw = resp2.json().get('data', [])
            fixtures = []
            for f in raw:
                parts = f.get('participants', [])
                home = next((p for p in parts if p.get('meta', {}).get('location') == 'home'), None)
                away = next((p for p in parts if p.get('meta', {}).get('location') == 'away'), None)
                state = f.get('state', {})
                fixtures.append({
                    'home': home.get('name', '') if home else '',
                    'away': away.get('name', '') if away else '',
                    'status': state.get('state', '') if state else '',
                    'starting_at': f.get('starting_at', ''),
                    'league': f.get('league', {}).get('name', '') if f.get('league') else '',
                })
            return fixtures
    except Exception as e:
        logger.error(f"Sportmonks team fixtures error: {e}")
    return []
