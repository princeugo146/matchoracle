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
            # Extract result blocks with a lightweight regex (no BeautifulSoup dep)
            # DuckDuckGo HTML wraps each result in <div class="result__body">
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
    """
    Parse search result snippets for team form, injuries, and basic stats.
    Returns a dict suitable for merging into engine_a / engine_d input data.
    """
    text = _combine_text(search_results)
    data = {
        'home': {'name': home_team},
        'away': {'name': away_team},
        'h2h': {},
        'data_source': 'web_search',
        'raw_snippets': [r.get('snippet', '') for r in search_results[:3]],
    }

    # Form strings – look for patterns like "WWDLW" or "W W D L W"
    form_pat = re.compile(r'\b([wdlWDL][\s\-]?){3,6}\b')
    forms = form_pat.findall(text)
    # Injury counts
    inj_pat = re.compile(r'(\d+)\s+(?:player[s]?\s+)?(?:injur|doubt|miss)')
    injuries = inj_pat.findall(text)

    # Goals per game patterns like "1.8 goals per game" or "scoring 2.1"
    gpg_pat = re.compile(r'(\d+\.?\d*)\s+goals?\s+(?:per|a)\s+game')
    gpg = gpg_pat.findall(text)

    # League position patterns like "3rd in the table" or "position 5"
    pos_pat = re.compile(r'(?:position|placed?|sit[st]?|rank[s]?)\s+(?:at\s+)?(\d+)')
    positions = pos_pat.findall(text)

    # Win rate / win percentage
    wr_pat = re.compile(r'(\d+)%?\s+win\s+(?:rate|percentage)')
    win_rates = wr_pat.findall(text)

    # H2H patterns like "Arsenal won 5 of the last 10"
    h2h_pat = re.compile(
        r'(?:won|win)\s+(\d+)\s+(?:of\s+(?:the\s+)?last\s+(\d+)|times?)'
    )
    h2h_matches = h2h_pat.findall(text)

    # Assign extracted values (first match → home, second → away where applicable)
    if len(gpg) >= 1:
        data['home']['goals_scored'] = float(gpg[0])
    if len(gpg) >= 2:
        data['away']['goals_scored'] = float(gpg[1])
    if len(positions) >= 1:
        data['home']['position'] = int(positions[0])
    if len(positions) >= 2:
        data['away']['position'] = int(positions[1])
    if len(win_rates) >= 1:
        data['home']['win_rate'] = int(win_rates[0])
    if len(win_rates) >= 2:
        data['away']['win_rate'] = int(win_rates[1])
    if injuries:
        data['home']['injuries'] = int(injuries[0])
    if len(injuries) >= 2:
        data['away']['injuries'] = int(injuries[1])
    if h2h_matches:
        wins, total = h2h_matches[0]
        data['h2h']['home_wins'] = int(wins)
        if total:
            rest = int(total) - int(wins)
            data['h2h']['draws'] = rest // 2
            data['h2h']['away_wins'] = rest - rest // 2

    return data


def extract_player_data(search_results, player_name):
    """
    Parse search result snippets for player stats.
    Returns a dict suitable for engine_b input.
    """
    text = _combine_text(search_results)
    data = {
        'name': player_name,
        'data_source': 'web_search',
        'raw_snippets': [r.get('snippet', '') for r in search_results[:3]],
    }

    # Goals this season
    goals_pat = re.compile(r'(\d+)\s+goals?\s+(?:this\s+season|in\s+\d+\s+games?|scored)')
    goals = goals_pat.findall(text)
    if goals:
        data['goals'] = int(goals[0])

    # Assists
    ast_pat = re.compile(r'(\d+)\s+assists?')
    assists = ast_pat.findall(text)
    if assists:
        data['assists'] = int(assists[0])

    # Games / appearances
    apps_pat = re.compile(r'(\d+)\s+(?:appearances?|games?|matches?)')
    apps = apps_pat.findall(text)
    if apps:
        data['games'] = int(apps[0])

    # Position detection
    pos_keywords = {
        'goalkeeper': 'GK', 'keeper': 'GK',
        'centre-back': 'CB', 'center-back': 'CB', 'defender': 'CB',
        'midfielder': 'CM', 'central mid': 'CM',
        'attacking mid': 'CAM', 'number 10': 'CAM',
        'striker': 'ST', 'forward': 'ST', 'centre-forward': 'ST',
        'winger': 'CAM',
    }
    for kw, pos in pos_keywords.items():
        if kw in text:
            data['position'] = pos
            break

    # Pass accuracy
    pass_pat = re.compile(r'(\d+)%?\s+pass(?:ing)?\s+accuracy')
    pass_acc = pass_pat.findall(text)
    if pass_acc:
        data['pass_accuracy'] = float(pass_acc[0])

    # Injury status
    if any(w in text for w in ['injured', 'out for', 'ruled out', 'sidelined']):
        data['injury_status'] = 'major'
    elif any(w in text for w in ['doubt', 'fitness concern', 'minor knock']):
        data['injury_status'] = 'doubt'
    else:
        data['injury_status'] = 'fit'

    return data


def extract_upcoming_matches(search_results, team_name):
    """
    Parse search results for the team's next fixture.
    Returns {'home_team': ..., 'away_team': ..., 'date': ..., 'competition': ...}
    or None if nothing found.
    """
    text = _combine_text(search_results)
    team_lower = team_name.lower()

    # Look for "X vs Y" or "X v Y" patterns
    vs_pat = re.compile(
        r'([a-z\s]{3,25})\s+(?:vs?\.?|versus)\s+([a-z\s]{3,25})'
    )
    matches = vs_pat.findall(text)
    for home, away in matches:
        home = home.strip(); away = away.strip()
        if team_lower in home or team_lower in away:
            return {
                'home_team': home.title(),
                'away_team': away.title(),
                'competition': 'league',
            }

    # Date patterns like "next match on 15 January"
    date_pat = re.compile(
        r'next\s+(?:match|game|fixture)\s+(?:on\s+)?(\d{1,2}\s+\w+|\w+\s+\d{1,2})'
    )
    dates = date_pat.findall(text)
    if dates:
        return {'team': team_name, 'date': dates[0], 'competition': 'league'}

    return None


# ─── Intent Detection ─────────────────────────────────────────────────────────

