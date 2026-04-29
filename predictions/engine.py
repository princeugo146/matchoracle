"""
MatchOracle V1 Football Intelligence Engine
4 Engines: Prediction | Player Rating | Team Ranking | Simulation
"""
import math
import random
import json
import requests
from django.conf import settings


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def parse_form(form_str):
    if not form_str:
        return 0.5
    results = [c for c in form_str.upper() if c in 'WDL']
    if not results:
        return 0.5
    weights = [1, 0.9, 0.8, 0.7, 0.6]
    total, wtotal = 0, 0
    scores = {'W': 1, 'D': 0.5, 'L': 0}
    for i, r in enumerate(results[:5]):
        w = weights[i]
        total += scores[r] * w
        wtotal += w
    return total / wtotal if wtotal else 0.5


def call_ai(system_prompt, user_prompt):
    api_key = settings.MATCHORACLE.get('ANTHROPIC_API_KEY', '')
    if not api_key:
        return None
    try:
        resp = requests.post(
            'https://api.anthropic.com/v1/messages',
            headers={'Content-Type': 'application/json', 'x-api-key': api_key, 'anthropic-version': '2023-06-01'},
            json={'model': 'claude-sonnet-4-20250514', 'max_tokens': 800,
                  'system': system_prompt, 'messages': [{'role': 'user', 'content': user_prompt}]},
            timeout=15
        )
        if resp.status_code == 200:
            data = resp.json()
            text = ''.join(b.get('text','') for b in data.get('content',[]))
            return json.loads(text.replace('```json','').replace('```','').strip())
    except Exception:
        pass
    return None


# ── ENGINE A: MATCH PREDICTION ──
def engine_a_predict(data):
    home = data.get('home', {})
    away = data.get('away', {})
    h2h  = data.get('h2h', {})

    hgs  = float(home.get('goals_scored', 1.5))
    hgc  = float(home.get('goals_conceded', 1.0))
    ags  = float(away.get('goals_scored', 1.5))
    agc  = float(away.get('goals_conceded', 1.0))
    hform = parse_form(home.get('form', ''))
    aform = parse_form(away.get('form', ''))
    hwr  = float(home.get('win_rate', 50)) / 100
    awr  = float(away.get('win_rate', 45)) / 100
    hinj = int(home.get('injuries', 0))
    ainj = int(away.get('injuries', 0))
    hpos = int(home.get('position', 10))
    apos = int(away.get('position', 10))
    h2hh = int(h2h.get('home_wins', 4))
    h2hd = int(h2h.get('draws', 3))
    h2ha = int(h2h.get('away_wins', 3))

    inj_pen = 0.12
    h_inj = hinj * inj_pen
    a_inj = ainj * inj_pen

    h_att = (hgs / max(agc, 0.5)) * 0.22
    a_att = (ags / max(hgc, 0.5)) * 0.22
    h_form_s = hform * 0.28
    a_form_s = aform * 0.28
    h_wr_s = hwr * 0.15
    a_wr_s = awr * 0.15
    h_pos_s = ((20 - hpos) / 19) * 0.1
    a_pos_s = ((20 - apos) / 19) * 0.1
    h2h_tot = h2hh + h2hd + h2ha or 10
    h_h2h = (h2hh / h2h_tot) * 0.18
    a_h2h = (h2ha / h2h_tot) * 0.18

    h_score = clamp((h_att + h_form_s + h_wr_s + h_pos_s + h_h2h) * 1.15 - h_inj, 0.1, 2.0)
    a_score = clamp((a_att + a_form_s + a_wr_s + a_pos_s + a_h2h) - a_inj, 0.1, 2.0)

    total = h_score + a_score
    draw_base = 0.22 + 0.08 * (1 - abs(h_score - a_score) / total)
    v1_home = h_score / (total + draw_base * total)
    v1_draw = draw_base
    v1_away = a_score / (total + draw_base * total)
    s = v1_home + v1_draw + v1_away
    v1_home /= s; v1_draw /= s; v1_away /= s

    ai_prompt = f"""Football match prediction:
Home: {home.get('name','Home')} | Form: {hform:.0%} | Goals: {hgs}/{hgc} | Injuries: {hinj} | Pos: {hpos}
Away: {away.get('name','Away')} | Form: {aform:.0%} | Goals: {ags}/{agc} | Injuries: {ainj} | Pos: {apos}
H2H: Home {h2hh}W/{h2hd}D/{h2ha}W Away
V1: Home {v1_home:.1%} Draw {v1_draw:.1%} Away {v1_away:.1%}
Return JSON: {{"homeWin":0-1,"draw":0-1,"awayWin":0-1,"insight":"2 sentences","key_factor":"string","v1_agreement":"agree|adjust|override"}}"""

    ai = call_ai('Football prediction AI. Return only valid JSON.', ai_prompt)

    if ai and 'homeWin' in ai:
        fh = v1_home * 0.6 + ai['homeWin'] * 0.4
        fd = v1_draw  * 0.6 + ai['draw']    * 0.4
        fa = v1_away  * 0.6 + ai['awayWin'] * 0.4
    else:
        fh, fd, fa = v1_home, v1_draw, v1_away

    s2 = fh + fd + fa
    fh = round(fh/s2*1000)/10
    fd = round(fd/s2*1000)/10
    fa = round(fa/s2*1000)/10
    confidence = int(clamp(40 + (max(fh,fd,fa) - 33) * 1.8, 40, 95))

    return {
        'home_win': fh, 'draw': fd, 'away_win': fa,
        'confidence': confidence,
        'v1': {'home': round(v1_home*1000)/10, 'draw': round(v1_draw*1000)/10, 'away': round(v1_away*1000)/10},
        'ai': ai,
        'verdict': home.get('name','Home') if fh > fa and fh > fd else (away.get('name','Away') if fa > fh and fa > fd else 'Draw'),
    }


