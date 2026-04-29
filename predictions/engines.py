"""
MatchOracle V1 Football Intelligence Engine
4 core engines: Match Prediction, Player Rating, Team Ranking, Match Simulation
"""
import math
import random
from typing import Dict, Any

# ─── SHARED UTILITIES ───────────────────────────────────────────────────────
def clamp(v, lo, hi): return max(lo, min(hi, v))

def parse_form(form_str: str) -> float:
    if not form_str: return 0.5
    results = [c for c in form_str.upper() if c in 'WDL']
    if not results: return 0.5
    weights = [1.0, 0.9, 0.8, 0.7, 0.6]
    pts = {'W': 1.0, 'D': 0.5, 'L': 0.0}
    total = sum(pts[r] * weights[i] for i, r in enumerate(results[:5]))
    w_sum = sum(weights[:len(results[:5])])
    return total / w_sum if w_sum else 0.5

def poisson_random(lam: float) -> int:
    L = math.exp(-lam)
    k, p = 0, 1.0
    while True:
        k += 1
        p *= random.random()
        if p <= L:
            return k - 1

# ─── ENGINE A: MATCH PREDICTION ─────────────────────────────────────────────
def engine_a_predict(data: Dict[str, Any]) -> Dict[str, Any]:
    home = data['home']
    away = data['away']

    home_form   = parse_form(home.get('form', ''))
    away_form   = parse_form(away.get('form', ''))
    home_gs     = float(home.get('goals_scored', 1.5))
    home_gc     = float(home.get('goals_conceded', 1.0))
    away_gs     = float(away.get('goals_scored', 1.5))
    away_gc     = float(away.get('goals_conceded', 1.0))
    home_wr     = float(home.get('win_rate', 50)) / 100
    away_wr     = float(away.get('win_rate', 45)) / 100
    home_inj    = int(home.get('injuries', 0))
    away_inj    = int(away.get('injuries', 0))
    home_pos    = int(home.get('position', 10))
    away_pos    = int(away.get('position', 10))
    h2h_home    = int(data.get('h2h_home', 4))
    h2h_draws   = int(data.get('h2h_draws', 3))
    h2h_away    = int(data.get('h2h_away', 3))

    # Weights
    HOME_ADV    = 1.15
    INJ_PENALTY = 0.12

    # Attack vs defence
    h_att = (home_gs / max(away_gc, 0.4)) * 0.22
    a_att = (away_gs / max(home_gc, 0.4)) * 0.22

    # Form
    h_form_s = home_form * 0.28
    a_form_s = away_form * 0.28

    # Win rate
    h_wr_s = home_wr * 0.15
    a_wr_s = away_wr * 0.15

    # Position
    h_pos_s = ((20 - home_pos) / 19) * 0.10
    a_pos_s = ((20 - away_pos) / 19) * 0.10

    # H2H
    h2h_total = max(h2h_home + h2h_draws + h2h_away, 1)
    h_h2h = (h2h_home / h2h_total) * 0.18
    a_h2h = (h2h_away / h2h_total) * 0.18

    # Injury
    h_inj_pen = home_inj * INJ_PENALTY
    a_inj_pen = away_inj * INJ_PENALTY

    h_score = clamp((h_att + h_form_s + h_wr_s + h_pos_s + h_h2h) * HOME_ADV - h_inj_pen, 0.05, 2.0)
    a_score = clamp((a_att + a_form_s + a_wr_s + a_pos_s + a_h2h) - a_inj_pen, 0.05, 2.0)

    draw_base = 0.22 + 0.08 * (1 - abs(h_score - a_score) / (h_score + a_score))
    total = h_score + a_score + draw_base * (h_score + a_score)
    home_win = h_score / total
    draw     = draw_base * (h_score + a_score) / total
    away_win = a_score / total

    s = home_win + draw + away_win
    home_win /= s; draw /= s; away_win /= s

    confidence = clamp(40 + (max(home_win, draw, away_win) - 0.33) * 150, 40, 95)

    verdict = (home.get('name','Home') if home_win > away_win and home_win > draw
               else away.get('name','Away') if away_win > home_win and away_win > draw
               else 'Draw')

    return {
        'home_win': round(home_win * 100, 1),
        'draw': round(draw * 100, 1),
        'away_win': round(away_win * 100, 1),
        'verdict': verdict,
        'confidence': round(confidence, 1),
        'home_score': round(h_score, 3),
        'away_score': round(a_score, 3),
        'key_factors': {
            'home_form': round(home_form * 100, 1),
            'away_form': round(away_form * 100, 1),
            'home_injury_impact': round(h_inj_pen * 100, 1),
            'away_injury_impact': round(a_inj_pen * 100, 1),
            'home_advantage_boost': round((HOME_ADV - 1) * 100, 1),
        }
    }