def detect_intent(question):
    """
    Classify the user's question into one of four intents:
      'match_prediction' – asking who will win a match
      'player_comparison' – asking about one or two players
      'simulation'        – asking to simulate a match
      'general'           – general football question

    Returns a dict: {intent, teams, players, confidence}
    """
    q = question.lower()

    # Simulation keywords
    sim_keywords = ['simulat', 'run a sim', 'monte carlo', 'simulate']
    if any(k in q for k in sim_keywords):
        teams = _extract_team_names(q)
        return {'intent': 'simulation', 'teams': teams, 'players': [], 'confidence': 90}

    # Player comparison keywords
    player_keywords = ['messi', 'ronaldo', 'haaland', 'mbappe', 'salah', 'kane',
                       'better player', 'best player', 'compare', 'who is better',
                       'who is best', 'goat', 'rating', 'stats']
    if any(k in q for k in player_keywords):
        players = _extract_player_names(q)
        return {'intent': 'player_comparison', 'teams': [], 'players': players, 'confidence': 85}

    # Match prediction keywords
    match_keywords = ['win', 'beat', 'vs', 'versus', 'v ', 'match', 'game',
                      'predict', 'who will', 'score', 'result', 'fixture']
    if any(k in q for k in match_keywords):
        teams = _extract_team_names(q)
        if teams:
            return {'intent': 'match_prediction', 'teams': teams, 'players': [], 'confidence': 85}

    # Default: general
    return {'intent': 'general', 'teams': [], 'players': [], 'confidence': 60}


def _extract_team_names(text):
    """
    Heuristic extraction of team names from a question string.
    Returns a list of up to two team name strings.
    """
    # Common "X vs Y" pattern
    vs_pat = re.compile(
        r'([A-Za-z\s]{3,25}?)\s+(?:vs?\.?|versus|v\s)\s*([A-Za-z\s]{3,25})',
        re.IGNORECASE
    )
    m = vs_pat.search(text)
    if m:
        return [m.group(1).strip().title(), m.group(2).strip().title()]

    # Known club names as fallback
    known_clubs = [
        'Arsenal', 'Chelsea', 'Liverpool', 'Manchester City', 'Manchester United',
        'Tottenham', 'Newcastle', 'Aston Villa', 'West Ham', 'Brighton',
        'Real Madrid', 'Barcelona', 'Atletico Madrid', 'Bayern Munich', 'Dortmund',
        'PSG', 'Juventus', 'Inter Milan', 'AC Milan', 'Napoli',
        'Ajax', 'Porto', 'Benfica', 'Celtic', 'Rangers',
    ]
    found = [c for c in known_clubs if c.lower() in text.lower()]
    return found[:2]


def _extract_player_names(text):
    """
    Heuristic extraction of player names from a question string.
    Returns a list of up to two player name strings.
    """
    known_players = [
        'Messi', 'Ronaldo', 'Haaland', 'Mbappe', 'Salah', 'Kane',
        'Neymar', 'De Bruyne', 'Bellingham', 'Vinicius', 'Lewandowski',
        'Benzema', 'Modric', 'Kroos', 'Pedri', 'Gavi', 'Saka',
        'Rashford', 'Fernandes', 'Son', 'Firmino', 'Suarez',
    ]
    found = [p for p in known_players if p.lower() in text.lower()]
    return found[:2]

def get_confidence_badge(confidence_pct):
    """
    Convert a raw confidence percentage into a tiered badge dict.
    Returns: {badge_type, label, color, emoji, message}
    Falls back gracefully on any error.
    """
    try:
        pct = int(confidence_pct)
        if pct >= 80:
            return {
                'badge_type': 'high',
                'label': 'High Confidence',
                'color': '#10b981',
                'emoji': '🟢',
                'message': 'Our engines strongly agree',
            }
        elif pct >= 60:
            return {
                'badge_type': 'watch',
                'label': 'Watch List',
                'color': '#fb923c',
                'emoji': '🟡',
                'message': 'Monitor team news before committing',
            }
        else:
            return {
                'badge_type': 'risk',
                'label': 'Risk Alert',
                'color': '#ef4444',
                'emoji': '🔴',
                'message': 'Proceed with caution',
            }
    except Exception:
        return {
            'badge_type': 'watch',
            'label': 'Watch List',
            'color': '#fb923c',
            'emoji': '🟡',
            'message': 'Monitor team news before committing',
        }


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

def call_ai(system, user_msg, max_tokens=700):
    key = settings.MATCHORACLE.get('ANTHROPIC_API_KEY','')
    if not key: return None
    try:
        resp = requests.post(
            'https://api.anthropic.com/v1/messages',
            headers={'Content-Type':'application/json','x-api-key':key,'anthropic-version':'2023-06-01'},
            json={'model':'claude-3-5-sonnet-20241022','max_tokens':max_tokens,'system':system,
                  'messages':[{'role':'user','content':user_msg}]},
            timeout=18
        )
        if resp.status_code == 200:
            text = ''.join(b.get('text','') for b in resp.json().get('content',[]))
            return json.loads(text.replace('```json','').replace('```','').strip())
        else:
            logger.error(f"Anthropic {resp.status_code}")
    except Exception as e:
        logger.error(f"AI error: {e}")
    return None

# TACTICAL STYLE ENGINE
TACTICAL_STYLES = {
    'high_press':      {'attack_boost':0.12,'defense_boost':0.08,'goal_mod':1.15},
    'counter_attack':  {'attack_boost':0.06,'defense_boost':0.14,'goal_mod':0.90},
    'possession':      {'attack_boost':0.08,'defense_boost':0.10,'goal_mod':0.95},
    'defensive_block': {'attack_boost':-0.05,'defense_boost':0.20,'goal_mod':0.75},
    'wing_play':       {'attack_boost':0.10,'defense_boost':0.05,'goal_mod':1.10},
    'long_ball':       {'attack_boost':0.04,'defense_boost':0.04,'goal_mod':1.05},
    'balanced':        {'attack_boost':0.0,'defense_boost':0.0,'goal_mod':1.00},
}

TACTICAL_MATCHUPS = {
    ('high_press','possession'):1.18,
    ('high_press','long_ball'):1.12,
    ('counter_attack','possession'):1.15,
    ('counter_attack','high_press'):1.10,
    ('possession','defensive_block'):0.88,
    ('possession','long_ball'):1.12,
    ('defensive_block','counter_attack'):1.10,
    ('wing_play','defensive_block'):1.08,
    ('wing_play','high_press'):0.92,
}