# ── ENGINE B: PLAYER RATING ──
def engine_b_rate(data):
    pos = data.get('position', 'ST')
    goals = float(data.get('goals', 0))
    assists = float(data.get('assists', 0))
    games = max(float(data.get('games', 1)), 1)
    pass_acc = float(data.get('pass_accuracy', 75))
    shots_ot = float(data.get('shots_on_target', 50))
    dribbles = float(data.get('dribble_success', 50))
    tackles  = float(data.get('tackle_success', 50))
    aerials  = float(data.get('aerial_duels', 50))
    distance = float(data.get('distance_covered', 10))
    yellows  = float(data.get('yellow_cards', 0))
    injury   = data.get('injury_status', 'fit')

    pos_weights = {
        'GK':  {'pass':0.15,'tackle':0.35,'aerial':0.25,'dist':0.1,'goals':0.0,'assist':0.0,'shot':0.05,'drib':0.1},
        'CB':  {'pass':0.15,'tackle':0.3,'aerial':0.3,'dist':0.1,'goals':0.02,'assist':0.02,'shot':0.01,'drib':0.1},
        'CM':  {'pass':0.25,'tackle':0.2,'aerial':0.15,'dist':0.1,'goals':0.07,'assist':0.1,'shot':0.05,'drib':0.08},
        'CAM': {'pass':0.2,'tackle':0.1,'aerial':0.1,'dist':0.1,'goals':0.1,'assist':0.2,'shot':0.1,'drib':0.1},
        'ST':  {'pass':0.1,'tackle':0.05,'aerial':0.15,'dist':0.1,'goals':0.3,'assist':0.1,'shot':0.15,'drib':0.05},
    }
    pw = pos_weights.get(pos, pos_weights['CM'])

    gpg = goals / games
    apg = assists / games
    scores = {
        'pass': clamp(pass_acc, 0, 100),
        'tackle': clamp(tackles, 0, 100),
        'aerial': clamp(aerials, 0, 100),
        'dist': clamp((distance / 13) * 100, 0, 100),
        'goals': clamp((gpg / 0.7) * 100, 0, 100),
        'assist': clamp((apg / 0.4) * 100, 0, 100),
        'shot': clamp(shots_ot, 0, 100),
        'drib': clamp(dribbles, 0, 100),
    }

    rating = sum(scores[k] * pw.get(k, 0) for k in scores)
    inj_mult = {'fit': 1.0, 'doubt': 0.93, 'minor': 0.84, 'major': 0.7}
    rating *= inj_mult.get(injury, 1.0)
    rating = clamp(rating - (yellows / games) * 2, 0, 99)

    ai_prompt = f"""Player: {data.get('name','?')}, Pos: {pos}, Goals: {goals}, Assists: {assists}, Games: {games}
Pass: {pass_acc}%, SOT: {shots_ot}%, V1 Rating: {rating:.1f}, Injury: {injury}
Return JSON: {{"adjusted_rating":0-99,"tier":"World Class|Elite|Quality|Average|Below Average","insight":"2 sentences","strengths":["s1","s2"],"weakness":"string"}}"""

    ai = call_ai('Football player rating AI. Return only valid JSON.', ai_prompt)

    final = int(rating * 0.55 + ai['adjusted_rating'] * 0.45) if ai and 'adjusted_rating' in ai else int(rating)
    tier = ai.get('tier') if ai else ('World Class' if final>=88 else 'Elite' if final>=80 else 'Quality' if final>=70 else 'Average' if final>=60 else 'Below Average')

    return {'rating': final, 'v1_rating': round(rating, 1), 'tier': tier,
            'scores': {k: round(v,1) for k,v in scores.items()}, 'ai': ai}


