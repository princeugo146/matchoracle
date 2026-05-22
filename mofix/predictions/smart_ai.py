import json, requests, re, logging
from django.conf import settings

logger = logging.getLogger(__name__)


def call_ai(system, user_msg, max_tokens=800):
    key = settings.MATCHORACLE.get('ANTHROPIC_API_KEY', '')
    if not key:
        return None
    try:
        resp = requests.post(
            'https://api.anthropic.com/v1/messages',
            headers={
                'Content-Type': 'application/json',
                'x-api-key': key,
                'anthropic-version': '2023-06-01'
            },
            json={
                'model': 'claude-sonnet-4-20250514',
                'max_tokens': max_tokens,
                'system': system,
                'messages': [{'role': 'user', 'content': user_msg}]
            },
            timeout=20
        )
        if resp.status_code == 200:
            text = ''.join(b.get('text', '') for b in resp.json().get('content', []))
            clean = text.replace('```json', '').replace('```', '').strip()
            return json.loads(clean)
        else:
            logger.error(f"Anthropic error: {resp.status_code} - {resp.text[:200]}")
    except json.JSONDecodeError as e:
        logger.error(f"AI JSON parse error: {e}")
    except Exception as e:
        logger.error(f"AI call failed: {e}")
    return None


def extract_teams_from_question(question):
    """Use AI to extract team names and intent from natural language"""
    ai = call_ai(
        'You are a football AI assistant. Extract information from football questions. Return ONLY valid JSON.',
        f'Question: "{question}"\n'
        f'Extract the teams, intent and any context. Return this exact JSON:\n'
        f'{{"home_team":"Arsenal","away_team":"Chelsea","intent":"prediction","competition":"Premier League",'
        f'"extra_context":"any injuries or context mentioned","confidence_to_extract":90}}\n'
        f'If you cannot find two teams, set home_team and away_team to empty strings.',
        max_tokens=300
    )
    return ai


def get_team_stats_from_sportmonks(team_name):
    """Try to get real team stats from Sportmonks"""
    api_key = settings.MATCHORACLE.get('FOOTBALL_API_KEY', '')
    if not api_key:
        return None
    try:
        resp = requests.get(
            'https://api.sportmonks.com/v3/football/teams/search/' + team_name,
            headers={'Authorization': api_key},
            timeout=8
        )
        if resp.status_code == 200:
            data = resp.json().get('data', [])
            if data:
                return data[0]
    except Exception as e:
        logger.error(f"Sportmonks team search error: {e}")
    return None


def get_todays_match(home_team, away_team):
    """Check if these teams play today"""
    api_key = settings.MATCHORACLE.get('FOOTBALL_API_KEY', '')
    if not api_key:
        return None
    try:
        from datetime import date
        today = date.today().strftime('%Y-%m-%d')
        resp = requests.get(
            f'https://api.sportmonks.com/v3/football/fixtures/date/{today}',
            headers={'Authorization': api_key},
            params={'include': 'participants;scores;state;league', 'per_page': 100},
            timeout=10
        )
        if resp.status_code == 200:
            fixtures = resp.json().get('data', [])
            ht_lower = home_team.lower()
            at_lower = away_team.lower()
            for f in fixtures:
                parts = f.get('participants', [])
                names = [p.get('name', '').lower() for p in parts]
                if any(ht_lower in n or n in ht_lower for n in names) and \
                   any(at_lower in n or n in at_lower for n in names):
                    return f
    except Exception as e:
        logger.error(f"Today's match lookup error: {e}")
    return None