def get_tactical_multiplier(h_style, a_style):
    return TACTICAL_MATCHUPS.get((h_style,a_style),1.0), TACTICAL_MATCHUPS.get((a_style,h_style),1.0)

MATCH_IMPORTANCE = {
    'friendly':0.60,'qualifier':0.80,'group':0.90,'league':0.88,
    'knockout':1.10,'semifinal':1.18,'final':1.25,'worldcup':1.20,'champions':1.15,
}

def get_pressure_modifier(match_type, tour_exp, knockout_mentality):
    importance = MATCH_IMPORTANCE.get(match_type, 0.88)
    exp = tour_exp/10.0; ment = knockout_mentality/10.0
    if importance >= 1.10:
        mod = 1.0 + (exp*0.12) + (ment*0.08) - (1-exp)*0.05
    else:
        mod = 1.0 + (exp*0.04)
    return clamp(mod, 0.80, 1.20)

def compute_chemistry(coach_years, xi_consistency, key_partnerships):
    return 1.0 + (clamp(coach_years/5.0,0,1)*0.35 + (xi_consistency/100.0)*0.40 + (key_partnerships/10.0)*0.25)*0.10

def predict_correct_score(h_lam, a_lam, top_n=6):
    scores = {}
    for hg in range(8):
        for ag in range(8):
            p = (math.exp(-h_lam)*h_lam**hg/math.factorial(hg)) * (math.exp(-a_lam)*a_lam**ag/math.factorial(ag))
            scores[f"{hg}-{ag}"] = round(p*100, 2)
    return sorted(scores.items(), key=lambda x:-x[1])[:top_n]

def simulate_penalty_shootout(hn, an, h_comp, a_comp, h_gk, a_gk, h_conv, a_conv, sims=10000):
    hw = 0
    for _ in range(sims):
        hs=as_=0
        for _ in range(5):
            if random.random() > a_gk/100*(1-h_comp/200) and random.random() < h_conv/100: hs+=1
            if random.random() > h_gk/100*(1-a_comp/200) and random.random() < a_conv/100: as_+=1
        if hs==as_:
            for _ in range(5):
                hk = random.random()<(h_conv/100*(1-a_gk/200))
                ak = random.random()<(a_conv/100*(1-h_gk/200))
                if hk and not ak: hs+=1; break
                elif ak and not hk: as_+=1; break
        if hs>as_: hw+=1
    hp=round(hw/sims*100,1)
    return {'home_win_pct':hp,'away_win_pct':round(100-hp,1),'home_name':hn,'away_name':an}

def engine_a(data):
    home=data.get('home',{}); away=data.get('away',{}); h2h=data.get('h2h',{})
    match_ctx=data.get('match_context',{})
    hgs=float(home.get('goals_scored',1.5)); hgc=float(home.get('goals_conceded',1.0))
    ags=float(away.get('goals_scored',1.5)); agc=float(away.get('goals_conceded',1.0))
    hform=parse_form(home.get('form','')); aform=parse_form(away.get('form',''))
    hwr=float(home.get('win_rate',50))/100; awr=float(away.get('win_rate',45))/100
    hinj=int(home.get('injuries',0)); ainj=int(away.get('injuries',0))
    hpos=int(home.get('position',10)); apos=int(away.get('position',10))
    h2hh=int(h2h.get('home_wins',4)); h2hd=int(h2h.get('draws',3)); h2ha=int(h2h.get('away_wins',3))
    h2h_tot=h2hh+h2hd+h2ha or 10
    hn=home.get('name','Home'); an=away.get('name','Away')
    h_style=home.get('tactical_style','balanced'); a_style=away.get('tactical_style','balanced')
    h_tac=TACTICAL_STYLES.get(h_style,TACTICAL_STYLES['balanced'])
    a_tac=TACTICAL_STYLES.get(a_style,TACTICAL_STYLES['balanced'])
    h_tac_vs_a,a_tac_vs_h=get_tactical_multiplier(h_style,a_style)
    match_type=match_ctx.get('match_type','league')
    h_pressure=get_pressure_modifier(match_type,float(home.get('tournament_experience',5)),float(home.get('knockout_mentality',5)))
    a_pressure=get_pressure_modifier(match_type,float(away.get('tournament_experience',5)),float(away.get('knockout_mentality',5)))
    h_chem=compute_chemistry(float(home.get('coach_years',2)),float(home.get('xi_consistency',70)),float(home.get('key_partnerships',5)))
    a_chem=compute_chemistry(float(away.get('coach_years',2)),float(away.get('xi_consistency',70)),float(away.get('key_partnerships',5)))
    importance=MATCH_IMPORTANCE.get(match_type,0.88)
    h_base=((hgs/max(agc,0.5))*0.20+hform*0.24+hwr*0.14+((20-hpos)/19)*0.10+(h2hh/h2h_tot)*0.16+h_tac['attack_boost']*0.10+h_tac['defense_boost']*0.06)
    a_base=((ags/max(hgc,0.5))*0.20+aform*0.24+awr*0.14+((20-apos)/19)*0.10+(h2ha/h2h_tot)*0.16+a_tac['attack_boost']*0.10+a_tac['defense_boost']*0.06)
    h_score=clamp((h_base*1.12-hinj*0.10)*h_tac_vs_a*h_pressure*h_chem*importance,0.1,2.5)
    a_score=clamp((a_base-ainj*0.10)*a_tac_vs_h*a_pressure*a_chem*importance,0.1,2.5)
    total=h_score+a_score
    draw_base=0.22+0.06*(1-abs(h_score-a_score)/total)
    v1h=h_score/(total+draw_base*total); v1d=draw_base; v1a=a_score/(total+draw_base*total)
    s=v1h+v1d+v1a; v1h/=s; v1d/=s; v1a/=s
    # CORRECT SCORE via Poisson
    h_xg=clamp(hgs*(agc/(agc+hgs+0.1))*h_tac['goal_mod']*h_pressure*(1-ainj*0.05)*importance*2.2,0.5,4.5)
    a_xg=clamp(ags*(hgc/(hgc+ags+0.1))*a_tac['goal_mod']*a_pressure*(1-hinj*0.05)*importance*1.8,0.3,4.0)
    top_scores=predict_correct_score(h_xg,a_xg)
    predicted_score=top_scores[0][0] if top_scores else '1-1'
    ai=call_ai(
        'You are a football prediction AI. Return ONLY valid JSON.',
        f"Match:{hn}({h_style}) vs {an}({a_style}) Type:{match_type}\n"
        f"Home:form={hform:.0%} goals={hgs}/{hgc} inj={hinj} pos={hpos} pressure={h_pressure:.2f} chem={h_chem:.2f}\n"
        f"Away:form={aform:.0%} goals={ags}/{agc} inj={ainj} pos={apos} pressure={a_pressure:.2f} chem={a_chem:.2f}\n"
        f"H2H:{h2hh}W {h2hd}D {h2ha}A Tactical:{h_style} vs {a_style}\n"
        f"V1:Home={v1h:.1%} Draw={v1d:.1%} Away={v1a:.1%} xG:{hn}={h_xg:.2f} {an}={a_xg:.2f}\n"
        f"Top Poisson scores:{top_scores[:3]}\n"
        f'Return JSON:{{"homeWin":0.50,"draw":0.25,"awayWin":0.25,"insight":"2 sentence tactical analysis","predicted_score":"{predicted_score}","tactical_note":"tactical insight"}}'
    )
    if ai and 'homeWin' in ai:
        fh=v1h*0.55+float(ai['homeWin'])*0.45
        fd=v1d*0.55+float(ai['draw'])*0.45
        fa=v1a*0.55+float(ai['awayWin'])*0.45
        ai_score=ai.get('predicted_score','')
        if ai_score and '-' in ai_score and ai_score!='1-1': predicted_score=ai_score
    else:
        fh,fd,fa=v1h,v1d,v1a
    s2=fh+fd+fa
    fh=round(fh/s2*1000)/10; fd=round(fd/s2*1000)/10; fa=round(fa/s2*1000)/10
    confidence=int(clamp(40+(max(fh,fd,fa)-33)*1.8,40,95))
    verdict=hn if fh>fa and fh>fd else (an if fa>fh and fa>fd else 'Draw')
    return {
        'home_win':fh,'draw':fd,'away_win':fa,'confidence':confidence,'verdict':verdict,
        'confidence_badge':get_confidence_badge(confidence),
        'predicted_score':predicted_score,
        'top_scores':[{'score':s,'prob':round(p,1)} for s,p in top_scores],
        'expected_goals':{'home':round(h_xg,2),'away':round(a_xg,2)},
        'tactical':{'home_style':h_style,'away_style':a_style,'matchup':round(h_tac_vs_a,2),'note':ai.get('tactical_note',f'{h_style} vs {a_style}') if ai else ''},
        'pressure':{'home':round(h_pressure,2),'away':round(a_pressure,2),'match_type':match_type},
        'chemistry':{'home':round(h_chem,2),'away':round(a_chem,2)},
        'v1':{'home':round(v1h*100,1),'draw':round(v1d*100,1),'away':round(v1a*100,1)},
        'ai':ai,'insight':ai.get('insight',f'V1+Tactical: {verdict} predicted.') if ai else f'V1: {verdict}',
    }

