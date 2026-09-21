#!/usr/bin/env python3
"""Filtre de volume SUR LA BOUGIE D'ENTRÉE. Entrée repli VWAP + volume, stop -5%, trailing 5%."""
import csv, json, os, sys
from datetime import datetime
from zoneinfo import ZoneInfo
sys.path.insert(0, '/home/martin/dev/stock-journal-long')
from bot.indicators import vwap

ET = ZoneInfo('America/New_York')
CACHE = '/home/martin/dev/stock-journal-long/research/bars_cache'
STOP = 0.05; TRAIL = 0.05; MIN_PM_VOL = 150_000; VWAP_TOL = 0.003; MIN_ABOVE = 3

def load(tk, d):
    cf = os.path.join(CACHE, f"{tk}_{d}.json")
    if not os.path.exists(cf): return []
    return [{'t': datetime.fromisoformat(b['t']),'o':b['o'],'h':b['h'],'l':b['l'],'c':b['c'],'v':b['v']}
            for b in json.load(open(cf))]

def find_entry(bars, min_bar_vol=0, rel_surge=0):
    pm=[b for b in bars if (b['t'].hour,b['t'].minute)<(9,30)]
    rth=[b for b in bars if (b['t'].hour,b['t'].minute)>=(9,30)]
    if len(pm)<MIN_ABOVE+2 or not rth: return None
    for i in range(MIN_ABOVE,len(pm)):
        seg=pm[:i+1]; vw=vwap(seg); last=seg[-1]
        if sum(b['v'] for b in seg)<MIN_PM_VOL: continue
        # --- filtre volume sur la bougie d'entrée ---
        if last['v'] < min_bar_vol: continue
        if rel_surge:
            prev5=[b['v'] for b in pm[max(0,i-5):i]]
            avg5=sum(prev5)/len(prev5) if prev5 else 0
            if avg5 and last['v'] < rel_surge*avg5: continue
        above=all(seg[j]['c']>vwap(seg[:j+1])[-1] for j in range(i-MIN_ABOVE,i))
        if above and last['l']<=vw[-1]*(1+VWAP_TOL) and last['c']>=last['o'] and last['c']>vw[-1]:
            return last['c'],i,pm,rth
    return None

def run_trail(entry, idx, pm, rth):
    peak=entry; hard=entry*(1-STOP)
    for b in pm[idx+1:]:
        eff=max(hard, peak*(1-TRAIL))
        if b['l']<=eff: return (eff-entry)/entry*100
        peak=max(peak, b['h'])
    return (rth[0]['o']-entry)/entry*100

rows=list(csv.DictReader(open('/home/martin/dev/stock-journal-long/data/long-checklist.csv')))
allbars=[(r['Ticker'].strip(), load(r['Ticker'].strip(), r['Date'].strip())) for r in rows]
allbars=[(tk,b) for tk,b in allbars if b]

def evaluate(label, **kw):
    r=[]
    for tk,bars in allbars:
        e=find_entry(bars, **kw)
        if e: r.append(run_trail(*e))
    if not r:
        print(f"{label:28} 0 trade"); return
    wins=sum(1 for p in r if p>0)
    print(f"{label:28} {len(r):>4} tr  {100*wins//len(r):>3}%  moy {sum(r)/len(r):>+6.2f}%  tot {sum(r):>+7.1f}%")

print(f"{'FILTRE BOUGIE ENTRÉE':28} {'N':>4}      {'WIN':>4}  {'P&L moy':>9}  {'CUMULÉ':>8}")
print("-"*72)
evaluate("aucun (base)")
for v in (5_000, 10_000, 20_000, 50_000):
    evaluate(f"vol bougie >= {v//1000}k", min_bar_vol=v)
evaluate("surge >= 3x moy(5 bougies)", rel_surge=3)
evaluate("vol>=10k ET surge>=3x", min_bar_vol=10_000, rel_surge=3)
