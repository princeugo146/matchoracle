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
    if not question:
        return {'answer':'Please type a question.','prediction':'Unknown','confidence':0,'key_factors':[]}
    ai=call_ai(
        'You are a football expert AI. Return ONLY valid JSON with no extra text.',
        f'Football question: "{question}"\n'
        f'JSON: {{"answer":"3-4 sentence answer.","prediction":"Home Win","confidence":75,"key_factors":["Factor 1","Factor 2","Factor 3"]}}',
        max_tokens=500
    )
    return ai or {'answer':'AI unavailable. Use Engine A for match predictions.','prediction':'Unknown','confidence':0,'key_factors':[]}