def engine_b(data):
    pos=data.get('position','ST'); goals=float(data.get('goals',0))
    assists=float(data.get('assists',0)); games=max(float(data.get('games',1)),1)
    pass_acc=float(data.get('pass_accuracy',75)); shots_ot=float(data.get('shots_on_target',50))
    dribbles=float(data.get('dribble_success',50)); tackles=float(data.get('tackle_success',50))
    aerials=float(data.get('aerial_duels',50)); distance=float(data.get('distance_covered',10))
    yellows=float(data.get('yellow_cards',0)); injury=data.get('injury_status','fit')
    name=data.get('name','Player')
    pw={'GK':{'pass':0.15,'tackle':0.35,'aerial':0.25,'dist':0.10,'goals':0.00,'assist':0.00,'shot':0.05,'drib':0.10},
        'CB':{'pass':0.15,'tackle':0.30,'aerial':0.30,'dist':0.10,'goals':0.02,'assist':0.02,'shot':0.01,'drib':0.10},
        'CM':{'pass':0.25,'tackle':0.20,'aerial':0.15,'dist':0.10,'goals':0.07,'assist':0.10,'shot':0.05,'drib':0.08},
        'CAM':{'pass':0.20,'tackle':0.10,'aerial':0.10,'dist':0.10,'goals':0.10,'assist':0.20,'shot':0.10,'drib':0.10},
        'ST':{'pass':0.10,'tackle':0.05,'aerial':0.15,'dist':0.10,'goals':0.30,'assist':0.10,'shot':0.15,'drib':0.05},
    }.get(pos,{'pass':0.20,'tackle':0.15,'aerial':0.15,'dist':0.10,'goals':0.12,'assist':0.12,'shot':0.08,'drib':0.08})
    scores={'pass':clamp(pass_acc,0,100),'tackle':clamp(tackles,0,100),'aerial':clamp(aerials,0,100),
            'dist':clamp((distance/13)*100,0,100),'goals':clamp((goals/games/0.7)*100,0,100),
            'assist':clamp((assists/games/0.4)*100,0,100),'shot':clamp(shots_ot,0,100),'drib':clamp(dribbles,0,100)}
    rating=sum(scores[k]*pw.get(k,0) for k in scores)
    rating*={'fit':1.0,'doubt':0.93,'minor':0.84,'major':0.70}.get(injury,1.0)
    rating=clamp(rating-(yellows/games)*2,0,99)
    ai=call_ai('You are a football player rating AI. Return ONLY valid JSON.',
        f'Player:{name} Pos:{pos} Goals:{goals} Assists:{assists} Games:{games} Pass:{pass_acc}% V1:{rating:.1f} Injury:{injury}\n'
        f'Return:{{"adjusted_rating":80,"tier":"Elite","insight":"2 sentence analysis."}}')
    final=int(rating*0.55+float(ai['adjusted_rating'])*0.45) if ai and 'adjusted_rating' in ai else int(rating)
    tier=ai.get('tier') if ai else ('World Class' if final>=88 else 'Elite' if final>=80 else 'Quality' if final>=70 else 'Average' if final>=60 else 'Below Average')
    return {'rating':final,'v1_rating':round(rating,1),'tier':tier,'scores':{k:round(v,1) for k,v in scores.items()},'ai':ai,
            'insight':ai.get('insight',f'{name} rated {final}/100. {tier}.') if ai else f'V1: {name} {final}/100'}