# ─── ENGINE B: PLAYER RATING ────────────────────────────────────────────────
POS_WEIGHTS = {
    'GK':  {'pass':0.15,'tackle':0.35,'aerial':0.25,'dist':0.10,'goals':0.00,'assist':0.00,'shot':0.05,'drib':0.10},
    'CB':  {'pass':0.15,'tackle':0.30,'aerial':0.30,'dist':0.10,'goals':0.02,'assist':0.02,'shot':0.01,'drib':0.10},
    'LB':  {'pass':0.20,'tackle':0.20,'aerial':0.15,'dist':0.15,'goals':0.05,'assist':0.10,'shot':0.05,'drib':0.10},
    'RB':  {'pass':0.20,'tackle':0.20,'aerial':0.15,'dist':0.15,'goals':0.05,'assist':0.10,'shot':0.05,'drib':0.10},
    'CDM': {'pass':0.25,'tackle':0.30,'aerial':0.20,'dist':0.10,'goals':0.03,'assist':0.05,'shot':0.02,'drib':0.05},
    'CM':  {'pass':0.25,'tackle':0.20,'aerial':0.15,'dist':0.10,'goals':0.07,'assist':0.10,'shot':0.05,'drib':0.08},
    'CAM': {'pass':0.20,'tackle':0.10,'aerial':0.10,'dist':0.10,'goals':0.10,'assist':0.20,'shot':0.10,'drib':0.10},
    'LW':  {'pass':0.15,'tackle':0.08,'aerial':0.08,'dist':0.12,'goals':0.15,'assist':0.15,'shot':0.15,'drib':0.12},
    'RW':  {'pass':0.15,'tackle':0.08,'aerial':0.08,'dist':0.12,'goals':0.15,'assist':0.15,'shot':0.15,'drib':0.12},
    'ST':  {'pass':0.10,'tackle':0.05,'aerial':0.15,'dist':0.10,'goals':0.30,'assist':0.10,'shot':0.15,'drib':0.05},
}

def engine_b_rate(data: Dict[str, Any]) -> Dict[str, Any]:
    pos    = data.get('position', 'ST')
    goals  = float(data.get('goals', 0))
    assists= float(data.get('assists', 0))
    games  = max(float(data.get('games', 1)), 1)
    pass_a = float(data.get('pass_accuracy', 75))
    shots  = float(data.get('shots_on_target', 50))
    drib   = float(data.get('dribble_success', 50))
    tackle = float(data.get('tackles_won', 50))
    aerial = float(data.get('aerial_duels', 50))
    dist   = float(data.get('distance', 10))
    yellows= float(data.get('yellow_cards', 0))
    injury = data.get('injury_status', 'fit')

    pw = POS_WEIGHTS.get(pos, POS_WEIGHTS['ST'])

    gpg = goals / games
    apg = assists / games

    scores = {
        'pass':   clamp(pass_a, 0, 100),
        'tackle': clamp(tackle, 0, 100),
        'aerial': clamp(aerial, 0, 100),
        'dist':   clamp((dist / 13) * 100, 0, 100),
        'goals':  clamp((gpg / 0.7) * 100, 0, 100),
        'assist': clamp((apg / 0.4) * 100, 0, 100),
        'shot':   clamp(shots, 0, 100),
        'drib':   clamp(drib, 0, 100),
    }

    rating = sum(scores[k] * pw[k] for k in scores)
    inj_mult = {'fit':1.0,'doubt':0.93,'minor':0.84,'major':0.70}
    rating *= inj_mult.get(injury, 1.0)
    rating -= (yellows / games) * 2
    rating = clamp(rating, 0, 99)

    tier = ('World Class' if rating >= 88 else 'Elite' if rating >= 80
            else 'Quality' if rating >= 70 else 'Average' if rating >= 60 else 'Below Average')

    return {
        'rating': round(rating, 1),
        'tier': tier,
        'position': pos,
        'breakdown': {k: round(scores[k], 1) for k in scores},
        'goals_per_game': round(gpg, 2),
        'assists_per_game': round(apg, 2),
        'injury_impact': round((1 - inj_mult.get(injury, 1.0)) * 100, 1),
    }

