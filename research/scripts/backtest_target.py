#!/usr/bin/env python3
"""Filtre 'reward minimum' : n'entrer que si la bande VWAP+2s (le TP) est a >= X% de l'entree."""
import csv, json, os, sys, math
from datetime import datetime
from zoneinfo import ZoneInfo
sys.path.insert(0, '/home/martin/dev/stock-journal-long')
from bot.indicators import vwap

ET = ZoneInfo('America/New_York')
CACHE = '/home/martin/dev/stock-journal-long/research/bars_cache'
STOP=0.05; BAND_K=2; SURGE=3; MIN_PM_VOL=150_000; VWAP_TOL=0.003; MIN_ABOVE=3
MIN_RANGE=0.01; MIN_BARV=10_000   # filtre tradabilite actuel

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

def find_entry(bars, min_target=0.0):
    pm=[b for b in bars if (b['t'].hour,b['t'].minute)<(9,30)]
    rth=[b for b in bars if (b['t'].hour,b['t'].minute)>=(9,30)]
    if len(pm)<MIN_ABOVE+2 or not rth: return None
    bd=bands(pm,BAND_K)
    for i in range(MIN_ABOVE,len(pm)):
        seg=pm[:i+1];vw=vwap(seg);last=seg[-1]
        if sum(b['v'] for b in seg)<MIN_PM_VOL: continue
        prev5=[b['v'] for b in pm[max(0,i-5):i]];avg5=sum(prev5)/len(prev5) if prev5 else 0
        if avg5 and last['v']<SURGE*avg5: continue
        if last['v']<MIN_BARV: continue
        last5=pm[max(0,i-4):i+1];rng=sum((b['h']-b['l'])/b['c'] for b in last5)/len(last5)
        if rng<MIN_RANGE: continue
        above=all(seg[j]['c']>vwap(seg[:j+1])[-1] for j in range(i-MIN_ABOVE,i))
        if not (above and last['l']<=vw[-1]*(1+VWAP_TOL) and last['c']>=last['o'] and last['c']>vw[-1]):
            continue
        entry=last['c']
        target_pct=(bd[i]-entry)/entry               # <-- la bande AVANT d'entrer
        if target_pct<min_target: continue
        return entry,i,pm,rth,target_pct
    return None

def exit_band(entry,idx,pm,rth):
    stop=entry*(1-STOP);bd=bands(pm,BAND_K)
    for j in range(idx+1,len(pm)):
        b=pm[j]
        if b['l']<=stop: return -STOP*100
        if b['h']>=bd[j]: return (bd[j]-entry)/entry*100
    return (rth[0]['o']-entry)/entry*100

rows=list(csv.DictReader(open('/home/martin/dev/stock-journal-long/data/long-checklist.csv')))
allbars=[(r['Ticker'].strip(),load(r['Ticker'].strip(),r['Date'].strip())) for r in rows]
allbars=[(tk,b) for tk,b in allbars if b]

print(f"{'TP mini (bande)':16} {'N':>4}  {'WIN':>4}  {'P&L moy':>9}  {'CUMULE':>8}  {'gain moy des WIN':>16}")
print("-"*76)
for thr in (0.0,0.02,0.05,0.08,0.10):
    res=[]
    for tk,bars in allbars:
        e=find_entry(bars,min_target=thr)
        if e: res.append(exit_band(e[0],e[1],e[2],e[3]))
    if not res: print(f">= {thr*100:>3.0f}%           0 trade");continue
    wins=[p for p in res if p>0]
    wr=100*len(wins)//len(res)
    wavg=sum(wins)/len(wins) if wins else 0
    print(f">= {thr*100:>3.0f}%          {len(res):>4}  {wr:>3}%  {sum(res)/len(res):>+7.2f}%  {sum(res):>+7.1f}%  {wavg:>+15.2f}%")