def compute_elo(wins,draws,losses,gf,ga,opp,base=1000):
    games=wins+draws+losses or 1
    return int(base+(wins/games)*400+((gf-ga)/games)*20+opp*30+((wins*3+draws)/games)*50)

def _poisson(lam):
    L=math.exp(-lam); k,p=0,1.0
    while True:
        k+=1; p*=random.random()
        if p<=L: return k-1

def engine_d(data):
    home=data.get('home',{}); away=data.get('away',{})
    n=int(data.get('simulations',10000)); weather=data.get('weather','normal'); comp=data.get('competition','league')
    match_type=data.get('match_type','league')
    h_atk=float(home.get('attack',75)); h_def=float(home.get('defence',70))
    h_elo=float(home.get('elo',1000)); h_inj=int(home.get('injuries',0))
    a_atk=float(away.get('attack',75)); a_def=float(away.get('defence',70))
    a_elo=float(away.get('elo',1000)); a_inj=int(away.get('injuries',0))
    h_style=home.get('tactical_style','balanced'); a_style=away.get('tactical_style','balanced')
    h_tac=TACTICAL_STYLES.get(h_style,TACTICAL_STYLES['balanced'])
    a_tac=TACTICAL_STYLES.get(a_style,TACTICAL_STYLES['balanced'])
    h_tac_vs_a,a_tac_vs_h=get_tactical_multiplier(h_style,a_style)
    h_pressure=get_pressure_modifier(match_type,float(home.get('tournament_experience',5)),float(home.get('knockout_mentality',5)))
    a_pressure=get_pressure_modifier(match_type,float(away.get('tournament_experience',5)),float(away.get('knockout_mentality',5)))
    importance=MATCH_IMPORTANCE.get(match_type,0.88)
    wm={'normal':1.0,'rain':0.90,'wind':0.85,'heat':0.88}.get(weather,1.0)
    ha={'league':1.12,'champions':1.08,'cup':1.10,'friendly':1.05,'worldcup':1.06,'knockout':1.08,'final':1.05}.get(comp,1.10)
    im=[1.0,0.91,0.83,0.74]
    h_lam=clamp((h_atk/100)*(1-a_def/200)*2.8*ha*im[min(h_inj,3)]*wm*(1+(h_elo-a_elo)/4000)*h_tac['goal_mod']*h_tac_vs_a*h_pressure*importance,0.3,4.5)
    a_lam=clamp((a_atk/100)*(1-h_def/200)*2.8*im[min(a_inj,3)]*wm*(1-(h_elo-a_elo)/4000)*a_tac['goal_mod']*a_tac_vs_h*a_pressure*importance,0.3,4.5)
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
    ai=call_ai('You are a football simulation AI. Return ONLY valid JSON.',
        f'{hn}({h_style}) vs {an}({a_style}) - {match_type}\n{n} sims:Home{hp}% Draw{dp}% Away{ap}% Score:{likely}\n'
        f'Return:{{"insight":"3 sentence analysis","key_battle":"main area","tactical_edge":"team name"}}')
    return {'home_win':hp,'draw':dp,'away_win':ap,'likely_score':likely,
            'avg_goals':{'home':round(th/n,2),'away':round(ta/n,2)},'simulations':n,'ai':ai,
            'tactical':{'home_style':h_style,'away_style':a_style},
            'top_scores':sorted(score_counts.items(),key=lambda x:-x[1])[:6],
            'insight':ai.get('insight',f'V1:{n} sims. Likely:{likely}.') if ai else f'V1 complete. Likely:{likely}'}

