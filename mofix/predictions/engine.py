import math, random, json, requests, logging
from django.conf import settings

logger = logging.getLogger(__name__)

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
            json={'model':'claude-sonnet-4-20250514','max_tokens':max_tokens,'system':system,
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
    if not question:
        return {'answer':'Please ask a question.','prediction':'Unknown','confidence':0,'key_factors':[]}
    ai=call_ai('You are a football expert AI. Return ONLY valid JSON.',
        f'Question:"{question}"\nReturn:{{"answer":"3-4 sentence answer","prediction":"Home Win","confidence":75,"key_factors":["f1","f2","f3"]}}',
        max_tokens=500)
    return ai or {'answer':'AI unavailable. Use Engine A.','prediction':'Unknown','confidence':0,'key_factors':[]}
