#!/usr/bin/env python3
"""Test des sorties trailing vs TP fixe. Entrée repli VWAP, stop -5%, tout en pré-marché."""
import csv, json, os, sys
from datetime import datetime
from zoneinfo import ZoneInfo
sys.path.insert(0, '/home/martin/dev/stock-journal-long')
from bot.indicators import vwap, ema

ET = ZoneInfo('America/New_York')
CACHE = '/home/martin/dev/stock-journal-long/research/bars_cache'
STOP = 0.05; MIN_PM_VOL = 150_000; VWAP_TOL = 0.003; MIN_ABOVE = 3

def load(tk, d):
    cf = os.path.join(CACHE, f"{tk}_{d}.json")
    if not os.path.exists(cf): return []
    return [{'t': datetime.fromisoformat(b['t']),'o':b['o'],'h':b['h'],'l':b['l'],'c':b['c'],'v':b['v']}
            for b in json.load(open(cf))]

def find_entry(bars):
    pm=[b for b in bars if (b['t'].hour,b['t'].minute)<(9,30)]
    rth=[b for b in bars if (b['t'].hour,b['t'].minute)>=(9,30)]
    if len(pm)<MIN_ABOVE+2 or not rth: return None
    for i in range(MIN_ABOVE,len(pm)):
        seg=pm[:i+1]; vw=vwap(seg); last=seg[-1]
        if sum(b['v'] for b in seg)<MIN_PM_VOL: continue
        above=all(seg[j]['c']>vwap(seg[:j+1])[-1] for j in range(i-MIN_ABOVE,i))
        if above and last['l']<=vw[-1]*(1+VWAP_TOL) and last['c']>=last['o'] and last['c']>vw[-1]:
            return last['c'],i,pm,rth
    return None

def exit_fixed_tp(entry, idx, pm, rth, tp):
    stop=entry*(1-STOP); tgt=entry*(1+tp)
    for b in pm[idx+1:]:
        if b['l']<=stop: return -STOP*100
        if b['h']>=tgt: return tp*100
    return (rth[0]['o']-entry)/entry*100

def exit_trail_pct(entry, idx, pm, rth, trail):
    peak=entry; hard=entry*(1-STOP)
    for b in pm[idx+1:]:
        eff=max(hard, peak*(1-trail))
        if b['l']<=eff: return (eff-entry)/entry*100
        peak=max(peak, b['h'])
    return (rth[0]['o']-entry)/entry*100

def exit_trail_ema(entry, idx, pm, rth):
    hard=entry*(1-STOP)
    closes=[b['c'] for b in pm]
    for j in range(idx+1, len(pm)):
        b=pm[j]
        if b['l']<=hard: return -STOP*100
        e9=ema(closes[:j+1],9)[-1]
        if b['c']<e9: return (b['c']-entry)/entry*100   # clôture sous la 9 EMA
    return (rth[0]['o']-entry)/entry*100

rows=list(csv.DictReader(open('/home/martin/dev/stock-journal-long/data/long-checklist.csv')))
entries=[]
for row in rows:
    bars=load(row['Ticker'].strip(),row['Date'].strip())
    if not bars: continue
    e=find_entry(bars)
    if e: entries.append(e)
print(f"Entrées: {len(entries)} | stop initial -{STOP*100:.0f}%\n")

def report(name, fn):
    r=[fn(*e) for e in entries]
    wins=sum(1 for p in r if p>0)
    print(f"{name:22} {100*wins//len(r):>4}%  moy {sum(r)/len(r):>+6.2f}%  total {sum(r):>+7.1f}%")

print(f"{'SORTIE':22} {'WIN':>5}  {'P&L moyen':>10}  {'CUMULÉ':>8}")
print("-"*56)
report("TP fixe +15% (base)", lambda en,i,pm,rth: exit_fixed_tp(en,i,pm,rth,0.15))
for tr in (0.05,0.08,0.10,0.15):
    report(f"Trailing {int(tr*100)}% du sommet", lambda en,i,pm,rth,tr=tr: exit_trail_pct(en,i,pm,rth,tr))
report("Trailing 9 EMA", exit_trail_ema)
