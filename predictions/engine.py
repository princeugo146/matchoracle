import math, random, json, re, time, requests, logging
from django.conf import settings

logger = logging.getLogger(__name__)

# ─── Simple in-process search cache (TTL: 5 minutes) ────────────────────────
_search_cache = {}
_CACHE_TTL = 300  # seconds


def _cache_get(key):
    entry = _search_cache.get(key)
    if entry and (time.time() - entry['ts']) < _CACHE_TTL:
        return entry['data']
    return None


def _cache_set(key, data):
    _search_cache[key] = {'data': data, 'ts': time.time()}


# ─── Web Search (DuckDuckGo HTML – no API key required) ─────────────────────

def search_web(query, max_results=5):
    """
    Search DuckDuckGo for football information.
    Returns a list of result dicts: [{title, snippet, url}, …]
    Falls back to an empty list on any error.
    """
    cached = _cache_get(query)
    if cached is not None:
        return cached

    results = []
    try:
        headers = {
            'User-Agent': (
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/120.0.0.0 Safari/537.36'
            ),
            'Accept-Language': 'en-US,en;q=0.9',
        }
        resp = requests.get(
            'https://html.duckduckgo.com/html/',
            params={'q': query, 'kl': 'us-en'},
            headers=headers,
            timeout=10,
        )
        if resp.status_code == 200:
            snippets = re.findall(
                r'class="result__snippet"[^>]*>(.*?)</a>',
                resp.text, re.DOTALL
            )
            titles = re.findall(
                r'class="result__a"[^>]*>(.*?)</a>',
                resp.text, re.DOTALL
            )
            urls = re.findall(
                r'class="result__url"[^>]*>(.*?)</span>',
                resp.text, re.DOTALL
            )
            for i in range(min(max_results, len(snippets))):
                title = re.sub(r'<[^>]+>', '', titles[i]).strip() if i < len(titles) else ''
                snippet = re.sub(r'<[^>]+>', '', snippets[i]).strip()
                url = urls[i].strip() if i < len(urls) else ''
                if snippet:
                    results.append({'title': title, 'snippet': snippet, 'url': url})
    except Exception as e:
        logger.warning(f"Web search failed for '{query}': {e}")

    _cache_set(query, results)
    return results


def _combine_text(results):
    """Flatten search results into a single text blob for regex parsing."""
    return ' '.join(
        f"{r.get('title','')} {r.get('snippet','')}" for r in results
    ).lower()


# ─── Data Extractors ─────────────────────────────────────────────────────────

def extract_match_data(search_results, home_team, away_team):
    """Parse search snippets for team stats. Returns engine_a-compatible dict."""
    text = _combine_text(search_results)
    data = {
        'home': {'name': home_team}, 'away': {'name': away_team}, 'h2h': {},
        'data_source': 'web_search',
        'raw_snippets': [r.get('snippet', '') for r in search_results[:3]],
    }
    inj_pat = re.compile(r'(\d+)\s+(?:player[s]?\s+)?(?:injur|doubt|miss)')
    injuries = inj_pat.findall(text)
    gpg_pat = re.compile(r'(\d+\.?\d*)\s+goals?\s+(?:per|a)\s+game')
    gpg = gpg_pat.findall(text)
    pos_pat = re.compile(r'(?:position|placed?|sit[st]?|rank[s]?)\s+(?:at\s+)?(\d+)')
    positions = pos_pat.findall(text)
    wr_pat = re.compile(r'(\d+)%?\s+win\s+(?:rate|percentage)')
    win_rates = wr_pat.findall(text)
    h2h_pat = re.compile(r'(?:won|win)\s+(\d+)\s+(?:of\s+(?:the\s+)?last\s+(\d+)|times?)')
    h2h_matches = h2h_pat.findall(text)
    if len(gpg) >= 1: data['home']['goals_scored'] = float(gpg[0])
    if len(gpg) >= 2: data['away']['goals_scored'] = float(gpg[1])
    if len(positions) >= 1: data['home']['position'] = int(positions[0])
    if len(positions) >= 2: data['away']['position'] = int(positions[1])
    if len(win_rates) >= 1: data['home']['win_rate'] = int(win_rates[0])
    if len(win_rates) >= 2: data['away']['win_rate'] = int(win_rates[1])
    if injuries: data['home']['injuries'] = int(injuries[0])
    if len(injuries) >= 2: data['away']['injuries'] = int(injuries[1])
    if h2h_matches:
        wins, total = h2h_matches[0]
        data['h2h']['home_wins'] = int(wins)
        if total:
            rest = int(total) - int(wins)
            data['h2h']['draws'] = rest // 2
            data['h2h']['away_wins'] = rest - rest // 2
    return data