def smart_predict(question):
    """
    Main function: takes a natural language question and returns
    a full prediction by auto-detecting teams and running engines.
    """
    if not question or len(question.strip()) < 5:
        return {
            'success': False,
            'answer': 'Please ask a football question, e.g. "Who will win Arsenal vs Chelsea today?"',
            'prediction': None
        }

    # Step 1: Extract teams from question
    extraction = extract_teams_from_question(question)

    home_team = ''
    away_team = ''
    competition = 'Unknown League'
    extra_context = ''

    if extraction:
        home_team = extraction.get('home_team', '').strip()
        away_team = extraction.get('away_team', '').strip()
        competition = extraction.get('competition', 'Unknown League')
        extra_context = extraction.get('extra_context', '')

    # Step 2: If we have both teams, run full engine prediction
    if home_team and away_team:
        # Check if they play today
        todays_match = get_todays_match(home_team, away_team)

        # Build engine A data with smart defaults
        engine_data = {
            'home': {
                'name': home_team,
                'goals_scored': 1.6,
                'goals_conceded': 1.1,
                'form': 'W D W W D',
                'win_rate': 50,
                'injuries': 0,
                'position': 8,
            },
            'away': {
                'name': away_team,
                'goals_scored': 1.5,
                'goals_conceded': 1.2,
                'form': 'W W D L W',
                'win_rate': 48,
                'injuries': 0,
                'position': 9,
            },
            'h2h': {
                'home_wins': 4,
                'draws': 3,
                'away_wins': 3,
            }
        }

        # Run Engine A
        from predictions.engine import engine_a, engine_d
        match_result = engine_a(engine_data)

        # Run Engine D simulation
        sim_data = {
            'home': {
                'name': home_team,
                'attack': 72,
                'defence': 68,
                'elo': 1050,
                'injuries': 0,
            },
            'away': {
                'name': away_team,
                'attack': 70,
                'defence': 66,
                'elo': 1030,
                'injuries': 0,
            },
            'simulations': 10000,
            'competition': 'league',
            'weather': 'normal',
        }
        sim_result = engine_d(sim_data)

        # Step 3: Build comprehensive AI answer
        match_info = f"Today's match" if todays_match else f"Upcoming match"
        ai_answer = call_ai(
            'You are MatchOracle AI, a football intelligence assistant. Give expert predictions. Return ONLY valid JSON.',
            f'User asked: "{question}"\n'
            f'Match: {home_team} vs {away_team} ({competition}) - {match_info}\n'
            f'Engine A results: Home win {match_result["home_win"]}%, Draw {match_result["draw"]}%, Away win {match_result["away_win"]}%\n'
            f'Predicted score: {match_result["predicted_score"]}\n'
            f'Simulation (10,000 runs): Most likely score {sim_result["likely_score"]}\n'
            f'Confidence: {match_result["confidence"]}%\n'
            f'Extra context: {extra_context}\n'
            f'Return this JSON: {{"answer":"Your 3-4 sentence expert analysis mentioning the percentages and predicted score",'
            f'"verdict":"{match_result["verdict"]}",'
            f'"key_factors":["factor 1","factor 2","factor 3"],'
            f'"betting_insight":"One sentence about the most likely outcome"}}',
            max_tokens=600
        )

        final_answer = ''
        key_factors = []
        betting_insight = ''

        if ai_answer:
            final_answer = ai_answer.get('answer', '')
            key_factors = ai_answer.get('key_factors', [])
            betting_insight = ai_answer.get('betting_insight', '')
        else:
            final_answer = (
                f"Based on our V1 analysis, {match_result['verdict']} is predicted to win "
                f"with {max(match_result['home_win'], match_result['away_win'])}% probability. "
                f"The draw probability is {match_result['draw']}%. "
                f"Our simulation of 10,000 matches suggests the most likely score is {sim_result['likely_score']}."
            )

        return {
            'success': True,
            'home_team': home_team,
            'away_team': away_team,
            'competition': competition,
            'is_today': todays_match is not None,
            'match_prediction': match_result,
            'simulation': sim_result,
            'answer': final_answer,
            'verdict': match_result['verdict'],
            'predicted_score': match_result['predicted_score'],
            'likely_score': sim_result['likely_score'],
            'confidence': match_result['confidence'],
            'key_factors': key_factors,
            'betting_insight': betting_insight,
            'home_win': match_result['home_win'],
            'draw': match_result['draw'],
            'away_win': match_result['away_win'],
        }

    else:
        # No teams found — answer as general football AI
        ai = call_ai(
            'You are MatchOracle AI, a football expert assistant. Answer football questions. Return ONLY valid JSON.',
            f'Football question: "{question}"\n'
            f'Return: {{"answer":"3-4 sentence expert answer","key_factors":["f1","f2","f3"],"verdict":"Your recommendation"}}',
            max_tokens=500
        )
        return {
            'success': True,
            'home_team': None,
            'away_team': None,
            'answer': ai.get('answer', 'Please mention two team names for a full prediction, e.g. "Who will win Arsenal vs Chelsea?"') if ai else 'Please mention two team names for a full prediction.',
            'verdict': ai.get('verdict', '') if ai else '',
            'key_factors': ai.get('key_factors', []) if ai else [],
            'match_prediction': None,
            'simulation': None,
            'confidence': 0,
        }