# ── ENGINE C: ELO RANKING ──
def compute_elo(wins, draws, losses, goals_for, goals_against, opp_strength, base_elo=1000):
    games = wins + draws + losses or 1
    win_rate = wins / games
    gd_per_game = (goals_for - goals_against) / games
    pts_per_game = (wins * 3 + draws) / games
    power_elo = base_elo + (win_rate * 400) + (gd_per_game * 20) + (opp_strength * 30) + (pts_per_game * 50)
    return int(power_elo)


# ── ENGINE D: MONTE CARLO SIMULATION ──
def poisson(lam):
    L = math.exp(-lam)
    k, p = 0, 1.0
    while True:
        k += 1
        p *= random.random()
        if p <= L:
            return k - 1


def engine_d_simulate(data):
    home = data.get('home', {})
    away = data.get('away', {})
    n_sims = int(data.get('simulations', 10000))
    weather = data.get('weather', 'normal')
    competition = data.get('competition', 'league')

    h_atk = float(home.get('attack', 75))
    h_def = float(home.get('defence', 70))
    h_elo = float(home.get('elo', 1000))
    h_inj = int(home.get('injuries', 0))
    a_atk = float(away.get('attack', 75))
    a_def = float(away.get('defence', 70))
    a_elo = float(away.get('elo', 1000))
    a_inj = int(away.get('injuries', 0))

    weather_mod = {'normal': 1.0, 'rain': 0.9, 'wind': 0.85, 'heat': 0.88}.get(weather, 1.0)
    home_adv    = {'league': 1.12, 'cup': 1.1, 'champions': 1.08, 'friendly': 1.05}.get(competition, 1.1)
    inj_mod     = [1.0, 0.91, 0.83, 0.74]

    h_lam = clamp((h_atk/100) * (1 - a_def/200) * 2.8 * home_adv * inj_mod[min(h_inj,3)] * weather_mod * (1 + (h_elo - a_elo)/4000), 0.3, 4.5)
    a_lam = clamp((a_atk/100) * (1 - h_def/200) * 2.8 * inj_mod[min(a_inj,3)] * weather_mod * (1 - (h_elo - a_elo)/4000), 0.3, 4.5)

    h_wins = draws = a_wins = 0
    score_counts = {}
    total_h = total_a = 0

    for _ in range(min(n_sims, 100000)):
        hg = poisson(h_lam)
        ag = poisson(a_lam)
        total_h += hg; total_a += ag
        if hg > ag: h_wins += 1
        elif ag > hg: a_wins += 1
        else: draws += 1
        key = f"{hg}-{ag}"
        score_counts[key] = score_counts.get(key, 0) + 1

    likely_score = max(score_counts, key=score_counts.get) if score_counts else '1-1'
    h_pct = round(h_wins / n_sims * 1000) / 10
    d_pct = round(draws  / n_sims * 1000) / 10
    a_pct = round(a_wins / n_sims * 1000) / 10

    ai_prompt = f"""{home.get('name','Home')} vs {away.get('name','Away')}, {n_sims} simulations.
Result: Home {h_pct}% | Draw {d_pct}% | Away {a_pct}% | Likely score: {likely_score}
Return JSON: {{"insight":"3 sentences","key_battle":"string","risk_factor":"string"}}"""

    ai = call_ai('Football simulation AI. Return only valid JSON.', ai_prompt)

    return {
        'home_win': h_pct, 'draw': d_pct, 'away_win': a_pct,
        'likely_score': likely_score,
        'avg_goals': {'home': round(total_h/n_sims,2), 'away': round(total_a/n_sims,2)},
        'home_lambda': round(h_lam, 3), 'away_lambda': round(a_lam, 3),
        'simulations': n_sims, 'ai': ai,
        'top_scores': sorted(score_counts.items(), key=lambda x: -x[1])[:5],
    }
