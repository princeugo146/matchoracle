import json
import requests
import re
import logging
from django.conf import settings
from .engine import (
    search_web, extract_match_data, extract_player_data,
    extract_upcoming_matches, detect_intent,
    _build_match_engine_input, _build_sim_engine_input,
    engine_a, engine_b, engine_d, get_confidence_badge,
)

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
    """Use AI to extract team names and intent from natural language."""
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
    """Try to get real team stats from Sportmonks."""
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
    """Check if these teams play today."""
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
    Main function: takes a natural language question and returns a full
    prediction by detecting intent, searching the web for real data,
    trying Sportmonks if available, and routing to the right engine.

    Intent routing:
      match_prediction  → Engine A + Engine D (simulation)
      player_comparison → Engine B (per player) + comparison narrative
      simulation        → Engine D
      general           → Claude AI only
    """
    if not question or len(question.strip()) < 5:
        return {
            'success': False,
            'answer': 'Please ask a football question, e.g. "Who will win Arsenal vs Chelsea today?"',
            'prediction': None,
            'data_sources': [],
        }

    # ── 1. Detect intent ────────────────────────────────────────────────────
    intent_info = detect_intent(question)
    intent = intent_info['intent']
    teams = intent_info.get('teams', [])
    players = intent_info.get('players', [])
    data_sources = []

    # ── 2. If intent unclear, try AI extraction as fallback ─────────────────
    if intent in ('general', 'match_prediction') and not teams:
        extraction = extract_teams_from_question(question)
        if extraction:
            ht = extraction.get('home_team', '').strip()
            at = extraction.get('away_team', '').strip()
            if ht and at:
                teams = [ht, at]
                intent = 'match_prediction'

    # ── 3. Match prediction ─────────────────────────────────────────────────
    if intent == 'match_prediction' and len(teams) >= 2:
        home_team, away_team = teams[0], teams[1]

        todays_match = get_todays_match(home_team, away_team)
        competition = 'League'

        search_q = f"{home_team} vs {away_team} prediction form injuries stats 2024"
        web_results = search_web(search_q)
        if web_results:
            data_sources.append('web_search')
        if todays_match:
            data_sources.append('sportmonks')

        web_data = extract_match_data(web_results, home_team, away_team)

        upcoming = extract_upcoming_matches(web_results, home_team)
        if upcoming:
            competition = upcoming.get('competition', 'League').title()

        engine_data = _build_match_engine_input(home_team, away_team, web_data)
        sim_data = _build_sim_engine_input(home_team, away_team, web_data)

        try:
            match_result = engine_a(engine_data)
        except Exception as e:
            logger.error(f"Engine A error in smart_predict: {e}")
            match_result = None

        try:
            sim_result = engine_d(sim_data)
        except Exception as e:
            logger.error(f"Engine D error in smart_predict: {e}")
            sim_result = None

        if not match_result:
            return {
                'success': False,
                'answer': f'Unable to generate prediction for {home_team} vs {away_team}.',
                'home_team': home_team,
                'away_team': away_team,
                'data_sources': data_sources,
            }

        match_info = "Today's match" if todays_match else "Upcoming match"
        snippets_text = ' | '.join(web_data.get('raw_snippets', []))
        ai_answer = call_ai(
            'You are MatchOracle AI, a football intelligence assistant. Give expert predictions. Return ONLY valid JSON.',
            f'User asked: "{question}"\n'
            f'Match: {home_team} vs {away_team} ({competition}) - {match_info}\n'
            f'Web data snippets: {snippets_text[:300]}\n'
            f'Engine A: Home {match_result["home_win"]}% Draw {match_result["draw"]}% Away {match_result["away_win"]}%\n'
            f'Predicted score: {match_result.get("predicted_score","1-1")}\n'
            f'Simulation (10,000 runs): Most likely score {sim_result["likely_score"] if sim_result else "N/A"}\n'
            f'Confidence: {match_result["confidence"]}%\n'
            f'Data sources: {", ".join(data_sources) or "defaults"}\n'
            f'Return JSON: {{"answer":"3-4 sentence expert analysis mentioning percentages and predicted score",'
            f'"verdict":"{match_result["verdict"]}",'
            f'"key_factors":["factor1","factor2","factor3"],'
            f'"betting_insight":"one sentence about most likely outcome"}}',
            max_tokens=600,
        )

        if ai_answer:
            final_answer = ai_answer.get('answer', '')
            key_factors = ai_answer.get('key_factors', [])
            betting_insight = ai_answer.get('betting_insight', '')
        else:
            final_answer = (
                f"Based on web data and V1 analysis, {match_result['verdict']} is predicted to win "
                f"({match_result['home_win']}% home / {match_result['draw']}% draw / "
                f"{match_result['away_win']}% away). "
                f"Predicted score: {match_result.get('predicted_score','1-1')}. "
                f"Simulation most likely score: {sim_result['likely_score'] if sim_result else 'N/A'}."
            )
            key_factors = []
            betting_insight = ''

        return {
            'success': True,
            'intent': intent,
            'home_team': home_team,
            'away_team': away_team,
            'competition': competition,
            'is_today': todays_match is not None,
            'match_prediction': match_result,
            'simulation': sim_result,
            'answer': final_answer,
            'verdict': match_result['verdict'],
            'predicted_score': match_result.get('predicted_score', '1-1'),
            'likely_score': sim_result['likely_score'] if sim_result else 'N/A',
            'confidence': match_result['confidence'],
            'confidence_badge': get_confidence_badge(match_result['confidence']),
            'key_factors': key_factors,
            'betting_insight': betting_insight,
            'home_win': match_result['home_win'],
            'draw': match_result['draw'],
            'away_win': match_result['away_win'],
            'data_sources': data_sources,
        }

    # ── 4. Player comparison ────────────────────────────────────────────────
    if intent == 'player_comparison' and players:
        ratings = []
        for player in players:
            search_q = f"{player} football stats goals assists 2024 season"
            results = search_web(search_q)
            if results:
                data_sources.append('web_search')
            pdata = extract_player_data(results, player)
            try:
                rating = engine_b(pdata)
                ratings.append({'player': player, 'result': rating})
            except Exception as e:
                logger.error(f"Engine B error for {player} in smart_predict: {e}")

        if ratings:
            comparison_text = '\n'.join(
                f"{r['player']}: rating={r['result']['rating']}/100 tier={r['result']['tier']} "
                f"insight={r['result'].get('insight','')}"
                for r in ratings
            )
            ai_answer = call_ai(
                'You are MatchOracle AI. Compare football players expertly. Return ONLY valid JSON.',
                f'User asked: "{question}"\n'
                f'Engine B player ratings:\n{comparison_text}\n'
                f'Data sources: {", ".join(data_sources) or "defaults"}\n'
                f'Return JSON: {{"answer":"3-4 sentence comparison with ratings",'
                f'"verdict":"name of better player",'
                f'"key_factors":["factor1","factor2","factor3"],'
                f'"confidence":75}}',
                max_tokens=600,
            )
            best = max(ratings, key=lambda x: x['result']['rating'])
            return {
                'success': True,
                'intent': intent,
                'answer': (ai_answer or {}).get('answer',
                    f"Engine B comparison: {comparison_text}"),
                'verdict': (ai_answer or {}).get('verdict', best['player']),
                'key_factors': (ai_answer or {}).get('key_factors', []),
                'confidence': (ai_answer or {}).get('confidence', 70),
                'player_ratings': ratings,
                'home_team': None,
                'away_team': None,
                'match_prediction': None,
                'simulation': None,
                'data_sources': data_sources,
            }

    # ── 5. Simulation ───────────────────────────────────────────────────────
    if intent == 'simulation':
        if len(teams) >= 2:
            home_team, away_team = teams[0], teams[1]
            search_q = f"{home_team} vs {away_team} stats attack defence 2024"
            results = search_web(search_q)
            if results:
                data_sources.append('web_search')
            web_data = extract_match_data(results, home_team, away_team)
            sim_data = _build_sim_engine_input(home_team, away_team, web_data)
        else:
            home_team = teams[0] if teams else 'Home Team'
            away_team = 'Away Team'
            sim_data = {
                'home': {'name': home_team, 'attack': 75, 'defence': 70, 'elo': 1050, 'injuries': 0,
                         'tactical_style': 'balanced', 'tournament_experience': 5, 'knockout_mentality': 5},
                'away': {'name': away_team, 'attack': 72, 'defence': 68, 'elo': 1020, 'injuries': 0,
                         'tactical_style': 'balanced', 'tournament_experience': 5, 'knockout_mentality': 5},
                'simulations': 10000, 'competition': 'league', 'weather': 'normal', 'match_type': 'league',
            }

        try:
            sim_result = engine_d(sim_data)
        except Exception as e:
            logger.error(f"Engine D error in smart_predict simulation: {e}")
            sim_result = None

        if sim_result:
            ai_answer = call_ai(
                'You are MatchOracle AI. Explain simulation results. Return ONLY valid JSON.',
                f'User asked: "{question}"\n'
                f'Simulation ({sim_result["simulations"]} runs): '
                f'Home {sim_result["home_win"]}% Draw {sim_result["draw"]}% Away {sim_result["away_win"]}%\n'
                f'Most likely score: {sim_result["likely_score"]}\n'
                f'Return JSON: {{"answer":"3-4 sentence simulation analysis",'
                f'"verdict":"most likely outcome",'
                f'"key_factors":["f1","f2","f3"],"confidence":75}}',
                max_tokens=500,
            )
            return {
                'success': True,
                'intent': intent,
                'answer': (ai_answer or {}).get('answer',
                    f"Simulation complete ({sim_result['simulations']} runs). "
                    f"Most likely score: {sim_result['likely_score']}. "
                    f"Home win {sim_result['home_win']}%, Draw {sim_result['draw']}%, "
                    f"Away win {sim_result['away_win']}%."),
                'verdict': (ai_answer or {}).get('verdict', sim_result['likely_score']),
                'key_factors': (ai_answer or {}).get('key_factors', []),
                'confidence': (ai_answer or {}).get('confidence', 70),
                'home_team': home_team,
                'away_team': away_team,
                'match_prediction': None,
                'simulation': sim_result,
                'data_sources': data_sources,
            }

    # ── 6. General football question (Claude only) ──────────────────────────
    ai = call_ai(
        'You are MatchOracle AI, a football expert assistant. Answer football questions. Return ONLY valid JSON.',
        f'Football question: "{question}"\n'
        f'Return: {{"answer":"3-4 sentence expert answer","key_factors":["f1","f2","f3"],"verdict":"Your recommendation"}}',
        max_tokens=500,
    )
    return {
        'success': True,
        'intent': intent,
        'home_team': None,
        'away_team': None,
        'answer': (ai or {}).get('answer',
            'Please mention two team names for a full prediction, e.g. "Who will win Arsenal vs Chelsea?"'),
        'verdict': (ai or {}).get('verdict', ''),
        'key_factors': (ai or {}).get('key_factors', []),
        'match_prediction': None,
        'simulation': None,
        'confidence': 0,
        'data_sources': data_sources,
    }
