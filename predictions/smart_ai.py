import json
import requests
import re
import logging
from datetime import datetime
from django.conf import settings
from .engine import (
    search_web, extract_match_data, extract_player_data,
    extract_upcoming_matches, detect_intent,
    _build_match_engine_input, _build_sim_engine_input,
    _build_consensus,
    engine_a, engine_b, engine_d, get_confidence_badge,
)
from .news import (
    build_match_context, build_general_context,
    fetch_team_news, fetch_recent_results,
    fetch_competition_standings, fetch_live_matches,
)

logger = logging.getLogger(__name__)

TODAY = datetime.now().strftime('%B %d, %Y')


def call_ai(system, user_msg, max_tokens=800):
    """
    Call Anthropic Claude API using the ANTHROPIC_API_KEY from settings.
    Sends the request via the Anthropic Messages REST API.
    Returns parsed JSON dict or None on failure.
    """
    key = settings.MATCHORACLE.get('ANTHROPIC_API_KEY', '')
    if not key:
        logger.warning("ANTHROPIC_API_KEY not configured — AI responses disabled")
        return None
    try:
        resp = requests.post(
            'https://api.anthropic.com/v1/messages',
            headers={
                'Content-Type': 'application/json',
                'x-api-key': key,
                'anthropic-version': '2023-06-01',
            },
            json={
                'model': 'claude-sonnet-4-20250514',
                'max_tokens': max_tokens,
                'system': system,
                'messages': [{'role': 'user', 'content': user_msg}],
            },
            timeout=25,
        )
        if resp.status_code == 200:
            text = ''.join(b.get('text', '') for b in resp.json().get('content', []))
            clean = text.replace('```json', '').replace('```', '').strip()
            return json.loads(clean)
        else:
            logger.error(f"Anthropic error: {resp.status_code} - {resp.text[:300]}")
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
    Smart AI Orchestrator — takes a natural language question and returns a full
    prediction by detecting intent, fetching CURRENT live internet data (news,
    standings, recent results), running ALL prediction engines, comparing results,
    and compiling a consensus answer grounded in real-time information.

    Intent routing:
      match_prediction  → Engine A + Engine D + consensus + current news context
      player_comparison → Engine B (per player) + comparison narrative
      simulation        → Engine D
      general           → Claude AI + current standings/news context
    """
    if not question or len(question.strip()) < 5:
        return {
            'success': False,
            'answer': 'Please ask a football question, e.g. "Who will win Arsenal vs Chelsea today?"',
            'verdict': None,
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

    # ── 3. Match prediction: run Engine A + Engine D, build consensus ────────
    if intent == 'match_prediction' and len(teams) >= 2:
        home_team, away_team = teams[0], teams[1]

        # Check if match is today via Sportmonks
        todays_match = get_todays_match(home_team, away_team)
        competition = 'League'

        # Fetch live internet data (web search)
        search_q = f"{home_team} vs {away_team} prediction form injuries stats 2025"
        web_results = search_web(search_q)
        if web_results:
            data_sources.append('web_search')
        if todays_match:
            data_sources.append('sportmonks')

        web_data = extract_match_data(web_results, home_team, away_team)

        upcoming = extract_upcoming_matches(web_results, home_team)
        if upcoming:
            competition = upcoming.get('competition', 'League').title()

        # ── Fetch CURRENT news and standings for both teams ──────────────────
        try:
            current_context = build_match_context(home_team, away_team, competition)
            if current_context.strip():
                data_sources.append('live_news')
        except Exception as e:
            logger.warning(f"News context fetch failed: {e}")
            current_context = ''

        engine_data = _build_match_engine_input(home_team, away_team, web_data)
        sim_data = _build_sim_engine_input(home_team, away_team, web_data)

        # Run Engine A
        try:
            match_result = engine_a(engine_data)
        except Exception as e:
            logger.error(f"Engine A error in smart_predict: {e}")
            match_result = None

        # Run Engine D
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

        # Build consensus from Engine A + Engine D
        consensus = _build_consensus(home_team, away_team, match_result, sim_result)
        final_verdict = consensus['final_verdict']
        consensus_confidence = consensus['confidence']
        agreement_text = (
            f"Both Engine A and Engine D agree: {final_verdict} to win."
            if consensus['agreement']
            else (
                f"Engine A predicts {consensus['engine_a_verdict']} but Engine D leans "
                f"{consensus['engine_d_verdict']} — mixed signals."
            )
        )

        match_info = "Today's match" if todays_match else "Upcoming match"
        snippets_text = ' | '.join(web_data.get('raw_snippets', []))

        # Build the AI prompt with CURRENT information injected
        ai_answer = call_ai(
            (
                f'You are MatchOracle Smart AI, a football intelligence assistant with access to '
                f'CURRENT real-world information as of {TODAY}. '
                f'You have been provided with live news, recent results, and standings fetched from the web. '
                f'Use this current information to give accurate, up-to-date answers. '
                f'Return ONLY valid JSON.'
            ),
            f'User asked: "{question}"\n'
            f'Today\'s date: {TODAY}\n'
            f'Match: {home_team} vs {away_team} ({competition}) - {match_info}\n\n'
            f'{current_context[:800]}\n'
            f'Web search snippets: {snippets_text[:300]}\n\n'
            f'Engine A (match prediction): Home {match_result["home_win"]}% '
            f'Draw {match_result["draw"]}% Away {match_result["away_win"]}% '
            f'→ Verdict: {consensus["engine_a_verdict"]} | Score: {match_result.get("predicted_score","1-1")}\n'
            f'Engine D (Monte Carlo 10,000 sims): Home {sim_result["home_win"] if sim_result else "N/A"}% '
            f'Draw {sim_result["draw"] if sim_result else "N/A"}% '
            f'Away {sim_result["away_win"] if sim_result else "N/A"}% '
            f'→ Verdict: {consensus["engine_d_verdict"]} | Score: {sim_result["likely_score"] if sim_result else "N/A"}\n'
            f'Consensus: {agreement_text}\n'
            f'Final confidence: {consensus_confidence}%\n'
            f'Data sources: {", ".join(data_sources) or "defaults"}\n\n'
            f'Using the CURRENT information above, provide an expert analysis. '
            f'Mention current form, recent news, and standings where relevant. '
            f'Return JSON: {{"answer":"4-6 sentence expert analysis referencing current information, both engine results, percentages, and consensus",'
            f'"key_factors":["current factor 1","current factor 2","current factor 3"],'
            f'"current_info":"1 sentence summary of the most relevant current news/standings",'
            f'"betting_insight":"one sentence about the best bet based on current form"}}',
            max_tokens=900,
        )

        if ai_answer:
            final_answer = ai_answer.get('answer', '')
            key_factors = ai_answer.get('key_factors', [])
            betting_insight = ai_answer.get('betting_insight', '')
            current_info = ai_answer.get('current_info', '')
        else:
            final_answer = (
                f"As of {TODAY}, based on current web data, Engine A predicts {consensus['engine_a_verdict']} "
                f"({match_result['home_win']}% home / {match_result['draw']}% draw / "
                f"{match_result['away_win']}% away). "
                f"Engine D ({sim_result['simulations'] if sim_result else 10000} simulations) "
                f"most likely score: {sim_result['likely_score'] if sim_result else 'N/A'}. "
                f"{agreement_text}"
            )
            key_factors = [
                f"Engine A: {consensus['engine_a_verdict']} ({match_result['home_win']}% home win)",
                f"Engine D: {consensus['engine_d_verdict']} ({sim_result['home_win'] if sim_result else 'N/A'}% home win)",
                f"Consensus: {'Both engines agree' if consensus['agreement'] else 'Engines disagree — caution advised'}",
            ]
            betting_insight = (
                f"Strong consensus for {final_verdict} — both engines agree."
                if consensus['agreement']
                else "Mixed signals from engines — consider smaller stake or avoid."
            )
            current_info = ''

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
            'verdict': final_verdict,
            'predicted_score': match_result.get('predicted_score', '1-1'),
            'likely_score': sim_result['likely_score'] if sim_result else 'N/A',
            'confidence': consensus_confidence,
            'confidence_badge': get_confidence_badge(consensus_confidence),
            'consensus': consensus,
            'key_factors': key_factors,
            'betting_insight': betting_insight,
            'current_info': current_info,
            'home_win': match_result['home_win'],
            'draw': match_result['draw'],
            'away_win': match_result['away_win'],
            'data_sources': data_sources,
        }

    # ── 4. Player comparison ────────────────────────────────────────────────
    if intent == 'player_comparison' and players:
        ratings = []
        for player in players:
            search_q = f"{player} football stats goals assists 2025 season"
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
            # Fetch current news for each player
            player_news_ctx = ''
            for r in ratings:
                pname = r['player']
                news = fetch_team_news(pname, max_results=2)
                if news:
                    snippets = ' | '.join(n.get('snippet', '')[:150] for n in news)
                    player_news_ctx += f"{pname} news: {snippets}\n"

            ai_answer = call_ai(
                (
                    f'You are MatchOracle AI, a football expert with access to CURRENT information '
                    f'as of {TODAY}. Compare football players using current stats and news. '
                    f'Return ONLY valid JSON.'
                ),
                f'User asked: "{question}"\n'
                f'Today\'s date: {TODAY}\n'
                f'Engine B player ratings:\n{comparison_text}\n'
                f'Current player news:\n{player_news_ctx}\n'
                f'Data sources: {", ".join(data_sources) or "defaults"}\n'
                f'Return JSON: {{"answer":"3-4 sentence comparison referencing current form and ratings",'
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
            search_q = f"{home_team} vs {away_team} stats attack defence 2025"
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
                f'You are MatchOracle AI with access to current information as of {TODAY}. '
                f'Explain simulation results. Return ONLY valid JSON.',
                f'User asked: "{question}"\n'
                f'Today\'s date: {TODAY}\n'
                f'Simulation ({sim_result["simulations"]} runs): '
                f'Home {sim_result["home_win"]}% Draw {sim_result["draw"]}% Away {sim_result["away_win"]}%\n'
                f'Most likely score: {sim_result["likely_score"]}\n'
                f'Return JSON: {{"answer":"3-4 sentence simulation analysis with current context",'
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

    # ── 6. General football question — Claude + current context ─────────────
    # Fetch current context (standings, news) relevant to the question
    try:
        general_context = build_general_context(question)
        if general_context.strip():
            data_sources.append('live_news')
    except Exception as e:
        logger.warning(f"General context fetch failed: {e}")
        general_context = ''

    ai = call_ai(
        (
            f'You are MatchOracle Smart AI, a football expert assistant with access to '
            f'CURRENT real-world information as of {TODAY}. '
            f'You have been provided with live news and standings fetched from the web. '
            f'Use this current information to give accurate, up-to-date answers. '
            f'Do NOT say you lack access to current information — you have it. '
            f'Return ONLY valid JSON.'
        ),
        f'Football question: "{question}"\n'
        f'Today\'s date: {TODAY}\n\n'
        f'{general_context[:600]}\n\n'
        f'Using the current information above, answer the question accurately. '
        f'Return: {{"answer":"3-5 sentence expert answer referencing current standings/news where relevant",'
        f'"key_factors":["current factor 1","current factor 2","current factor 3"],'
        f'"verdict":"Your recommendation based on current information",'
        f'"confidence":70}}',
        max_tokens=600,
    )
    return {
        'success': True,
        'intent': intent,
        'home_team': None,
        'away_team': None,
        'answer': (ai or {}).get('answer',
            f'As of {TODAY}, please mention two team names for a full prediction, '
            f'e.g. "Who will win Arsenal vs Chelsea?"'),
        'verdict': (ai or {}).get('verdict', ''),
        'key_factors': (ai or {}).get('key_factors', []),
        'match_prediction': None,
        'simulation': None,
        'confidence': (ai or {}).get('confidence', 0),
        'data_sources': data_sources,
    }
