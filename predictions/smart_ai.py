import json
import requests
import re
import logging
from django.conf import settings
from .engine import (
    search_web, extract_match_data, extract_player_data,
    extract_upcoming_matches, detect_intent,
    _build_match_engine_input, _build_sim_engine_input,
    _build_consensus,
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
                'model': 'claude-opus-4-1-20250805',
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
    Smart AI Orchestrator — takes a natural language question and returns a full
    prediction by detecting intent, fetching live internet data, running ALL
    prediction engines, comparing results, and compiling a consensus.

    Intent routing:
      match_prediction  → Engine A + Engine D + consensus comparison
      player_comparison → Engine B (per player) + comparison narrative
      simulation        → Engine D
      general           → Claude AI only
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

        # Fetch live internet data
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

        match_info = "Today's match" if todays_match else "Upcoming match"
        snippets_text = ' | '.join(web_data.get('raw_snippets', []))

        # ── Claude generates its OWN independent prediction ─────────────────
        claude_raw = call_ai(
            'You are MatchOracle AI, a world-class football analyst. Generate your own independent prediction. Return ONLY valid JSON.',
            f'Match: {home_team} vs {away_team} ({competition}) — {match_info}\n'
            f'Live data: {snippets_text[:300]}\n'
            f'Based on current form, injuries, head-to-head, and tactical analysis:\n'
            f'Return JSON: {{"verdict":"{home_team} or {away_team} or Draw",'
            f'"confidence":85,"score":"2-1",'
            f'"reasoning":"3-4 sentences of expert analysis",'
            f'"betting_insight":"one sentence about the best bet"}}',
            max_tokens=500,
        )

        # Parse Claude's prediction
        if claude_raw:
            claude_verdict = claude_raw.get('verdict', '').strip()
            claude_confidence = int(claude_raw.get('confidence', 70))
            claude_score = claude_raw.get('score', '1-1')
            claude_reasoning = claude_raw.get('reasoning', '')
            claude_betting = claude_raw.get('betting_insight', '')
        else:
            claude_verdict = consensus['final_verdict']
            claude_confidence = consensus['confidence']
            claude_score = match_result.get('predicted_score', '1-1')
            claude_reasoning = ''
            claude_betting = ''

        # ── Compare all 3: Claude + Engine A + Engine D ──────────────────────
        engine_a_verdict = consensus['engine_a_verdict']
        engine_d_verdict = consensus['engine_d_verdict']
        engine_a_score = match_result.get('predicted_score', '1-1')
        engine_a_confidence = match_result.get('confidence', 60)
        engine_d_score = sim_result['likely_score'] if sim_result else 'N/A'
        engine_d_confidence = int(max(
            sim_result.get('home_win', 0),
            sim_result.get('draw', 0),
            sim_result.get('away_win', 0),
        )) if sim_result else 50

        # Count agreement across all 3 sources
        all_verdicts = [v for v in [claude_verdict, engine_a_verdict, engine_d_verdict] if v]
        if all_verdicts:
            from collections import Counter
            verdict_counts = Counter(all_verdicts)
            best_verdict, best_count = verdict_counts.most_common(1)[0]
        else:
            best_verdict = consensus['final_verdict']
            best_count = 1

        agreement_count = best_count  # how many of the 3 agree on best_verdict

        # Determine best outcome: prefer highest agreement, then highest confidence
        if agreement_count >= 2:
            final_verdict = best_verdict
            agreeing_confidences = []
            if claude_verdict == best_verdict:
                agreeing_confidences.append(claude_confidence)
            if engine_a_verdict == best_verdict:
                agreeing_confidences.append(engine_a_confidence)
            if engine_d_verdict == best_verdict:
                agreeing_confidences.append(engine_d_confidence)
            final_confidence = max(agreeing_confidences) if agreeing_confidences else consensus['confidence']
        else:
            # No majority — trust Claude + Engine A (Engine A has more data)
            if claude_verdict == engine_a_verdict and claude_verdict:
                final_verdict = claude_verdict
                final_confidence = max(claude_confidence, engine_a_confidence)
                agreement_count = 2
            else:
                final_verdict = claude_verdict or consensus['final_verdict']
                final_confidence = claude_confidence or consensus['confidence']
                agreement_count = 1

        final_confidence = min(95, max(40, final_confidence))

        # Best score: from the source with highest confidence
        source_scores = [
            (claude_confidence, claude_score, 'Claude'),
            (engine_a_confidence, engine_a_score, 'Engine A'),
            (engine_d_confidence, engine_d_score, 'Engine D'),
        ]
        best_score = max(source_scores, key=lambda x: x[0])[1]

        # Build reasoning from Claude (or fallback)
        if not claude_reasoning:
            if agreement_count >= 2:
                claude_reasoning = (
                    f"{agreement_count} out of 3 prediction engines agree that {final_verdict} is the most likely outcome. "
                    f"Engine A gives {engine_a_verdict} at {engine_a_confidence}% confidence, "
                    f"Engine D simulation predicts {engine_d_verdict} with score {engine_d_score}. "
                    f"The consensus strongly favours {final_verdict}."
                )
            else:
                claude_reasoning = (
                    f"Engines show mixed signals for {home_team} vs {away_team}. "
                    f"Engine A predicts {engine_a_verdict} ({engine_a_confidence}%), "
                    f"Engine D leans {engine_d_verdict}. "
                    f"Claude AI independently assesses {claude_verdict} as the most likely outcome."
                )

        if not claude_betting:
            claude_betting = (
                f"Strong consensus for {final_verdict} — {agreement_count}/3 engines agree."
                if agreement_count >= 2
                else "Mixed signals — consider a smaller stake or wait for more data."
            )

        key_factors = [
            f"Claude AI: {claude_verdict} ({claude_confidence}%) — Score: {claude_score}",
            f"Engine A: {engine_a_verdict} ({engine_a_confidence}%) — Score: {engine_a_score}",
            f"Engine D: {engine_d_verdict} ({engine_d_confidence}%) — Score: {engine_d_score}",
        ]

        return {
            'success': True,
            'intent': intent,
            'home_team': home_team,
            'away_team': away_team,
            'competition': competition,
            'is_today': todays_match is not None,
            'match_prediction': match_result,
            'simulation': sim_result,
            # Claude's own prediction
            'claude_prediction': {
                'verdict': claude_verdict,
                'confidence': claude_confidence,
                'score': claude_score,
                'reasoning': claude_reasoning,
            },
            # Engine A result
            'engine_a_result': {
                'verdict': engine_a_verdict,
                'confidence': engine_a_confidence,
                'score': engine_a_score,
            },
            # Engine D result
            'engine_d_result': {
                'verdict': engine_d_verdict,
                'confidence': engine_d_confidence,
                'score': engine_d_score,
            },
            # Best outcome
            'best_outcome': final_verdict,
            'best_score': best_score,
            'agreement_count': agreement_count,
            'reasoning': claude_reasoning,
            'betting_insight': claude_betting,
            # Legacy fields for backward compatibility
            'answer': claude_reasoning,
            'verdict': final_verdict,
            'predicted_score': engine_a_score,
            'likely_score': engine_d_score,
            'confidence': final_confidence,
            'confidence_badge': get_confidence_badge(final_confidence),
            'consensus': consensus,
            'key_factors': key_factors,
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

    # ── 6. Health questions ─────────────────────────────────────────────────
    if intent == 'health_question':
        results = search_web(question)
        if results:
            data_sources.append('web_search')

        ai_answer = call_ai(
            'You are a helpful AI assistant. For health questions, ALWAYS include a clear disclaimer '
            'that this is general information only and not a substitute for professional medical advice. '
            'Return ONLY valid JSON.',
            f'Question: "{question}"\n'
            f'Web data: {" | ".join(r.get("snippet", "") for r in results[:3]) if results else "N/A"}\n'
            f'Return JSON: {{"answer":"informative response with general health information",'
            f'"disclaimer":"⚠️ DISCLAIMER: This is general information only, not medical advice. '
            f'Always consult a qualified healthcare professional for medical concerns.",'
            f'"key_factors":["point1","point2","point3"]}}',
            max_tokens=600,
        )

        default_disclaimer = (
            '⚠️ DISCLAIMER: This is general information only, not medical advice. '
            'Always consult a qualified healthcare professional for medical concerns.'
        )
        return {
            'success': True,
            'intent': intent,
            'answer': (ai_answer or {}).get('answer', ''),
            'disclaimer': (ai_answer or {}).get('disclaimer', default_disclaimer),
            'key_factors': (ai_answer or {}).get('key_factors', []),
            'home_team': None,
            'away_team': None,
            'match_prediction': None,
            'simulation': None,
            'data_sources': data_sources,
        }

    # ── 7. News / current events questions ─────────────────────────────────
    if intent == 'news_question':
        results = search_web(question)
        if results:
            data_sources.append('web_search')

        ai_answer = call_ai(
            'You are a news analyst. Provide current, factual information based on available data. '
            'Return ONLY valid JSON.',
            f'Question: "{question}"\n'
            f'Latest data: {" | ".join(r.get("snippet", "") for r in results[:3]) if results else "N/A"}\n'
            f'Return JSON: {{"answer":"news summary with key facts","key_factors":["fact1","fact2","fact3"]}}',
            max_tokens=600,
        )

        return {
            'success': True,
            'intent': intent,
            'answer': (ai_answer or {}).get('answer', ''),
            'key_factors': (ai_answer or {}).get('key_factors', []),
            'home_team': None,
            'away_team': None,
            'match_prediction': None,
            'simulation': None,
            'data_sources': data_sources,
        }

    # ── 8. General knowledge questions ─────────────────────────────────────
    if intent == 'general_knowledge':
        results = search_web(question)
        if results:
            data_sources.append('web_search')

        ai_answer = call_ai(
            'You are a knowledgeable AI assistant. Provide accurate, helpful, and well-structured information. '
            'Return ONLY valid JSON.',
            f'Question: "{question}"\n'
            f'Information: {" | ".join(r.get("snippet", "") for r in results[:3]) if results else "N/A"}\n'
            f'Return JSON: {{"answer":"detailed and informative explanation",'
            f'"key_factors":["point1","point2","point3"]}}',
            max_tokens=600,
        )

        return {
            'success': True,
            'intent': intent,
            'answer': (ai_answer or {}).get('answer', ''),
            'key_factors': (ai_answer or {}).get('key_factors', []),
            'home_team': None,
            'away_team': None,
            'match_prediction': None,
            'simulation': None,
            'data_sources': data_sources,
        }

    # ── 9. General football question (Claude only) ──────────────────────────
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