# ─── ENGINE C: TEAM RANKING (ELO) ───────────────────────────────────────────
def engine_c_elo(data: Dict[str, Any]) -> float:
    base_elo  = float(data.get('elo', 1000))
    wins      = int(data.get('wins', 0))
    draws     = int(data.get('draws', 0))
    losses    = int(data.get('losses', 0))
    gf        = int(data.get('goals_for', 0))
    ga        = int(data.get('goals_against', 0))
    opp_str   = float(data.get('opponent_strength', 5))

    games = max(wins + draws + losses, 1)
    gd = gf - ga
    win_rate = wins / games
    pts_pg = (wins * 3 + draws) / games

    power_elo = (base_elo
                 + win_rate * 400
                 + (gd / games) * 20
                 + opp_str * 30
                 + pts_pg * 50)
    return round(clamp(power_elo, 400, 2500), 1)

# ─── ENGINE D: MATCH SIMULATION (Monte Carlo) ───────────────────────────────
def engine_d_simulate(data: Dict[str, Any], n_sims: int = 10000) -> Dict[str, Any]:
    home = data['home']
    away = data['away']

    h_atk  = float(home.get('attack', 75))
    h_def  = float(home.get('defence', 70))
    h_elo  = float(home.get('elo', 1000))
    h_inj  = int(home.get('injuries', 0))
    a_atk  = float(away.get('attack', 75))
    a_def  = float(away.get('defence', 70))
    a_elo  = float(away.get('elo', 1000))
    a_inj  = int(away.get('injuries', 0))

    weather = data.get('weather', 'normal')
    comp    = data.get('competition', 'league')

    weather_mod = {'normal':1.0,'rain':0.90,'wind':0.85,'heat':0.88}.get(weather, 1.0)
    home_adv    = {'league':1.12,'cup':1.10,'champions':1.08,'friendly':1.05}.get(comp, 1.12)
    inj_mod     = [1.0, 0.91, 0.83, 0.74]

    h_inj_mod = inj_mod[min(h_inj, 3)]
    a_inj_mod = inj_mod[min(a_inj, 3)]
    elo_diff  = (h_elo - a_elo) / 4000

    h_lam = clamp((h_atk/100) * (1 - a_def/200) * 2.8 * home_adv * h_inj_mod * weather_mod * (1 + elo_diff), 0.3, 4.5)
    a_lam = clamp((a_atk/100) * (1 - h_def/200) * 2.8 * a_inj_mod * weather_mod * (1 - elo_diff), 0.3, 4.5)

    h_wins = draws = a_wins = 0
    score_counts = {}
    total_hg = total_ag = 0

    for _ in range(n_sims):
        hg = poisson_random(h_lam)
        ag = poisson_random(a_lam)
        total_hg += hg; total_ag += ag
        if hg > ag:   h_wins += 1
        elif ag > hg: a_wins += 1
        else:         draws  += 1
        key = f"{hg}-{ag}"
        score_counts[key] = score_counts.get(key, 0) + 1

    likely_score = max(score_counts, key=score_counts.get)
    top_scores = sorted(score_counts.items(), key=lambda x: -x[1])[:5]

    return {
        'home_win_pct': round(h_wins / n_sims * 100, 1),
        'draw_pct':     round(draws  / n_sims * 100, 1),
        'away_win_pct': round(a_wins / n_sims * 100, 1),
        'likely_score': likely_score,
        'top_scorelines': [{'score': s, 'pct': round(c/n_sims*100,1)} for s, c in top_scores],
        'avg_home_goals': round(total_hg / n_sims, 2),
        'avg_away_goals': round(total_ag / n_sims, 2),
        'home_lambda': round(h_lam, 3),
        'away_lambda': round(a_lam, 3),
        'simulations_run': n_sims,
    }