def natural_language(question):
    """
    Smart AI entry point.  Detects intent, searches the web for real data,
    tries Sportmonks if available, then routes to the appropriate engine.

    Intent routing:
      match_prediction  → engine_a  (+ engine_d simulation)
      player_comparison → engine_b  (one rating per player)
      simulation        → engine_d
      general           → Claude AI only
    """
    if not question:
        return {
            'answer': 'Please ask a football question.',
            'prediction': 'Unknown',
            'confidence': 0,
            'key_factors': [],
            'intent': 'unknown',
            'data_sources': [],
        }

    # ── 1. Detect intent ────────────────────────────────────────────────────
    intent_info = detect_intent(question)
    intent = intent_info['intent']
    teams = intent_info.get('teams', [])
    players = intent_info.get('players', [])
    data_sources = []

    # ── 2. Match prediction ─────────────────────────────────────────────────
    if intent == 'match_prediction' and len(teams) >= 2:
        home_team, away_team = teams[0], teams[1]

        # 2a. Try Sportmonks first
        sportmonks_data = _try_sportmonks_match(home_team, away_team)
        if sportmonks_data:
            data_sources.append('sportmonks')
            engine_input = sportmonks_data
        else:
            # 2b. Fall back to web search
            search_q = f"{home_team} vs {away_team} prediction form injuries stats 2024"
            results = search_web(search_q)
            if results:
                data_sources.append('web_search')
            web_data = extract_match_data(results, home_team, away_team)
            engine_input = _build_match_engine_input(home_team, away_team, web_data)

        # Run Engine A
        try:
            match_result = engine_a(engine_input)
        except Exception as e:
            logger.error(f"Engine A error in natural_language: {e}")
            match_result = None

        # Run Engine D simulation
        sim_input = _build_sim_engine_input(home_team, away_team, engine_input)
        try:
            sim_result = engine_d(sim_input)
        except Exception as e:
            logger.error(f"Engine D error in natural_language: {e}")
            sim_result = None

        if not match_result:
            return {
                'answer': f'Unable to generate prediction for {home_team} vs {away_team}.',
                'prediction': 'Unknown',
                'confidence': 0,
                'key_factors': [],
                'intent': intent,
                'data_sources': data_sources,
            }

        # Build final AI narrative
        ai_answer = call_ai(
            'You are MatchOracle AI. Give expert football predictions. Return ONLY valid JSON.',
            f'User asked: "{question}"\n'
            f'Match: {home_team} vs {away_team}\n'
            f'Engine A: Home {match_result["home_win"]}% Draw {match_result["draw"]}% Away {match_result["away_win"]}%\n'
            f'Predicted score: {match_result.get("predicted_score","1-1")}\n'
            f'Simulation most likely score: {sim_result["likely_score"] if sim_result else "N/A"}\n'
            f'Confidence: {match_result["confidence"]}%\n'
            f'Data sources: {", ".join(data_sources) or "defaults"}\n'
            f'Return JSON: {{"answer":"3-4 sentence expert analysis with percentages",'
            f'"prediction":"{match_result["verdict"]}",'
            f'"confidence":{match_result["confidence"]},'
            f'"key_factors":["factor1","factor2","factor3"],'
            f'"betting_insight":"one sentence"}}',
            max_tokens=600,
        )

        if ai_answer:
            return {
                **ai_answer,
                'intent': intent,
                'home_team': home_team,
                'away_team': away_team,
                'home_win': match_result['home_win'],
                'draw': match_result['draw'],
                'away_win': match_result['away_win'],
                'predicted_score': match_result.get('predicted_score', '1-1'),
                'likely_score': sim_result['likely_score'] if sim_result else 'N/A',
                'match_prediction': match_result,
                'simulation': sim_result,
                'data_sources': data_sources,
            }

        # Fallback without AI narrative
        verdict = match_result['verdict']
        return {
            'answer': (
                f"Based on web data and V1 analysis, {verdict} is predicted to win "
                f"({match_result['home_win']}% home / {match_result['draw']}% draw / "
                f"{match_result['away_win']}% away). "
                f"Predicted score: {match_result.get('predicted_score','1-1')}."
            ),
            'prediction': verdict,
            'confidence': match_result['confidence'],
            'key_factors': [],
            'intent': intent,
            'home_team': home_team,
            'away_team': away_team,
            'home_win': match_result['home_win'],
            'draw': match_result['draw'],
            'away_win': match_result['away_win'],
            'predicted_score': match_result.get('predicted_score', '1-1'),
            'likely_score': sim_result['likely_score'] if sim_result else 'N/A',
            'match_prediction': match_result,
            'simulation': sim_result,
            'data_sources': data_sources,
        }

    # ── 3. Player comparison ────────────────────────────────────────────────
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
                logger.error(f"Engine B error for {player}: {e}")

        if ratings:
            comparison_text = '\n'.join(
                f"{r['player']}: rating={r['result']['rating']}/100 tier={r['result']['tier']}"
                for r in ratings
            )
            ai_answer = call_ai(
                'You are MatchOracle AI. Compare football players. Return ONLY valid JSON.',
                f'User asked: "{question}"\n'
                f'Player ratings from Engine B:\n{comparison_text}\n'
                f'Data sources: {", ".join(data_sources) or "defaults"}\n'
                f'Return JSON: {{"answer":"3-4 sentence comparison",'
                f'"prediction":"Player name who is better",'
                f'"confidence":75,'
                f'"key_factors":["factor1","factor2","factor3"]}}',
                max_tokens=600,
            )
            best = max(ratings, key=lambda x: x['result']['rating'])
            return {
                **(ai_answer or {}),
                'answer': (ai_answer or {}).get('answer',
                    f"Based on Engine B analysis: {comparison_text}"),
                'prediction': (ai_answer or {}).get('prediction', best['player']),
                'confidence': (ai_answer or {}).get('confidence', 70),
                'key_factors': (ai_answer or {}).get('key_factors', []),
                'intent': intent,
                'player_ratings': ratings,
                'data_sources': data_sources,
            }

    # ── 4. Simulation ───────────────────────────────────────────────────────
    if intent == 'simulation':
        if len(teams) >= 2:
            home_team, away_team = teams[0], teams[1]
            search_q = f"{home_team} vs {away_team} stats attack defence 2024"
            results = search_web(search_q)
            if results:
                data_sources.append('web_search')
            web_data = extract_match_data(results, home_team, away_team)
            sim_input = _build_sim_engine_input(home_team, away_team, web_data)
        else:
            home_team = teams[0] if teams else 'Home Team'
            away_team = 'Away Team'
            sim_input = {
                'home': {'name': home_team, 'attack': 75, 'defence': 70, 'elo': 1050, 'injuries': 0},
                'away': {'name': away_team, 'attack': 72, 'defence': 68, 'elo': 1020, 'injuries': 0},
                'simulations': 10000, 'competition': 'league', 'weather': 'normal',
                'match_type': 'league',
            }

        try:
            sim_result = engine_d(sim_input)
        except Exception as e:
            logger.error(f"Engine D error in natural_language simulation: {e}")
            sim_result = None

        if sim_result:
            ai_answer = call_ai(
                'You are MatchOracle AI. Explain simulation results. Return ONLY valid JSON.',
                f'User asked: "{question}"\n'
                f'Simulation ({sim_result["simulations"]} runs): '
                f'Home {sim_result["home_win"]}% Draw {sim_result["draw"]}% Away {sim_result["away_win"]}%\n'
                f'Most likely score: {sim_result["likely_score"]}\n'
                f'Return JSON: {{"answer":"3-4 sentence simulation analysis",'
                f'"prediction":"most likely outcome",'
                f'"confidence":75,'
                f'"key_factors":["f1","f2","f3"]}}',
                max_tokens=500,
            )
            return {
                **(ai_answer or {}),
                'answer': (ai_answer or {}).get('answer',
                    f"Simulation complete. Most likely score: {sim_result['likely_score']}. "
                    f"Home win {sim_result['home_win']}%, Draw {sim_result['draw']}%, "
                    f"Away win {sim_result['away_win']}%."),
                'prediction': (ai_answer or {}).get('prediction', sim_result['likely_score']),
                'confidence': (ai_answer or {}).get('confidence', 70),
                'key_factors': (ai_answer or {}).get('key_factors', []),
                'intent': intent,
                'simulation': sim_result,
                'data_sources': data_sources,
            }

    # ── 5. General football question (Claude only) ──────────────────────────
    ai = call_ai(
        'You are MatchOracle AI, a football expert. Return ONLY valid JSON.',
        f'Football question: "{question}"\n'
        f'Return: {{"answer":"3-4 sentence expert answer","prediction":"your verdict",'
        f'"confidence":70,"key_factors":["f1","f2","f3"]}}',
        max_tokens=500,
    )
    result = ai or {
        'answer': 'AI unavailable. Use Engine A for match predictions.',
        'prediction': 'Unknown',
        'confidence': 0,
        'key_factors': [],
    }
    result['intent'] = intent
    result['data_sources'] = data_sources
    return result


