import requests
from django.conf import settings
from django.core.cache import cache


def get_live_count():
    scores = get_live_scores()
    return len([s for s in scores if s.get('minute')])


def get_live_scores():
    cached = cache.get('live_scores_v2')
    if cached:
        return cached
    api_key = settings.MATCHORACLE.get('FOOTBALL_API_KEY', '')
    if api_key:
        try:
            headers = {
                'X-RapidAPI-Key': api_key,
                'X-RapidAPI-Host': 'api-football-v1.p.rapidapi.com'
            }
            resp = requests.get(
                'https://api-football-v1.p.rapidapi.com/v3/fixtures',
                headers=headers, params={'live': 'all'}, timeout=8
            )
            if resp.status_code == 200:
                data = resp.json()
                scores = _parse(data.get('response', []))
                cache.set('live_scores_v2', scores, 60)
                return scores
        except Exception:
            pass
    scores = _mock_live()
    cache.set('live_scores_v2', scores, 60)
    return scores


def get_todays_fixtures():
    cached = cache.get('today_fixtures_v2')
    if cached:
        return cached
    api_key = settings.MATCHORACLE.get('FOOTBALL_API_KEY', '')
    if api_key:
        try:
            from datetime import date
            today = date.today().strftime('%Y-%m-%d')
            headers = {
                'X-RapidAPI-Key': api_key,
                'X-RapidAPI-Host': 'api-football-v1.p.rapidapi.com'
            }
            resp = requests.get(
                'https://api-football-v1.p.rapidapi.com/v3/fixtures',
                headers=headers,
                params={'date': today, 'timezone': 'Africa/Lagos'}, timeout=8
            )
            if resp.status_code == 200:
                data = resp.json()
                fixtures = _parse(data.get('response', []))
                cache.set('today_fixtures_v2', fixtures, 300)
                return fixtures
        except Exception:
            pass
    return _mock_fixtures()


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
                'id': fix.get('id'),
                'home': teams.get('home', {}).get('name', '?'),
                'away': teams.get('away', {}).get('name', '?'),
                'home_logo': teams.get('home', {}).get('logo', ''),
                'away_logo': teams.get('away', {}).get('logo', ''),
                'home_score': goals.get('home'),
                'away_score': goals.get('away'),
                'status': status.get('short', 'NS'),
                'status_long': status.get('long', 'Not Started'),
                'minute': status.get('elapsed'),
                'league': league.get('name', ''),
                'league_logo': league.get('logo', ''),
                'date': fix.get('date', ''),
            })
        except Exception:
            continue
    return results


def _mock_live():
    return [
        {'id': 1, 'home': 'Arsenal', 'away': 'Chelsea', 'home_score': 2, 'away_score': 1,
         'status': 'LIVE', 'status_long': 'Second Half', 'minute': 67,
         'league': 'Premier League', 'home_logo': '', 'away_logo': '', 'league_logo': '', 'date': ''},
        {'id': 2, 'home': 'Real Madrid', 'away': 'Barcelona', 'home_score': 1, 'away_score': 1,
         'status': 'LIVE', 'status_long': 'First Half', 'minute': 34,
         'league': 'La Liga', 'home_logo': '', 'away_logo': '', 'league_logo': '', 'date': ''},
        {'id': 3, 'home': 'Bayern Munich', 'away': 'Dortmund', 'home_score': 3, 'away_score': 0,
         'status': 'FT', 'status_long': 'Match Finished', 'minute': None,
         'league': 'Bundesliga', 'home_logo': '', 'away_logo': '', 'league_logo': '', 'date': ''},
    ]


def _mock_fixtures():
    return [
        {'id': 4, 'home': 'Man City', 'away': 'Liverpool', 'home_score': None, 'away_score': None,
         'status': 'NS', 'status_long': 'Not Started', 'minute': None,
         'league': 'Premier League', 'home_logo': '', 'away_logo': '', 'league_logo': '', 'date': '20:00'},
        {'id': 5, 'home': 'Juventus', 'away': 'AC Milan', 'home_score': None, 'away_score': None,
         'status': 'NS', 'status_long': 'Not Started', 'minute': None,
         'league': 'Serie A', 'home_logo': '', 'away_logo': '', 'league_logo': '', 'date': '19:45'},
    ]
