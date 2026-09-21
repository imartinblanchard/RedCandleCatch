#!/usr/bin/env python3
"""Filtres de 'tradabilite' : volume absolu / dollar / range mini, par-dessus la strat actuelle."""
import csv, json, os, sys, math
from datetime import datetime
from zoneinfo import ZoneInfo
sys.path.insert(0, '/home/martin/dev/stock-journal-long')
from bot.indicators import vwap

ET = ZoneInfo('America/New_York')
CACHE = '/home/martin/dev/stock-journal-long/research/bars_cache'
STOP = 0.05; BAND_K = 2; SURGE = 3; MIN_PM_VOL = 150_000; VWAP_TOL = 0.003; MIN_ABOVE = 3

def load(tk, d):
    cf = os.path.join(CACHE, f"{tk}_{d}.json")
    if not os.path.exists(cf): return []
    return [{'t': datetime.fromisoformat(b['t']),'o':b['o'],'h':b['h'],'l':b['l'],'c':b['c'],'v':b['v']}
            for b in json.load(open(cf))]

def bands(bars, k):
    out=[]; cv=cpv=cpv2=0.0
    for b in bars:
        tp=(b['h']+b['l']+b['c'])/3; cv+=b['v']; cpv+=tp*b['v']; cpv2+=tp*tp*b['v']
        if cv<=0: out.append(b['c']); continue
        vw=cpv/cv; sd=math.sqrt(max(0.0,cpv2/cv-vw*vw)); out.append(vw+k*sd)
    return out

def find_entry(bars, min_shares=0, min_dollars=0, min_range=0.0):
    pm=[b for b in bars if (b['t'].hour,b['t'].minute)<(9,30)]
    rth=[b for b in bars if (b['t'].hour,b['t'].minute)>=(9,30)]
    if len(pm)<MIN_ABOVE+2 or not rth: return None
    for i in range(MIN_ABOVE,len(pm)):
        seg=pm[:i+1]; vw=vwap(seg); last=seg[-1]
        if sum(b['v'] for b in seg)<MIN_PM_VOL: continue
        prev5=[b['v'] for b in pm[max(0,i-5):i]]; avg5=sum(prev5)/len(prev5) if prev5 else 0
        if avg5 and last['v']<SURGE*avg5: continue
        above=all(seg[j]['c']>vwap(seg[:j+1])[-1] for j in range(i-MIN_ABOVE,i))
        if not (above and last['l']<=vw[-1]*(1+VWAP_TOL) and last['c']>=last['o'] and last['c']>vw[-1]):
            continue
        # --- filtres de tradabilite (sur la bougie/le contexte d'entree) ---
        if min_shares and last['v']<min_shares: continue
        if min_dollars and last['c']*last['v']<min_dollars: continue
        if min_range:
            last5=pm[max(0,i-4):i+1]
            avgr=sum((b['h']-b['l'])/b['c'] for b in last5)/len(last5)
            if avgr<min_range: continue
        return last['c'],i,pm,rth
    return None

def exit_band(entry, idx, pm, rth):
    stop=entry*(1-STOP); band=bands(pm,BAND_K)
    for j in range(idx+1,len(pm)):
        b=pm[j]
        if b['l']<=stop: return -STOP*100
        if b['h']>=band[j]: return (band[j]-entry)/entry*100
    return (rth[0]['o']-entry)/entry*100

rows=list(csv.DictReader(open('/home/martin/dev/stock-journal-long/data/long-checklist.csv')))
allbars=[(r['Ticker'].strip(), load(r['Ticker'].strip(), r['Date'].strip())) for r in rows]
allbars=[(tk,b) for tk,b in allbars if b]

def evaluate(label, **kw):
    r=[]
    for tk,bars in allbars:
        e=find_entry(bars, **kw)
        if e: r.append(exit_band(*e))
    if not r: print(f"{label:32} 0 trade"); return
    wins=sum(1 for p in r if p>0)
    print(f"{label:32} {len(r):>4} tr  {100*wins//len(r):>3}%  moy {sum(r)/len(r):>+6.2f}%  tot {sum(r):>+7.1f}%")

print(f"{'FILTRE TRADABILITE':32} {'N':>4}      {'WIN':>4}  {'P&L moy':>9}  {'CUMULE':>8}")
print("-"*74)
evaluate("aucun (baseline)")
print("-- volume absolu bougie d'entree --")
for v in (10_000, 20_000, 50_000): evaluate(f"vol bougie >= {v//1000}k actions", min_shares=v)
print("-- dollar-volume bougie d'entree --")
for d in (30_000, 50_000, 100_000): evaluate(f"$ bougie >= ${d//1000}k", min_dollars=d)
print("-- range moyen (5 bougies) --")
for rg in (0.005, 0.01, 0.02): evaluate(f"range moy >= {rg*100:.1f}%", min_range=rg)
print("-- combo --")
evaluate("$>=50k ET range>=1%", min_dollars=50_000, min_range=0.01)