# ─── Engine input builders ────────────────────────────────────────────────────

def _build_match_engine_input(home_team, away_team, web_data):
    """
    Merge web-extracted data with safe defaults to produce a valid engine_a input dict.
    """
    home_web = web_data.get('home', {})
    away_web = web_data.get('away', {})
    h2h_web = web_data.get('h2h', {})
    return {
        'home': {
            'name': home_team,
            'goals_scored': home_web.get('goals_scored', 1.5),
            'goals_conceded': home_web.get('goals_conceded', 1.1),
            'form': home_web.get('form', 'WDWWD'),
            'win_rate': home_web.get('win_rate', 50),
            'injuries': home_web.get('injuries', 0),
            'position': home_web.get('position', 8),
            'tactical_style': 'balanced',
            'tournament_experience': 5,
            'knockout_mentality': 5,
            'coach_years': 2,
            'xi_consistency': 70,
            'key_partnerships': 5,
        },
        'away': {
            'name': away_team,
            'goals_scored': away_web.get('goals_scored', 1.4),
            'goals_conceded': away_web.get('goals_conceded', 1.2),
            'form': away_web.get('form', 'WWDLW'),
            'win_rate': away_web.get('win_rate', 47),
            'injuries': away_web.get('injuries', 0),
            'position': away_web.get('position', 9),
            'tactical_style': 'balanced',
            'tournament_experience': 5,
            'knockout_mentality': 5,
            'coach_years': 2,
            'xi_consistency': 70,
            'key_partnerships': 5,
        },
        'h2h': {
            'home_wins': h2h_web.get('home_wins', 4),
            'draws': h2h_web.get('draws', 3),
            'away_wins': h2h_web.get('away_wins', 3),
        },
        'match_context': {'match_type': 'league'},
    }


def _build_sim_engine_input(home_team, away_team, match_data):
    """
    Build engine_d input from match data (web-extracted or Sportmonks).
    """
    home = match_data.get('home', {})
    away = match_data.get('away', {})
    h_gs = float(home.get('goals_scored', 1.5))
    h_gc = float(home.get('goals_conceded', 1.1))
    a_gs = float(away.get('goals_scored', 1.4))
    a_gc = float(away.get('goals_conceded', 1.2))
    return {
        'home': {
            'name': home_team,
            'attack': clamp(int(h_gs / 3.0 * 100), 40, 95),
            'defence': clamp(int((1 - h_gc / 3.0) * 100), 40, 95),
            'elo': home.get('elo', 1050),
            'injuries': home.get('injuries', 0),
            'tactical_style': 'balanced',
            'tournament_experience': 5,
            'knockout_mentality': 5,
        },
        'away': {
            'name': away_team,
            'attack': clamp(int(a_gs / 3.0 * 100), 40, 95),
            'defence': clamp(int((1 - a_gc / 3.0) * 100), 40, 95),
            'elo': away.get('elo', 1020),
            'injuries': away.get('injuries', 0),
            'tactical_style': 'balanced',
            'tournament_experience': 5,
            'knockout_mentality': 5,
        },
        'simulations': 10000,
        'competition': 'league',
        'weather': 'normal',
        'match_type': 'league',
    }


def _try_sportmonks_match(home_team, away_team):
    """
    Attempt to fetch today's fixture from Sportmonks.
    Returns a valid engine_a input dict on success, or None.
    """
    try:
        api_key = settings.MATCHORACLE.get('FOOTBALL_API_KEY', '')
        if not api_key:
            return None
        from datetime import date
        today = date.today().strftime('%Y-%m-%d')
        resp = requests.get(
            f'https://api.sportmonks.com/v3/football/fixtures/date/{today}',
            headers={'Authorization': api_key},
            params={'include': 'participants;statistics;league', 'per_page': 100},
            timeout=8,
        )
        if resp.status_code != 200:
            return None
        fixtures = resp.json().get('data', [])
        ht_lower = home_team.lower()
        at_lower = away_team.lower()
        for fixture in fixtures:
            parts = fixture.get('participants', [])
            names = [p.get('name', '').lower() for p in parts]
            if (any(ht_lower in n or n in ht_lower for n in names) and
                    any(at_lower in n or n in at_lower for n in names)):
                return _build_match_engine_input(home_team, away_team, {
                    'home': {'name': home_team},
                    'away': {'name': away_team},
                    'h2h': {},
                })
    except Exception as e:
        logger.warning(f"Sportmonks lookup failed: {e}")
    return None


# ─── Final Consensus Prediction ───────────────────────────────────────────────