def extract_player_data(search_results, player_name):
    """Parse search snippets for player stats. Returns engine_b-compatible dict."""
    text = _combine_text(search_results)
    data = {
        'name': player_name, 'data_source': 'web_search',
        'raw_snippets': [r.get('snippet', '') for r in search_results[:3]],
    }
    goals = re.findall(r'(\d+)\s+goals?\s+(?:this\s+season|in\s+\d+\s+games?|scored)', text)
    if goals: data['goals'] = int(goals[0])
    assists = re.findall(r'(\d+)\s+assists?', text)
    if assists: data['assists'] = int(assists[0])
    apps = re.findall(r'(\d+)\s+(?:appearances?|games?|matches?)', text)
    if apps: data['games'] = int(apps[0])
    pos_keywords = {
        'goalkeeper': 'GK', 'keeper': 'GK', 'centre-back': 'CB', 'defender': 'CB',
        'midfielder': 'CM', 'attacking mid': 'CAM', 'striker': 'ST', 'forward': 'ST', 'winger': 'CAM',
    }
    for kw, pos in pos_keywords.items():
        if kw in text:
            data['position'] = pos
            break
    pass_acc = re.findall(r'(\d+)%?\s+pass(?:ing)?\s+accuracy', text)
    if pass_acc: data['pass_accuracy'] = float(pass_acc[0])
    if any(w in text for w in ['injured', 'out for', 'ruled out', 'sidelined']):
        data['injury_status'] = 'major'
    elif any(w in text for w in ['doubt', 'fitness concern', 'minor knock']):
        data['injury_status'] = 'doubt'
    else:
        data['injury_status'] = 'fit'
    return data


def extract_upcoming_matches(search_results, team_name):
    """Parse search results for the team's next fixture. Returns dict or None."""
    text = _combine_text(search_results)
    team_lower = team_name.lower()
    vs_pat = re.compile(r'([a-z\s]{3,25})\s+(?:vs?\.?|versus)\s+([a-z\s]{3,25})')
    for home, away in vs_pat.findall(text):
        home = home.strip(); away = away.strip()
        if team_lower in home or team_lower in away:
            return {'home_team': home.title(), 'away_team': away.title(), 'competition': 'league'}
    dates = re.findall(r'next\s+(?:match|game|fixture)\s+(?:on\s+)?(\d{1,2}\s+\w+|\w+\s+\d{1,2})', text)
    if dates:
        return {'team': team_name, 'date': dates[0], 'competition': 'league'}
    return None


# ─── Intent Detection ─────────────────────────────────────────────────────────

def detect_intent(question):
    """Classify question intent: match_prediction, player_comparison, simulation, general."""
    q = question.lower()
    if any(k in q for k in ['simulat', 'run a sim', 'monte carlo']):
        return {'intent': 'simulation', 'teams': _extract_team_names(q), 'players': [], 'confidence': 90}
    if any(k in q for k in ['messi', 'ronaldo', 'haaland', 'mbappe', 'salah', 'kane',
                              'better player', 'best player', 'compare', 'who is better', 'goat']):
        return {'intent': 'player_comparison', 'teams': [], 'players': _extract_player_names(q), 'confidence': 85}
    if any(k in q for k in ['win', 'beat', 'vs', 'versus', 'v ', 'match', 'game', 'predict', 'score', 'result']):
        teams = _extract_team_names(q)
        if teams:
            return {'intent': 'match_prediction', 'teams': teams, 'players': [], 'confidence': 85}
    return {'intent': 'general', 'teams': [], 'players': [], 'confidence': 60}


