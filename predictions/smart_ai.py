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
from .sportmonks_client import (
    get_live_matches, get_todays_fixtures, get_league_standings,
    get_league_id_for_question, get_team_recent_fixtures,
)
from .news_client import fetch_football_news, format_news_for_context

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
            timeout=25
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


def _build_live_context(question, teams=None):
    """
    Gather live internet data: today's fixtures, live matches, league standings,
    and current news. Returns a dict with all fetched data plus a compact
    text summary suitable for inclusion in an AI prompt.
    """
    live_matches = get_live_matches()
    todays_fixtures = get_todays_fixtures()
    news_articles = fetch_football_news(question)
    league_id = get_league_id_for_question(question)
    standings = get_league_standings(league_id) if league_id else []

    # Fetch team-specific recent fixtures if teams are known
    team_fixtures = {}
    if teams:
        for team in teams[:2]:
            recent = get_team_recent_fixtures(team, limit=3)
            if recent:
                team_fixtures[team] = recent

    # Build compact text summary for the AI prompt
    parts = []

    if live_matches:
        live_lines = [
            f"  • {m['home']} {m.get('home_score','?')}-{m.get('away_score','?')} {m['away']}"
            f" ({m.get('league','')}, {m.get('minute','?')}' LIVE)"
            for m in live_matches[:6]
        ]
        parts.append("LIVE MATCHES RIGHT NOW:\n" + '\n'.join(live_lines))

    if todays_fixtures:
        today_lines = []
        for f in todays_fixtures[:8]:
            status = f.get('status', '')
            if f.get('home_score') is not None:
                score = f"{f['home_score']}-{f['away_score']}"
                today_lines.append(f"  • {f['home']} {score} {f['away']} ({f.get('league','')}) [{status}]")
            else:
                today_lines.append(f"  • {f['home']} vs {f['away']} ({f.get('league','')}) [{status}]")
        if today_lines:
            parts.append("TODAY'S FIXTURES:\n" + '\n'.join(today_lines))

    if standings:
        top5 = standings[:5]
        stand_lines = [
            f"  {s.get('position','?')}. {s.get('team','')} — {s.get('points',0)} pts "
            f"({s.get('won',0)}W {s.get('drawn',0)}D {s.get('lost',0)}L, GD {s.get('gd',0)})"
            for s in top5
        ]
        parts.append("CURRENT LEAGUE STANDINGS (Top 5):\n" + '\n'.join(stand_lines))

    if news_articles:
        parts.append("LATEST FOOTBALL NEWS:\n" + format_news_for_context(news_articles))

    context_text = '\n\n'.join(parts) if parts else 'No live data available at this moment.'

    return {
        'live_matches': live_matches,
        'todays_fixtures': todays_fixtures,
        'standings': standings,
        'news': news_articles,
        'team_fixtures': team_fixtures,
        'context_text': context_text,
        'has_live_data': bool(live_matches or todays_fixtures or news_articles or standings),
    }


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
    prediction by detecting intent, fetching LIVE internet data (Sportmonks +
    NewsAPI + DuckDuckGo), running ALL prediction engines, comparing results,
    and compiling a consensus answer grounded in current information.

    Intent routing:
      match_prediction  → Engine A + Engine D + consensus comparison
      player_comparison → Engine B (per player) + comparison narrative
      simulation        → Engine D
      general           → Claude AI with live context
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

    # ── 3. Fetch live internet context (runs for ALL intents) ───────────────
    live_ctx = _build_live_context(question, teams=teams if teams else None)
    if live_ctx['has_live_data']:
        data_sources.append('live_data')
    if live_ctx['news']:
        data_sources.append('news')
    if live_ctx['live_matches'] or live_ctx['todays_fixtures']:
        data_sources.append('sportmonks')

    # ── 4. Match prediction: run Engine A + Engine D, build consensus ────────
    if intent == 'match_prediction' and len(teams) >= 2:
        home_team, away_team = teams[0], teams[1]

        # Check if match is today via today's fixtures
        todays_match = None
        ht_lower = home_team.lower()
        at_lower = away_team.lower()
        for f in live_ctx['todays_fixtures']:
            fh = f.get('home', '').lower()
            fa = f.get('away', '').lower()
            if (ht_lower in fh or fh in ht_lower) and (at_lower in fa or fa in at_lower):
                todays_match = f
                break

        competition = 'League'

        # Fetch web search data for engine inputs
        search_q = f"{home_team} vs {away_team} prediction form injuries stats 2025"
        web_results = search_web(search_q)
        if web_results:
            data_sources.append('web_search')

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
                'live_matches': live_ctx['live_matches'],
                'todays_fixtures': live_ctx['todays_fixtures'],
                'standings': live_ctx['standings'],
                'news': live_ctx['news'],
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

        # Build AI prompt enriched with live context
        ai_answer = call_ai(
            'You are MatchOracle Smart AI, a football intelligence system with access to '
            'REAL-TIME data. You have been given live match data, current standings, and '
            'the latest news. Use this current information to give an accurate, up-to-date '
            'answer. Return ONLY valid JSON.',
            f'User asked: "{question}"\n'
            f'Match: {home_team} vs {away_team} ({competition}) - {match_info}\n\n'
            f'=== LIVE INTERNET DATA ===\n{live_ctx["context_text"][:600]}\n\n'
            f'=== WEB SEARCH SNIPPETS ===\n{snippets_text[:300]}\n\n'
            f'=== ENGINE RESULTS ===\n'
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
            f'Return JSON: {{"answer":"3-5 sentence expert analysis using the live data above, '
            f'mentioning both engines, percentages, and current form/news",'
            f'"key_factors":["factor1","factor2","factor3"],'
            f'"betting_insight":"one sentence about the best bet based on current data"}}',
            max_tokens=800,
        )

        if ai_answer:
            final_answer = ai_answer.get('answer', '')
            key_factors = ai_answer.get('key_factors', [])
            betting_insight = ai_answer.get('betting_insight', '')
        else:
            final_answer = (
                f"Based on live internet data, Engine A predicts {consensus['engine_a_verdict']} "
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
            'home_win': match_result['home_win'],
            'draw': match_result['draw'],
            'away_win': match_result['away_win'],
            'data_sources': data_sources,
            # Live data for UI display
            'live_matches': live_ctx['live_matches'],
            'todays_fixtures': live_ctx['todays_fixtures'],
            'standings': live_ctx['standings'],
            'news': live_ctx['news'],
        }

    # ── 5. Player comparison ────────────────────────────────────────────────
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
                'You are MatchOracle AI. Compare football players using current data. Return ONLY valid JSON.',
                f'User asked: "{question}"\n'
                f'Engine B player ratings:\n{comparison_text}\n\n'
                f'=== LATEST NEWS ===\n{live_ctx["context_text"][:400]}\n\n'
                f'Data sources: {", ".join(data_sources) or "defaults"}\n'
                f'Return JSON: {{"answer":"3-4 sentence comparison with ratings and current form",'
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
                'live_matches': live_ctx['live_matches'],
                'todays_fixtures': live_ctx['todays_fixtures'],
                'standings': live_ctx['standings'],
                'news': live_ctx['news'],
            }

    # ── 6. Simulation ───────────────────────────────────────────────────────
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
                'You are MatchOracle AI. Explain simulation results using current data. Return ONLY valid JSON.',
                f'User asked: "{question}"\n'
                f'Simulation ({sim_result["simulations"]} runs): '
                f'Home {sim_result["home_win"]}% Draw {sim_result["draw"]}% Away {sim_result["away_win"]}%\n'
                f'Most likely score: {sim_result["likely_score"]}\n\n'
                f'=== LIVE CONTEXT ===\n{live_ctx["context_text"][:400]}\n\n'
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
                'live_matches': live_ctx['live_matches'],
                'todays_fixtures': live_ctx['todays_fixtures'],
                'standings': live_ctx['standings'],
                'news': live_ctx['news'],
            }

    # ── 7. General football question — Claude with live context ─────────────
    ai = call_ai(
        'You are MatchOracle Smart AI, a football expert with access to REAL-TIME data. '
        'Use the live context provided to give an accurate, current answer. '
        'Return ONLY valid JSON.',
        f'Football question: "{question}"\n\n'
        f'=== LIVE INTERNET DATA ===\n{live_ctx["context_text"][:700]}\n\n'
        f'Return: {{"answer":"3-5 sentence expert answer using the live data above",'
        f'"key_factors":["f1","f2","f3"],"verdict":"Your recommendation based on current data"}}',
        max_tokens=600,
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
        'live_matches': live_ctx['live_matches'],
        'todays_fixtures': live_ctx['todays_fixtures'],
        'standings': live_ctx['standings'],
        'news': live_ctx['news'],
    }
