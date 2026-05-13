import requests
import logging
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)


def get_sportmonks_headers():
    api_key = getattr(settings, 'SPORTMONKS_API_KEY', '') or settings.MATCHORACLE.get('FOOTBALL_API_KEY', '')
    return {
        'Authorization': api_key,
        'Content-Type': 'application/json',
    }


def get_live_scores():
    cached = cache.get('live_scores_v2')
    if cached is not None:
        return cached
    
    api_key = getattr(settings, 'SPORTMONKS_API_KEY', '') or settings.MATCHORACLE.get('FOOTBALL_API_KEY', '')
    if api_key:
        try:
            # Sportmonks v3 live fixtures endpoint
            headers = get_sportmonks_headers()
            resp = requests.get(
                'https://api.sportmonks.com/v3/football/livescores/inplay',
                headers=headers,
                params={
                    'include': 'participants;scores;state;league',
                    'per_page': 50,
                },
                timeout=10
            )
            if resp.status_code == 200:
                data = resp.json()
                scores = _parse_sportmonks(data.get('data', []))
                cache.set('live_scores_v2', scores, 60)
                return scores
            else:
                logger.warning(f"Sportmonks API error: {resp.status_code} - {resp.text[:200]}")
        except Exception as e:
            logger.error(f"Live scores error: {e}")
    
    scores = _mock_live()
    cache.set('live_scores_v2', scores, 60)
    return scores


def get_todays_fixtures():
    cached = cache.get('today_fixtures_v2')
    if cached is not None:
        return cached

    api_key = getattr(settings, 'SPORTMONKS_API_KEY', '') or settings.MATCHORACLE.get('FOOTBALL_API_KEY', '')
    if api_key:
        try:
            from datetime import date
            today = date.today().strftime('%Y-%m-%d')
            headers = get_sportmonks_headers()
            resp = requests.get(
                f'https://api.sportmonks.com/v3/football/fixtures/date/{today}',
                headers=headers,
                params={
                    'include': 'participants;scores;state;league',
                    'per_page': 50,
                },
                timeout=10
            )
            if resp.status_code == 200:
                data = resp.json()
                fixtures = _parse_sportmonks(data.get('data', []))
                cache.set('today_fixtures_v2', fixtures, 300)
                return fixtures
        except Exception as e:
            logger.error(f"Today fixtures error: {e}")
    
    return _mock_fixtures()


def _parse_sportmonks(fixtures):
    results = []
    for f in fixtures:
        try:
            # Get participants (home/away teams)
            participants = f.get('participants', [])
            home_team = next((p for p in participants if p.get('meta', {}).get('location') == 'home'), {})
            away_team = next((p for p in participants if p.get('meta', {}).get('location') == 'away'), {})

            # Get scores
            scores = f.get('scores', [])
            home_score = None
            away_score = None
            for score in scores:
                if score.get('description') == 'CURRENT':
                    counts = score.get('score', {}).get('participant', '')
                    goals = score.get('score', {}).get('goals', 0)
                    if counts == 'home':
                        home_score = goals
                    elif counts == 'away':
                        away_score = goals

            # Get state
            state = f.get('state', {})
            status_short = state.get('short_name', 'NS')
            status_long = state.get('name', 'Not Started')
            minute = f.get('minute', None)

            # Get league
            league = f.get('league', {})
            league_name = league.get('name', 'Unknown League')

            results.append({
                'id': f.get('id'),
                'home': home_team.get('name', 'Home'),
                'away': away_team.get('name', 'Away'),
                'home_logo': home_team.get('image_path', ''),
                'away_logo': away_team.get('image_path', ''),
                'home_score': home_score,
                'away_score': away_score,
                'status': status_short,
                'status_long': status_long,
                'minute': minute,
                'league': league_name,
                'date': f.get('starting_at', ''),
            })
        except Exception as e:
            logger.error(f"Parse error: {e}")
            continue
    return results


def _mock_live():
    return [
        {'id': 1, 'home': 'Arsenal', 'away': 'Chelsea',
         'home_score': 2, 'away_score': 1,
         'status': 'LIVE', 'status_long': 'Second Half', 'minute': 67,
         'league': 'Premier League', 'home_logo': '', 'away_logo': '', 'date': ''},
        {'id': 2, 'home': 'Real Madrid', 'away': 'Barcelona',
         'home_score': 1, 'away_score': 1,
         'status': 'LIVE', 'status_long': 'First Half', 'minute': 34,
         'league': 'La Liga', 'home_logo': '', 'away_logo': '', 'date': ''},
        {'id': 3, 'home': 'Bayern Munich', 'away': 'Dortmund',
         'home_score': 3, 'away_score': 0,
         'status': 'FT', 'status_long': 'Finished', 'minute': None,
         'league': 'Bundesliga', 'home_logo': '', 'away_logo': '', 'date': ''},
    ]


def _mock_fixtures():
    return [
        {'id': 4, 'home': 'Man City', 'away': 'Liverpool',
         'home_score': None, 'away_score': None,
         'status': 'NS', 'status_long': 'Not Started', 'minute': None,
         'league': 'Premier League', 'home_logo': '', 'away_logo': '', 'date': '20:00'},
        {'id': 5, 'home': 'Juventus', 'away': 'AC Milan',
         'home_score': None, 'away_score': None,
         'status': 'NS', 'status_long': 'Not Started', 'minute': None,
         'league': 'Serie A', 'home_logo': '', 'away_logo': '', 'date': '19:45'},
    ]