def _extract_team_names(text):
    m = re.search(r'([A-Za-z\s]{3,25}?)\s+(?:vs?\.?|versus|v\s)\s*([A-Za-z\s]{3,25})', text, re.IGNORECASE)
    if m:
        return [m.group(1).strip().title(), m.group(2).strip().title()]
    known = ['Arsenal','Chelsea','Liverpool','Manchester City','Manchester United','Tottenham',
             'Newcastle','Real Madrid','Barcelona','Bayern Munich','PSG','Juventus','Inter Milan']
    return [c for c in known if c.lower() in text.lower()][:2]


def _extract_player_names(text):
    known = ['Messi','Ronaldo','Haaland','Mbappe','Salah','Kane','Neymar','De Bruyne',
             'Bellingham','Vinicius','Lewandowski','Benzema','Modric','Saka','Rashford']
    return [p for p in known if p.lower() in text.lower()][:2]

def clamp(v, lo, hi):
    return max(lo, min(hi, v))

def parse_form(s):
    if not s: return 0.5
    results = [c for c in s.upper() if c in 'WDL']
    if not results: return 0.5
    weights = [1, 0.9, 0.8, 0.7, 0.6]
    sc = {'W':1,'D':0.5,'L':0}
    total = sum(sc[r]*weights[i] for i,r in enumerate(results[:5]))
    wtotal = sum(weights[i] for i in range(min(len(results),5)))
    return total/wtotal if wtotal else 0.5

def call_ai(system, user_msg, max_tokens=600):
    key = settings.MATCHORACLE.get('ANTHROPIC_API_KEY','')
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
            timeout=15
        )
        if resp.status_code == 200:
            text = ''.join(b.get('text','') for b in resp.json().get('content',[]))
            clean = text.replace('```json','').replace('```','').strip()
            return json.loads(clean)
        else:
            logger.error(f"Anthropic error: {resp.status_code}")
    except Exception as e:
        logger.error(f"AI call failed: {e}")
    return None

def engine_a(data):
    home = data.get('home',{}); away = data.get('away',{}); h2h = data.get('h2h',{})
    hgs = float(home.get('goals_scored',1.5)); hgc = float(home.get('goals_conceded',1.0))
    ags = float(away.get('goals_scored',1.5)); agc = float(away.get('goals_conceded',1.0))
    hform = parse_form(home.get('form','')); aform = parse_form(away.get('form',''))
    hwr = float(home.get('win_rate',50))/100; awr = float(away.get('win_rate',45))/100
    hinj = int(home.get('injuries',0)); ainj = int(away.get('injuries',0))
    hpos = int(home.get('position',10)); apos = int(away.get('position',10))
    h2hh = int(h2h.get('home_wins',4)); h2hd = int(h2h.get('draws',3)); h2ha = int(h2h.get('away_wins',3))
    h2h_tot = h2hh + h2hd + h2ha or 10
    h_score = clamp(((hgs/max(agc,0.5))*0.22 + hform*0.28 + hwr*0.15 + ((20-hpos)/19)*0.10 + (h2hh/h2h_tot)*0.18)*1.15 - hinj*0.12, 0.1, 2.0)
    a_score = clamp((ags/max(hgc,0.5))*0.22 + aform*0.28 + awr*0.15 + ((20-apos)/19)*0.10 + (h2ha/h2h_tot)*0.18 - ainj*0.12, 0.1, 2.0)
    total = h_score + a_score
    draw_base = 0.22 + 0.08*(1-abs(h_score-a_score)/total)
    v1h = h_score/(total+draw_base*total); v1d = draw_base; v1a = a_score/(total+draw_base*total)
    s = v1h+v1d+v1a; v1h/=s; v1d/=s; v1a/=s
    hn = home.get('name','Home'); an = away.get('name','Away')
    ai = call_ai(
        'You are a football prediction AI. Return ONLY valid JSON with no extra text.',
        f"Match: {hn} vs {an}\nHome: form={hform:.0%} goals={hgs}/{hgc} injuries={hinj} pos={hpos}\n"
        f"Away: form={aform:.0%} goals={ags}/{agc} injuries={ainj} pos={apos}\n"
        f"H2H: {h2hh}W {h2hd}D {h2ha}A\nV1: Home={v1h:.1%} Draw={v1d:.1%} Away={v1a:.1%}\n"
        f'JSON: {{"homeWin":0.5,"draw":0.25,"awayWin":0.25,"insight":"2 sentence analysis.","predicted_score":"2-1"}}'
    )
    if ai and 'homeWin' in ai:
        fh = v1h*0.6 + float(ai['homeWin'])*0.4
        fd = v1d*0.6 + float(ai['draw'])*0.4
        fa = v1a*0.6 + float(ai['awayWin'])*0.4
    else:
        fh, fd, fa = v1h, v1d, v1a
    s2 = fh+fd+fa
    fh = round(fh/s2*1000)/10; fd = round(fd/s2*1000)/10; fa = round(fa/s2*1000)/10
    confidence = int(clamp(40+(max(fh,fd,fa)-33)*1.8, 40, 95))
    verdict = hn if fh>fa and fh>fd else (an if fa>fh and fa>fd else 'Draw')
    return {
        'home_win':fh,'draw':fd,'away_win':fa,'confidence':confidence,'verdict':verdict,
        'v1':{'home':round(v1h*100,1),'draw':round(v1d*100,1),'away':round(v1a*100,1)},
        'ai':ai,'predicted_score':ai.get('predicted_score','1-1') if ai else '1-1',
        'insight':ai.get('insight',f'V1 analysis complete. {verdict} predicted to win.') if ai else f'V1 result: {verdict} predicted.'
    }

