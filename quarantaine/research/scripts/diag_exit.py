#!/usr/bin/env python3
"""Diagnostic sortie : le run se fait-il en pré-marché puis fade à l'open ?
Compare MFE (plus haut après entrée, en PM) vs prix à l'open, + test TP fixes."""
import csv, json, os, sys
from datetime import datetime
from zoneinfo import ZoneInfo
sys.path.insert(0, '/home/martin/dev/stock-journal-long')
from bot.indicators import vwap

ET = ZoneInfo('America/New_York')
CACHE = '/home/martin/dev/stock-journal-long/research/bars_cache'
STOP = 0.05; MIN_PM_VOL = 150_000; VWAP_TOL = 0.003; MIN_ABOVE = 3

def load(tk, d):
    cf = os.path.join(CACHE, f"{tk}_{d}.json")
    if not os.path.exists(cf): return []
    return [{'t': datetime.fromisoformat(b['t']), 'o':b['o'],'h':b['h'],'l':b['l'],'c':b['c'],'v':b['v']}
            for b in json.load(open(cf))]

def find_entry(bars):
    pm = [b for b in bars if (b['t'].hour,b['t'].minute)<(9,30)]
    rth = [b for b in bars if (b['t'].hour,b['t'].minute)>=(9,30)]
    if len(pm)<MIN_ABOVE+2 or not rth: return None
    for i in range(MIN_ABOVE,len(pm)):
        seg=pm[:i+1]; vw=vwap(seg); last=seg[-1]
        if sum(b['v'] for b in seg)<MIN_PM_VOL: continue
        above=all(seg[j]['c']>vwap(seg[:j+1])[-1] for j in range(i-MIN_ABOVE,i))
        if above and last['l']<=vw[-1]*(1+VWAP_TOL) and last['c']>=last['o'] and last['c']>vw[-1]:
            return last['c'],i,pm,rth
    return None

rows=list(csv.DictReader(open('/home/martin/dev/stock-journal-long/data/long-checklist.csv')))
mfes=[]; opens=[]
# TP fixes à tester (sortie pendant le PM si atteint, sinon à l'open), stop -5%
TPS=[0.05,0.10,0.15,0.20]; tp_res={t:[] for t in TPS}
for row in rows:
    bars=load(row['Ticker'].strip(),row['Date'].strip())
    if not bars: continue
    e=find_entry(bars)
    if not e: continue
    entry,idx,pm,rth=e
    after=pm[idx+1:]
    mfe=(max((b['h'] for b in after),default=entry)-entry)/entry*100
    op=(rth[0]['o']-entry)/entry*100
    mfes.append(mfe); opens.append(op)
    for tp in TPS:
        stop=entry*(1-STOP); tgt=entry*(1+tp); res=None
        for b in after:
            if b['l']<=stop: res=-STOP*100; break
            if b['h']>=tgt: res=tp*100; break
        if res is None: res=op
        tp_res[tp].append(res)

n=len(mfes)
print(f"Entrées: {n}\n")
print(f"MFE moyen (plus haut en PM après entrée) : {sum(mfes)/n:+.2f}%")
print(f"Sortie open 9:30 moyenne                 : {sum(opens)/n:+.2f}%")
print(f"-> le run EXISTE en PM mais s'évapore à l'open" if sum(mfes)/n>2 and sum(opens)/n<sum(mfes)/n/2 else "")
print(f"\nSi on prend un TP fixe PENDANT le pré-marché (stop -5%) :")
print(f"{'TP':>5} {'WIN%':>6} {'P&L moy':>9} {'TOTAL':>9}")
print("-"*40)
for tp in TPS:
    r=tp_res[tp]; wins=sum(1 for p in r if p>0)
    print(f"+{tp*100:>3.0f}% {100*wins//len(r):>5}% {sum(r)/len(r):>+8.2f}% {sum(r):>+8.1f}%")
