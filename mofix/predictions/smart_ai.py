import json, os, requests, re, logging
from django.conf import settings
from .engine import (
    search_web, extract_match_data, extract_player_data,
    extract_upcoming_matches, detect_intent,
    _build_match_engine_input, _build_sim_engine_input,
    engine_a, engine_b, engine_d, get_confidence_badge,
    consensus_prediction,
)

logger = logging.getLogger(__name__)


def call_ai(system, user_msg, max_tokens=800):
    key = settings.MATCHORACLE.get('ANTHROPIC_API_KEY', '') or os.environ.get('ANTHROPIC_API_KEY', '')
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
                'model': 'claude-3-sonnet-20240229',
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

        # 3a. Try Sportmonks for today's fixture
        todays_match = get_todays_match(home_team, away_team)
        competition = 'League'
        extra_context = ''

        # 3b. Web search for real stats
        search_q = f"{home_team} vs {away_team} prediction form injuries stats 2024"
        web_results = search_web(search_q)
        if web_results:
            data_sources.append('web_search')
        if todays_match:
            data_sources.append('sportmonks')

        web_data = extract_match_data(web_results, home_team, away_team)

        # Also search for upcoming match context
        upcoming = extract_upcoming_matches(web_results, home_team)
        if upcoming:
            competition = upcoming.get('competition', 'League').title()

        # 3c. Build engine inputs from web data (+ safe defaults)
        engine_data = _build_match_engine_input(home_team, away_team, web_data)
        sim_data = _build_sim_engine_input(home_team, away_team, web_data)

        # 3d. Run Engine A
        try:
            match_result = engine_a(engine_data)
        except Exception as e:
            logger.error(f"Engine A error in smart_predict: {e}")
            match_result = None

        # 3e. Run Engine D simulation
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

        # 3f. Build comprehensive AI narrative
        match_info = "Today's match" if todays_match else "Upcoming match"
        snippets_text = ' | '.join(web_data.get('raw_snippets', []))
        ai_answer = call_ai(
            'You are MatchOracle AI, an expert football intelligence assistant. You provide detailed, conversational, expert-level match analysis. Return ONLY valid JSON.',
            f'User asked: "{question}"\n'
            f'Match: {home_team} vs {away_team} ({competition}) - {match_info}\n'
            f'Real-world web data: {snippets_text[:400]}\n'
            f'Engine A probabilities: Home {match_result["home_win"]}% | Draw {match_result["draw"]}% | Away {match_result["away_win"]}%\n'
            f'Engine A predicted score: {match_result.get("predicted_score","1-1")}\n'
            f'Engine A tactical insight: {match_result.get("insight","")}\n'
            f'Monte Carlo simulation (10,000 runs): Most likely score {sim_result["likely_score"] if sim_result else "N/A"}\n'
            f'Confidence: {match_result["confidence"]}%\n'
            f'Data sources: {", ".join(data_sources) or "statistical defaults"}\n'
            f'Task: Based on ALL the above data, give a detailed expert analysis. Explain WHY one team is likely to win — reference their form, any injury concerns, head-to-head history, tactical advantages, and the statistical probabilities. '
            f'Your verdict must be based on your own analysis of the data, not just the highest percentage.\n'
            f'Return JSON: {{"answer":"3-4 sentence expert analysis explaining WHY the predicted winner will win, mentioning key factors like form, injuries, tactics, and the probability percentages",'
            f'"verdict":"name of the team most likely to win OR Draw",'
            f'"key_factors":["specific factor 1","specific factor 2","specific factor 3"],'
            f'"betting_insight":"one sentence on the most confident betting angle for this match",'
            f'"confidence_reasoning":"one sentence explaining the confidence level"}}',
            max_tokens=700,
        )



        if ai_answer:
            final_answer = ai_answer.get('answer', '')
            key_factors = ai_answer.get('key_factors', [])
            betting_insight = ai_answer.get('betting_insight', '')
            confidence_reasoning = ai_answer.get('confidence_reasoning', '')
            # Use AI's verdict if it returned one, otherwise fall back to engine verdict
            ai_verdict = ai_answer.get('verdict', match_result['verdict'])
        else:
            final_answer = (
                f"Based on statistical analysis, {match_result['verdict']} is predicted to win "
                f"({match_result['home_win']}% home / {match_result['draw']}% draw / "
                f"{match_result['away_win']}% away). "
                f"Predicted score: {match_result.get('predicted_score','1-1')}. "
                f"Monte Carlo simulation most likely score: {sim_result['likely_score'] if sim_result else 'N/A'}."
            )
            key_factors = []
            betting_insight = ''
            confidence_reasoning = ''
            ai_verdict = match_result['verdict']


        # 3g. Build Smart AI result dict for consensus (carries home_win/draw/away_win)
        smart_ai_for_consensus = None
        if ai_answer and 'homeWin' in ai_answer:
            # AI returned raw probabilities
            smart_ai_for_consensus = {
                'home_win': float(ai_answer.get('homeWin', match_result['home_win'])) * 100,
                'draw': float(ai_answer.get('draw', match_result['draw'])) * 100,
                'away_win': float(ai_answer.get('awayWin', match_result['away_win'])) * 100,
                'verdict': ai_verdict,
            }
        else:
            # Use Engine A percentages as Smart AI proxy, but with AI's verdict
            smart_ai_for_consensus = {
                'home_win': match_result['home_win'],
                'draw': match_result['draw'],
                'away_win': match_result['away_win'],
                'verdict': ai_verdict,
            }

        # 3h. Compute final consensus across all three engines
        consensus = None
        if sim_result:
            try:
                consensus = consensus_prediction(
                    engine_a_result=match_result,
                    engine_d_result=sim_result,
                    smart_ai_result=smart_ai_for_consensus,
                )
                # Attach team names to consensus for template use
                consensus['home_team'] = home_team
                consensus['away_team'] = away_team
            except Exception as e:
                logger.error(f"consensus_prediction error in smart_predict: {e}")

        return {
            'success': True,
            'intent': intent,
            'home_team': home_team,
            'away_team': away_team,
            'competition': competition,
            'is_today': todays_match is not None,
            'match_prediction': match_result,
            'simulation': sim_result,
            'consensus': consensus,
            'answer': final_answer,
            'verdict': ai_verdict,
            'predicted_score': match_result.get('predicted_score', '1-1'),
            'likely_score': sim_result['likely_score'] if sim_result else 'N/A',
            'confidence': match_result['confidence'],
            'confidence_badge': get_confidence_badge(match_result['confidence']),
            'key_factors': key_factors,
            'betting_insight': betting_insight,
            'confidence_reasoning': confidence_reasoning,
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

    # ── 6. Match prediction requested but no teams found ────────────────────
    if intent == 'match_prediction':
        return {
            'success': False,
            'intent': intent,
            'home_team': None,
            'away_team': None,
            'answer': 'Please mention two team names for a full prediction, e.g. "Who will win Arsenal vs Chelsea?"',
            'verdict': '',
            'key_factors': [],
            'match_prediction': None,
            'simulation': None,
            'confidence': 0,
            'data_sources': data_sources,
        }

    # ── 7. General / conversational (greetings, questions, anything else) ───
    # Determine the right system prompt based on whether this looks like a
    # greeting/casual message or a genuine football question.
    q_lower = question.lower().strip()
    greeting_words = ['hello', 'hi', 'hey', 'good morning', 'good afternoon',
                      'good evening', 'how are you', "what's up", 'sup', 'greetings']
    is_greeting = any(q_lower.startswith(g) or q_lower == g for g in greeting_words)

    if is_greeting:
        system_prompt = (
            'You are MatchOracle AI, a friendly and knowledgeable football assistant. '
            'Respond warmly and conversationally to greetings and casual messages. '
            'Keep your reply brief and friendly, and invite the user to ask a football question. '
            'Return ONLY valid JSON.'
        )
        user_prompt = (
            f'The user said: "{question}"\n'
            f'Respond in a friendly, conversational way. '
            f'Return: {{"answer":"your warm conversational reply","key_factors":[],"verdict":""}}'
        )
    else:
        system_prompt = (
            'You are MatchOracle AI, an expert football assistant. '
            'Answer football questions with insight and expertise. '
            'Return ONLY valid JSON.'
        )
        user_prompt = (
            f'Football question: "{question}"\n'
            f'Return: {{"answer":"3-4 sentence expert answer","key_factors":["f1","f2","f3"],"verdict":"Your recommendation"}}'
        )

    ai = call_ai(system_prompt, user_prompt, max_tokens=500)

    # Fallback message if Claude is unavailable — only prompt for teams if
    # the question genuinely looks like a prediction request.
    prediction_words = ['win', 'beat', 'predict', 'score', 'result', 'who will', 'vs', 'versus']
    looks_like_prediction = any(w in q_lower for w in prediction_words)
    if looks_like_prediction:
        fallback_answer = 'Please mention two team names for a full prediction, e.g. "Who will win Arsenal vs Chelsea?"'
    else:
        fallback_answer = "Hello! I'm MatchOracle AI, your football intelligence assistant. Ask me about match predictions, player comparisons, or any football question!"

    return {
        'success': True,
        'intent': intent,
        'home_team': None,
        'away_team': None,
        'answer': (ai or {}).get('answer', fallback_answer),
        'verdict': (ai or {}).get('verdict', ''),
        'key_factors': (ai or {}).get('key_factors', []),
        'match_prediction': None,
        'simulation': None,
        'confidence': 0,
        'data_sources': data_sources,
    }
