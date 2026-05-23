import requests, logging
from django.conf import settings
from django.core.cache import cache
logger = logging.getLogger(__name__)

def get_live_scores():
    cached = cache.get('live_scores')
    if cached is not None:
        return cached
    api_key = settings.MATCHORACLE.get('FOOTBALL_API_KEY', '')
    if api_key:
        try:
            resp = requests.get(
                'https://api.sportmonks.com/v3/football/livescores/inplay',
                headers={'Authorization': api_key},
                params={'include': 'participants;scores;state;league', 'per_page': 50},
                timeout=10
            )
            if resp.status_code == 200:
                scores = _parse(resp.json().get('data', []))
                cache.set('live_scores', scores, 60)
                return scores
        except Exception as e:
            logger.error(f"Live scores error: {e}")
    mock = _mock()
    cache.set('live_scores', mock, 60)
    return mock

def get_todays_fixtures():
    cached = cache.get('today_fixtures')
    if cached is not None:
        return cached
    api_key = settings.MATCHORACLE.get('FOOTBALL_API_KEY', '')
    if api_key:
        try:
            from datetime import date
            today = date.today().strftime('%Y-%m-%d')
            resp = requests.get(
                f'https://api.sportmonks.com/v3/football/fixtures/date/{today}',
                headers={'Authorization': api_key},
                params={'include': 'participants;scores;state;league', 'per_page': 50},
                timeout=10
            )
            if resp.status_code == 200:
                fixtures = _parse(resp.json().get('data', []))
                cache.set('today_fixtures', fixtures, 300)
                return fixtures
        except Exception as e:
            logger.error(f"Fixtures error: {e}")
    return []

def _parse(fixtures):
    results = []
    for f in fixtures:
        try:
            parts = f.get('participants', [])
            home = next((p for p in parts if p.get('meta', {}).get('location') == 'home'), {})
            away = next((p for p in parts if p.get('meta', {}).get('location') == 'away'), {})
            scores = f.get('scores', [])
            hs = next((s.get('score', {}).get('goals') for s in scores if s.get('description') == 'CURRENT' and s.get('score', {}).get('participant') == 'home'), None)
            as_ = next((s.get('score', {}).get('goals') for s in scores if s.get('description') == 'CURRENT' and s.get('score', {}).get('participant') == 'away'), None)
            state = f.get('state', {})
            results.append({
                'id': f.get('id'),
                'home': home.get('name', 'Home'),
                'away': away.get('name', 'Away'),
                'home_logo': home.get('image_path', ''),
                'away_logo': away.get('image_path', ''),
                'home_score': hs, 'away_score': as_,
                'status': state.get('short_name', 'NS'),
                'status_long': state.get('name', ''),
                'minute': f.get('minute'),
                'league': f.get('league', {}).get('name', ''),
                'date': f.get('starting_at', ''),
            })
        except Exception:
            continue
    return results

def _mock():
    return [
        {'id':1,'home':'Arsenal','away':'Chelsea','home_score':2,'away_score':1,'status':'LIVE','status_long':'Second Half','minute':67,'league':'Premier League','home_logo':'','away_logo':'','date':''},
        {'id':2,'home':'Real Madrid','away':'Barcelona','home_score':1,'away_score':1,'status':'LIVE','status_long':'First Half','minute':34,'league':'La Liga','home_logo':'','away_logo':'','date':''},
        {'id':3,'home':'Bayern Munich','away':'Dortmund','home_score':3,'away_score':0,'status':'FT','status_long':'Finished','minute':None,'league':'Bundesliga','home_logo':'','away_logo':'','date':''},
    ]