def engine_b(data):
    pos = data.get('position','ST'); goals = float(data.get('goals',0))
    assists = float(data.get('assists',0)); games = max(float(data.get('games',1)),1)
    pass_acc = float(data.get('pass_accuracy',75)); shots_ot = float(data.get('shots_on_target',50))
    dribbles = float(data.get('dribble_success',50)); tackles = float(data.get('tackle_success',50))
    aerials = float(data.get('aerial_duels',50)); distance = float(data.get('distance_covered',10))
    yellows = float(data.get('yellow_cards',0)); injury = data.get('injury_status','fit')
    name = data.get('name','Player')
    pw = {
        'GK':{'pass':0.15,'tackle':0.35,'aerial':0.25,'dist':0.10,'goals':0.00,'assist':0.00,'shot':0.05,'drib':0.10},
        'CB':{'pass':0.15,'tackle':0.30,'aerial':0.30,'dist':0.10,'goals':0.02,'assist':0.02,'shot':0.01,'drib':0.10},
        'CM':{'pass':0.25,'tackle':0.20,'aerial':0.15,'dist':0.10,'goals':0.07,'assist':0.10,'shot':0.05,'drib':0.08},
        'CAM':{'pass':0.20,'tackle':0.10,'aerial':0.10,'dist':0.10,'goals':0.10,'assist':0.20,'shot':0.10,'drib':0.10},
        'ST':{'pass':0.10,'tackle':0.05,'aerial':0.15,'dist':0.10,'goals':0.30,'assist':0.10,'shot':0.15,'drib':0.05},
    }.get(pos,{'pass':0.20,'tackle':0.15,'aerial':0.15,'dist':0.10,'goals':0.12,'assist':0.12,'shot':0.08,'drib':0.08})
    scores = {
        'pass':clamp(pass_acc,0,100),'tackle':clamp(tackles,0,100),'aerial':clamp(aerials,0,100),
        'dist':clamp((distance/13)*100,0,100),'goals':clamp((goals/games/0.7)*100,0,100),
        'assist':clamp((assists/games/0.4)*100,0,100),'shot':clamp(shots_ot,0,100),'drib':clamp(dribbles,0,100)
    }
    rating = sum(scores[k]*pw.get(k,0) for k in scores)
    rating *= {'fit':1.0,'doubt':0.93,'minor':0.84,'major':0.70}.get(injury,1.0)
    rating = clamp(rating-(yellows/games)*2, 0, 99)
    ai = call_ai(
        'You are a football player rating AI. Return ONLY valid JSON with no extra text.',
        f'Player:{name} Pos:{pos} Goals:{goals} Assists:{assists} Games:{games} Pass:{pass_acc}% V1:{rating:.1f} Injury:{injury}\n'
        f'JSON: {{"adjusted_rating":80,"tier":"Elite","insight":"2 sentence player analysis."}}'
    )
    final = int(rating*0.55+float(ai['adjusted_rating'])*0.45) if ai and 'adjusted_rating' in ai else int(rating)
    tier = ai.get('tier') if ai else ('World Class' if final>=88 else 'Elite' if final>=80 else 'Quality' if final>=70 else 'Average' if final>=60 else 'Below Average')
    return {
        'rating':final,'v1_rating':round(rating,1),'tier':tier,
        'scores':{k:round(v,1) for k,v in scores.items()},'ai':ai,
        'insight':ai.get('insight',f'{name} rated {final}/100. {tier} level {pos}.') if ai else f'V1: {name} {final}/100 - {tier}'
    }