def consensus_prediction(engine_a_result, engine_d_result, smart_ai_result=None):
    """
    Combine Engine A (40%), Engine D (40%), and Smart AI (20%) into a single
    weighted-average consensus prediction.

    Parameters
    ----------
    engine_a_result  : dict  – output of engine_a()
    engine_d_result  : dict  – output of engine_d()
    smart_ai_result  : dict or None – output of smart_predict() / call_ai()
                       Expected keys: home_win, draw, away_win (as numbers)

    Returns
    -------
    dict with keys:
        home_win, draw, away_win  – weighted-average percentages (float, sum ≈ 100)
        predicted_score           – from Engine D (corrected for draw contradictions)
        confidence                – 'High' | 'Medium' | 'Low'
        confidence_badge          – badge dict (reuses get_confidence_badge logic)
        agreement_status          – human-readable string describing engine agreement
        engines_agreed            – list of engine names that agreed on the winner
        final_verdict             – winner name or 'Draw'
        home_team                 – team name from Engine A result
        away_team                 – team name from Engine A result
    """
    try:
        # ── Extract per-engine probabilities ────────────────────────────────
        a_hw = float(engine_a_result.get('home_win', 33.3))
        a_dr = float(engine_a_result.get('draw', 33.3))
        a_aw = float(engine_a_result.get('away_win', 33.3))

        d_hw = float(engine_d_result.get('home_win', 33.3))
        d_dr = float(engine_d_result.get('draw', 33.3))
        d_aw = float(engine_d_result.get('away_win', 33.3))

        # Smart AI weights – fall back to Engine A values if unavailable
        if smart_ai_result and isinstance(smart_ai_result, dict):
            ai_hw = float(smart_ai_result.get('home_win', a_hw))
            ai_dr = float(smart_ai_result.get('draw', a_dr))
            ai_aw = float(smart_ai_result.get('away_win', a_aw))
            ai_weight = 0.20
        else:
            ai_hw, ai_dr, ai_aw = a_hw, a_dr, a_aw
            ai_weight = 0.0

        # Normalise weights so they always sum to 1.0
        a_weight = 0.40
        d_weight = 0.40
        total_weight = a_weight + d_weight + ai_weight
        a_w = a_weight / total_weight
        d_w = d_weight / total_weight
        ai_w = ai_weight / total_weight

        # ── Weighted averages ────────────────────────────────────────────────
        raw_hw = a_hw * a_w + d_hw * d_w + ai_hw * ai_w
        raw_dr = a_dr * a_w + d_dr * d_w + ai_dr * ai_w
        raw_aw = a_aw * a_w + d_aw * d_w + ai_aw * ai_w

        # Normalise to exactly 100 %
        total = raw_hw + raw_dr + raw_aw or 100.0
        c_hw = round(raw_hw / total * 1000) / 10
        c_dr = round(raw_dr / total * 1000) / 10
        c_aw = round(raw_aw / total * 1000) / 10

        # ── Determine per-engine verdicts ────────────────────────────────────
        home_name = engine_a_result.get('verdict', '')  # may be team name or 'Draw'
        # Recover actual team names from Engine A internals
        # Engine A stores them in 'v1' but not directly – use confidence_badge fallback
        # We'll derive from the result dict keys that smart_predict populates
        hn = engine_a_result.get('home_name', '')
        an = engine_a_result.get('away_name', '')

        def _verdict(hw, dr, aw, hn_fallback='Home', an_fallback='Away'):
            if hw > aw and hw > dr:
                return hn_fallback or 'Home'
            elif aw > hw and aw > dr:
                return an_fallback or 'Away'
            else:
                return 'Draw'

        # Engine A verdict is already computed
        a_verdict = engine_a_result.get('verdict', _verdict(a_hw, a_dr, a_aw))
        # Engine D verdict
        d_verdict = _verdict(d_hw, d_dr, d_aw)
        # Smart AI verdict
        if smart_ai_result and isinstance(smart_ai_result, dict):
            ai_verdict = smart_ai_result.get('verdict', _verdict(ai_hw, ai_dr, ai_aw))
        else:
            ai_verdict = a_verdict

        # ── Consensus verdict ────────────────────────────────────────────────
        final_verdict = _verdict(c_hw, c_dr, c_aw)

        # ── Agreement analysis ───────────────────────────────────────────────
        verdicts = {'Engine A': a_verdict, 'Engine D': d_verdict, 'Smart AI': ai_verdict}
        agreed = [name for name, v in verdicts.items() if v == final_verdict]
        disagreed = [name for name, v in verdicts.items() if v != final_verdict]

        all_agree = len(agreed) == 3
        two_agree = len(agreed) == 2
        none_agree = len(agreed) <= 1

        # ── Confidence level ─────────────────────────────────────────────────
        # High: all three agree, OR draw probability within 5 % of highest win prob
        highest_win = max(c_hw, c_aw)
        draw_near_winner = abs(c_dr - highest_win) <= 5.0

        if all_agree or (two_agree and draw_near_winner):
            confidence_level = 'High'
            confidence_pct = 82
        elif two_agree:
            confidence_level = 'Medium'
            confidence_pct = 65
        else:
            confidence_level = 'Low'
            confidence_pct = 45

        # ── Predicted score (from Engine D, corrected for draw contradictions) ──
        d_score = engine_d_result.get('likely_score', '1-1')

        # If draw probability is within 5 % of the highest win probability,
        # the predicted score must reflect a draw.
        if draw_near_winner and final_verdict == 'Draw':
            # Parse Engine D score and equalise it
            parts = str(d_score).split('-')
            if len(parts) == 2:
                try:
                    hg = int(parts[0])
                    ag = int(parts[1])
                    avg = round((hg + ag) / 2)
                    predicted_score = f"{avg}-{avg}"
                except ValueError:
                    predicted_score = '1-1'
            else:
                predicted_score = '1-1'
        else:
            predicted_score = d_score

        # ── Agreement status string ──────────────────────────────────────────
        if all_agree:
            agreement_status = f"All three engines agree: {final_verdict}"
        elif two_agree:
            agreement_status = f"{' & '.join(agreed)} agree on {final_verdict}; {', '.join(disagreed)} differs"
        else:
            agreement_status = f"Engines disagree — consensus leans {final_verdict}"

        # ── Confidence badge (reuse existing helper) ─────────────────────────
        badge = get_confidence_badge(confidence_pct)
        # Override label/emoji to match the three-tier naming in the spec
        if confidence_level == 'High':
            badge['label'] = 'High Confidence'
            badge['badge_type'] = 'high'
            badge['emoji'] = '🟢'
        elif confidence_level == 'Medium':
            badge['label'] = 'Watch List'
            badge['badge_type'] = 'watch'
            badge['emoji'] = '🟡'
        else:
            badge['label'] = 'Risk Alert'
            badge['badge_type'] = 'risk'
            badge['emoji'] = '🔴'

        return {
            'home_win': c_hw,
            'draw': c_dr,
            'away_win': c_aw,
            'predicted_score': predicted_score,
            'confidence': confidence_level,
            'confidence_pct': confidence_pct,
            'confidence_badge': badge,
            'agreement_status': agreement_status,
            'engines_agreed': agreed,
            'engines_disagreed': disagreed,
            'final_verdict': final_verdict,
            'engine_verdicts': verdicts,
        }

    except Exception as e:
        logger.error(f"consensus_prediction error: {e}", exc_info=True)
        # Safe fallback
        return {
            'home_win': 33.3,
            'draw': 33.3,
            'away_win': 33.3,
            'predicted_score': '1-1',
            'confidence': 'Low',
            'confidence_pct': 45,
            'confidence_badge': get_confidence_badge(45),
            'agreement_status': 'Unable to compute consensus',
            'engines_agreed': [],
            'engines_disagreed': ['Engine A', 'Engine D', 'Smart AI'],
            'final_verdict': 'Draw',
            'engine_verdicts': {},
        }
