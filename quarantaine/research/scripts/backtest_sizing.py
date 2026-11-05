#!/usr/bin/env python3
"""Sizing base sur le risque : P&L en % du COMPTE (compose), par-dessus la strat actuelle (7 filtres)."""
import csv, json, os, sys, math
from datetime import datetime
from zoneinfo import ZoneInfo
sys.path.insert(0, '/home/martin/dev/stock-journal-long')
from bot.indicators import vwap
from bot import strategy as S

ET = ZoneInfo('America/New_York')
CACHE = '/home/martin/dev/stock-journal-long/research/bars_cache'
STOP = S.STOP_PCT

def load(tk,d):
    cf=os.path.join(CACHE,f"{tk}_{d}.json")
    if not os.path.exists(cf): return []
    return [{'t':datetime.fromisoformat(b['t']),'o':b['o'],'h':b['h'],'l':b['l'],'c':b['c'],'v':b['v']}
            for b in json.load(open(cf))]

def bands(bars,k):
    out=[];cv=cpv=cpv2=0.0
    for b in bars:
        tp=(b['h']+b['l']+b['c'])/3;cv+=b['v'];cpv+=tp*b['v'];cpv2+=tp*tp*b['v']
        if cv<=0: out.append(b['c']);continue
        vw=cpv/cv;sd=math.sqrt(max(0.0,cpv2/cv-vw*vw));out.append(vw+k*sd)
    return out

def trade_for(bars):
    """1er setup valide (strategie complete) -> retourne le price_pnl% via sortie bande."""
    pm=[b for b in bars if (b['t'].hour,b['t'].minute)<(9,30)]
    rth=[b for b in bars if (b['t'].hour,b['t'].minute)>=(9,30)]
    if len(pm)<S.MIN_ABOVE+2 or not rth: return None
    for i in range(S.MIN_ABOVE+2, len(pm)+1):
        sig=S.check_entry(pm[:i])
        if not sig: continue
        entry=sig['entry']; idx=i-1; stop=entry*(1-STOP); bd=bands(pm,S.BAND_K)
        for j in range(idx+1,len(pm)):
            b=pm[j]
            if b['l']<=stop: return -STOP*100
            if b['h']>=bd[j]: return (bd[j]-entry)/entry*100
        return (rth[0]['o']-entry)/entry*100
    return None

# --- trades en ordre chronologique ---
rows=list(csv.DictReader(open('/home/martin/dev/stock-journal-long/data/long-checklist.csv')))
trades=[]
for r in rows:
    bars=load(r['Ticker'].strip(), r['Date'].strip())
    if not bars: continue
    p=trade_for(bars)
    if p is not None: trades.append((r['Date'].strip(), r['Ticker'].strip(), p))
trades.sort(key=lambda x:x[0])
print(f"{len(trades)} trades (strat 7 filtres), du {trades[0][0]} au {trades[-1][0]}\n")

def simulate(risk, maxpos, start=10000.0):
    acct=start; peak=start; maxdd=0.0; wins=0
    for _,_,pricepct in trades:
        pos = min(acct*risk/STOP, acct*maxpos)       # sizing risque, plafonne par position max
        pnl = pos*(pricepct/100.0)
        acct += pnl
        if pnl>0: wins+=1
        peak=max(peak,acct); maxdd=max(maxdd,(peak-acct)/peak)
    ret=(acct/start-1)*100
    return acct, ret, maxdd*100, wins

print(f"{'RISQUE/trade':12} {'MAX POS':8} {'compte final':>13} {'RENDEMENT':>10} {'MAX DD':>8}")
print("-"*60)
for risk,maxpos,label in [(0.01,1.0,'1% (sans cap)'),(0.02,1.0,'2% (sans cap)'),
                          (0.01,0.20,'1% cap 20%'),(0.02,0.20,'2% cap 20%'),
                          (0.02,0.10,'2% cap 10%'),(0.005,1.0,'0.5% (sans cap)')]:
    acct,ret,dd,wins=simulate(risk,maxpos)
    print(f"{label:12} {maxpos*100:>6.0f}% {acct:>12,.0f}$ {ret:>+9.0f}% {dd:>7.1f}%")
print("\n(compte départ 10 000$ - le RENDEMENT% est le même quel que soit le départ)")
print(f"Rappel: stop fixe {STOP*100:.0f}% -> risquer R% = position de R/{STOP*100:.0f}0 x compte")