def compute_elo(wins, draws, losses, gf, ga, opp, base=1000):
    games = wins+draws+losses or 1
    return int(base+(wins/games)*400+((gf-ga)/games)*20+opp*30+((wins*3+draws)/games)*50)

def _poisson(lam):
    L = math.exp(-lam); k,p = 0,1.0
    while True:
        k+=1; p*=random.random()
        if p<=L: return k-1

def engine_d(data):
    home = data.get('home',{}); away = data.get('away',{})
    n = int(data.get('simulations',10000))
    weather = data.get('weather','normal'); comp = data.get('competition','league')
    h_atk=float(home.get('attack',75)); h_def=float(home.get('defence',70))
    h_elo=float(home.get('elo',1000)); h_inj=int(home.get('injuries',0))
    a_atk=float(away.get('attack',75)); a_def=float(away.get('defence',70))
    a_elo=float(away.get('elo',1000)); a_inj=int(away.get('injuries',0))
    wm={'normal':1.0,'rain':0.90,'wind':0.85,'heat':0.88}.get(weather,1.0)
    ha={'league':1.12,'champions':1.08,'cup':1.10,'friendly':1.05}.get(comp,1.10)
    im=[1.0,0.91,0.83,0.74]
    h_lam=clamp((h_atk/100)*(1-a_def/200)*2.8*ha*im[min(h_inj,3)]*wm*(1+(h_elo-a_elo)/4000),0.3,4.5)
    a_lam=clamp((a_atk/100)*(1-h_def/200)*2.8*im[min(a_inj,3)]*wm*(1-(h_elo-a_elo)/4000),0.3,4.5)
    hw=draws=aw=0; score_counts={}; th=ta=0
    for _ in range(min(n,50000)):
        hg=_poisson(h_lam); ag=_poisson(a_lam); th+=hg; ta+=ag
        if hg>ag: hw+=1
        elif ag>hg: aw+=1
        else: draws+=1
        key=f"{hg}-{ag}"; score_counts[key]=score_counts.get(key,0)+1
    likely=max(score_counts,key=score_counts.get) if score_counts else '1-1'
    hp=round(hw/n*1000)/10; dp=round(draws/n*1000)/10; ap=round(aw/n*1000)/10
    hn=home.get('name','Home'); an=away.get('name','Away')
    ai=call_ai(
        'You are a football simulation AI. Return ONLY valid JSON with no extra text.',
        f'{hn} vs {an}: {n} simulations. Home {hp}% Draw {dp}% Away {ap}% Score:{likely}\n'
        f'JSON: {{"insight":"3 sentence match analysis.","key_battle":"Main area deciding the match"}}'
    )
    return {
        'home_win':hp,'draw':dp,'away_win':ap,'likely_score':likely,
        'avg_goals':{'home':round(th/n,2),'away':round(ta/n,2)},
        'simulations':n,'ai':ai,
        'top_scores':sorted(score_counts.items(),key=lambda x:-x[1])[:5],
        'insight':ai.get('insight',f'V1: {n} simulations run. Most likely score: {likely}.') if ai else f'V1 complete. Likely: {likely}'
    }

