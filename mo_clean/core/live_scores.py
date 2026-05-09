import requests
from django.conf import settings
from django.core.cache import cache

def get_live_scores():
    cached = cache.get('live_scores')
    if cached:
        return cached
    api_key = settings.MATCHORACLE.get('FOOTBALL_API_KEY', '')
    if api_key:
        try:
            headers = {'X-RapidAPI-Key': api_key, 'X-RapidAPI-Host': 'api-football-v1.p.rapidapi.com'}
            resp = requests.get('https://api-football-v1.p.rapidapi.com/v3/fixtures', headers=headers, params={'live': 'all'}, timeout=8)
            if resp.status_code == 200:
                scores = _parse(resp.json().get('response', []))
                cache.set('live_scores', scores, 60)
                return scores
        except Exception:
            pass
    return _mock()

def get_todays_fixtures():
    cached = cache.get('today_fixtures')
    if cached:
        return cached
    api_key = settings.MATCHORACLE.get('FOOTBALL_API_KEY', '')
    if api_key:
        try:
            from datetime import date
            today = date.today().strftime('%Y-%m-%d')
            headers = {'X-RapidAPI-Key': api_key, 'X-RapidAPI-Host': 'api-football-v1.p.rapidapi.com'}
            resp = requests.get('https://api-football-v1.p.rapidapi.com/v3/fixtures', headers=headers, params={'date': today, 'timezone': 'Africa/Lagos'}, timeout=8)
            if resp.status_code == 200:
                fixtures = _parse(resp.json().get('response', []))
                cache.set('today_fixtures', fixtures, 300)
                return fixtures
        except Exception:
            pass
    return []

def _parse(fixtures):
    results = []
    for f in fixtures:
        try:
            fix = f.get('fixture', {})
            teams = f.get('teams', {})
            goals = f.get('goals', {})
            league = f.get('league', {})
            status = fix.get('status', {})
            results.append({
                'id': fix.get('id'), 'home': teams.get('home', {}).get('name', '?'),
                'away': teams.get('away', {}).get('name', '?'),
                'home_logo': teams.get('home', {}).get('logo', ''),
                'away_logo': teams.get('away', {}).get('logo', ''),
                'home_score': goals.get('home'), 'away_score': goals.get('away'),
                'status': status.get('short', 'NS'), 'status_long': status.get('long', ''),
                'minute': status.get('elapsed'), 'league': league.get('name', ''),
                'date': fix.get('date', ''),
            })
        except Exception:
            continue
    return results

def _mock():
    return [
        {'id': 1, 'home': 'Arsenal', 'away': 'Chelsea', 'home_score': 2, 'away_score': 1,
         'status': 'LIVE', 'status_long': 'Second Half', 'minute': 67,
         'league': 'Premier League', 'home_logo': '', 'away_logo': '', 'date': ''},
        {'id': 2, 'home': 'Real Madrid', 'away': 'Barcelona', 'home_score': 1, 'away_score': 1,
         'status': 'LIVE', 'status_long': 'First Half', 'minute': 34,
         'league': 'La Liga', 'home_logo': '', 'away_logo': '', 'date': ''},
    ]