def natural_language(question):
    """
    Smart AI entry point. Detects intent, searches the web, routes to the right engine.
    Intent routing: match_prediction→engine_a+d, player_comparison→engine_b, simulation→engine_d, general→Claude
    """
    if not question:
        return {'answer':'Please ask a football question.','prediction':'Unknown','confidence':0,'key_factors':[],'intent':'unknown','data_sources':[]}

    intent_info = detect_intent(question)
    intent = intent_info['intent']
    teams = intent_info.get('teams', [])
    players = intent_info.get('players', [])
    data_sources = []

    if intent == 'match_prediction' and len(teams) >= 2:
        home_team, away_team = teams[0], teams[1]
        results = search_web(f"{home_team} vs {away_team} prediction form injuries stats 2024")
        if results: data_sources.append('web_search')
        web_data = extract_match_data(results, home_team, away_team)
        home_web = web_data.get('home', {}); away_web = web_data.get('away', {}); h2h_web = web_data.get('h2h', {})
        engine_input = {
            'home': {'name': home_team, 'goals_scored': home_web.get('goals_scored',1.5),
                     'goals_conceded': home_web.get('goals_conceded',1.1), 'form': 'WDWWD',
                     'win_rate': home_web.get('win_rate',50), 'injuries': home_web.get('injuries',0),
                     'position': home_web.get('position',8)},
            'away': {'name': away_team, 'goals_scored': away_web.get('goals_scored',1.4),
                     'goals_conceded': away_web.get('goals_conceded',1.2), 'form': 'WWDLW',
                     'win_rate': away_web.get('win_rate',47), 'injuries': away_web.get('injuries',0),
                     'position': away_web.get('position',9)},
            'h2h': {'home_wins': h2h_web.get('home_wins',4), 'draws': h2h_web.get('draws',3),
                    'away_wins': h2h_web.get('away_wins',3)},
        }
        try:
            match_result = engine_a(engine_input)
        except Exception as e:
            logger.error(f"Engine A error: {e}"); match_result = None
        h_gs = float(home_web.get('goals_scored',1.5)); h_gc = float(home_web.get('goals_conceded',1.1))
        a_gs = float(away_web.get('goals_scored',1.4)); a_gc = float(away_web.get('goals_conceded',1.2))
        sim_input = {
            'home': {'name': home_team, 'attack': clamp(int(h_gs/3.0*100),40,95), 'defence': clamp(int((1-h_gc/3.0)*100),40,95), 'elo': 1050, 'injuries': home_web.get('injuries',0)},
            'away': {'name': away_team, 'attack': clamp(int(a_gs/3.0*100),40,95), 'defence': clamp(int((1-a_gc/3.0)*100),40,95), 'elo': 1020, 'injuries': away_web.get('injuries',0)},
            'simulations': 10000, 'competition': 'league', 'weather': 'normal',
        }
        try:
            sim_result = engine_d(sim_input)
        except Exception as e:
            logger.error(f"Engine D error: {e}"); sim_result = None
        if not match_result:
            return {'answer': f'Unable to generate prediction for {home_team} vs {away_team}.', 'prediction':'Unknown','confidence':0,'key_factors':[],'intent':intent,'data_sources':data_sources}
        ai_answer = call_ai(
            'You are MatchOracle AI. Give expert football predictions. Return ONLY valid JSON.',
            f'User asked: "{question}"\nMatch: {home_team} vs {away_team}\n'
            f'Engine A: Home {match_result["home_win"]}% Draw {match_result["draw"]}% Away {match_result["away_win"]}%\n'
            f'Predicted score: {match_result.get("predicted_score","1-1")}\n'
            f'Simulation most likely: {sim_result["likely_score"] if sim_result else "N/A"}\n'
            f'Return JSON: {{"answer":"3-4 sentence analysis","prediction":"{match_result["verdict"]}","confidence":{match_result["confidence"]},"key_factors":["f1","f2","f3"]}}',
            max_tokens=600,
        )
        verdict = match_result['verdict']
        return {
            **(ai_answer or {}),
            'answer': (ai_answer or {}).get('answer', f"{verdict} predicted to win ({match_result['home_win']}% home / {match_result['draw']}% draw / {match_result['away_win']}% away). Score: {match_result.get('predicted_score','1-1')}."),
            'prediction': (ai_answer or {}).get('prediction', verdict),
            'confidence': match_result['confidence'],
            'key_factors': (ai_answer or {}).get('key_factors', []),
            'intent': intent, 'home_team': home_team, 'away_team': away_team,
            'home_win': match_result['home_win'], 'draw': match_result['draw'], 'away_win': match_result['away_win'],
            'predicted_score': match_result.get('predicted_score','1-1'),
            'likely_score': sim_result['likely_score'] if sim_result else 'N/A',
            'match_prediction': match_result, 'simulation': sim_result, 'data_sources': data_sources,
        }

    if intent == 'player_comparison' and players:
        ratings = []
        for player in players:
            results = search_web(f"{player} football stats goals assists 2024 season")
            if results: data_sources.append('web_search')
            pdata = extract_player_data(results, player)
            try:
                rating = engine_b(pdata); ratings.append({'player': player, 'result': rating})
            except Exception as e:
                logger.error(f"Engine B error for {player}: {e}")
        if ratings:
            comparison_text = '\n'.join(f"{r['player']}: rating={r['result']['rating']}/100 tier={r['result']['tier']}" for r in ratings)
            ai_answer = call_ai('You are MatchOracle AI. Compare football players. Return ONLY valid JSON.',
                f'User asked: "{question}"\nEngine B ratings:\n{comparison_text}\n'
                f'Return JSON: {{"answer":"3-4 sentence comparison","prediction":"better player","confidence":75,"key_factors":["f1","f2","f3"]}}', max_tokens=600)
            best = max(ratings, key=lambda x: x['result']['rating'])
            return {**(ai_answer or {}), 'answer': (ai_answer or {}).get('answer', f"Engine B: {comparison_text}"),
                    'prediction': (ai_answer or {}).get('prediction', best['player']),
                    'confidence': (ai_answer or {}).get('confidence', 70),
                    'key_factors': (ai_answer or {}).get('key_factors', []),
                    'intent': intent, 'player_ratings': ratings, 'data_sources': data_sources}

    if intent == 'simulation' and len(teams) >= 2:
        home_team, away_team = teams[0], teams[1]
        results = search_web(f"{home_team} vs {away_team} stats 2024")
        if results: data_sources.append('web_search')
        web_data = extract_match_data(results, home_team, away_team)
        home_web = web_data.get('home', {}); away_web = web_data.get('away', {})
        h_gs = float(home_web.get('goals_scored',1.5)); h_gc = float(home_web.get('goals_conceded',1.1))
        a_gs = float(away_web.get('goals_scored',1.4)); a_gc = float(away_web.get('goals_conceded',1.2))
        sim_input = {
            'home': {'name': home_team, 'attack': clamp(int(h_gs/3.0*100),40,95), 'defence': clamp(int((1-h_gc/3.0)*100),40,95), 'elo': 1050, 'injuries': home_web.get('injuries',0)},
            'away': {'name': away_team, 'attack': clamp(int(a_gs/3.0*100),40,95), 'defence': clamp(int((1-a_gc/3.0)*100),40,95), 'elo': 1020, 'injuries': away_web.get('injuries',0)},
            'simulations': 10000, 'competition': 'league', 'weather': 'normal',
        }
        try:
            sim_result = engine_d(sim_input)
        except Exception as e:
            logger.error(f"Engine D error: {e}"); sim_result = None
        if sim_result:
            ai_answer = call_ai('You are MatchOracle AI. Explain simulation results. Return ONLY valid JSON.',
                f'User asked: "{question}"\nSimulation ({sim_result["simulations"]} runs): Home {sim_result["home_win"]}% Draw {sim_result["draw"]}% Away {sim_result["away_win"]}%\nMost likely: {sim_result["likely_score"]}\n'
                f'Return JSON: {{"answer":"3-4 sentence analysis","prediction":"most likely outcome","confidence":75,"key_factors":["f1","f2","f3"]}}', max_tokens=500)
            return {**(ai_answer or {}), 'answer': (ai_answer or {}).get('answer', f"Simulation complete. Most likely: {sim_result['likely_score']}. Home {sim_result['home_win']}% Draw {sim_result['draw']}% Away {sim_result['away_win']}%."),
                    'prediction': (ai_answer or {}).get('prediction', sim_result['likely_score']),
                    'confidence': (ai_answer or {}).get('confidence', 70),
                    'key_factors': (ai_answer or {}).get('key_factors', []),
                    'intent': intent, 'simulation': sim_result, 'data_sources': data_sources}

    ai = call_ai('You are MatchOracle AI, a football expert. Return ONLY valid JSON.',
        f'Football question: "{question}"\nReturn: {{"answer":"3-4 sentence expert answer","prediction":"your verdict","confidence":70,"key_factors":["f1","f2","f3"]}}',
        max_tokens=500)
    result = ai or {'answer':'AI unavailable. Use Engine A for match predictions.','prediction':'Unknown','confidence':0,'key_factors':[]}
    result['intent'] = intent; result['data_sources'] = data_sources
    return result
