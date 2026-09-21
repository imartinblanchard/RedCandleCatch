#!/usr/bin/env python3
"""Détail complet de quelques trades pour vérification manuelle sur graphique."""
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

def find_entry(bars):
    pm=[b for b in bars if (b['t'].hour,b['t'].minute)<(9,30)]
    rth=[b for b in bars if (b['t'].hour,b['t'].minute)>=(9,30)]
    if len(pm)<MIN_ABOVE+2 or not rth: return None
    for i in range(MIN_ABOVE,len(pm)):
        seg=pm[:i+1]; vw=vwap(seg); last=seg[-1]
        if sum(b['v'] for b in seg)<MIN_PM_VOL: continue
        above=all(seg[j]['c']>vwap(seg[:j+1])[-1] for j in range(i-MIN_ABOVE,i))
        if above and last['l']<=vw[-1]*(1+VWAP_TOL) and last['c']>=last['o'] and last['c']>vw[-1]:
            return i,pm,rth,vw[-1]
    return None

def run_trade(entry_px, idx, pm):
    peak=entry_px; hard=entry_px*(1-STOP)
    for b in pm[idx+1:]:
        eff=max(hard, peak*(1-TRAIL))
        if b['l']<=eff:
            return eff, b['t'], peak
        peak=max(peak, b['h'])
    return None, None, peak

TARGET = sys.argv[1] if len(sys.argv)>1 else None
rows=list(csv.DictReader(open('/home/martin/dev/stock-journal-long/data/long-checklist.csv')))
examples=[]
for row in rows:
    tk,date=row['Ticker'].strip(),row['Date'].strip()
    if TARGET and tk!=TARGET: continue
    bars=load(tk,date)
    if not bars: continue
    e=find_entry(bars)
    if not e: continue
    idx,pm,rth,vw_entry=e
    entry_px=pm[idx]['c']
    exit_px,exit_t,peak=run_trade(entry_px,idx,pm)
    if exit_px is None:
        exit_px=rth[0]['o']; exit_t=rth[0]['t']; reason='OPEN'
    else:
        reason='TRAIL'
    pnl=(exit_px-entry_px)/entry_px*100
    examples.append((pnl,tk,date,idx,pm,rth,vw_entry,entry_px,exit_px,exit_t,peak,reason))

# meilleur trade gagnant "propre" (gain modéré, pas un outlier)
examples.sort(key=lambda x:x[0], reverse=True)
pick = examples[len(examples)//6] if not TARGET and len(examples)>6 else examples[0]
pnl,tk,date,idx,pm,rth,vw_entry,entry_px,exit_px,exit_t,peak,reason=pick

def hh(t): return t.astimezone(ET).strftime('%H:%M')
print(f"╔══════════════════════════════════════════════════════════════╗")
print(f"  TRADE : {tk}  le {date}   (à vérifier sur ton graphique 1-min, heure ET)")
print(f"╚══════════════════════════════════════════════════════════════╝")
print(f"\n  ENTRÉE  {hh(pm[idx]['t'])} ET  @ {entry_px:.4f}")
print(f"     VWAP à l'entrée : {vw_entry:.4f}   (repli qui touche la VWAP puis rebond vert)")
print(f"     stop initial    : {entry_px*(1-STOP):.4f}  (-5%)")
print(f"\n  Contexte autour de l'entrée (bougies 1-min) :")
print(f"     {'heure':6} {'open':>7} {'high':>7} {'low':>7} {'close':>7} {'vwap':>7} {'vol':>8}")
lo=max(0,idx-3); hi=min(len(pm),idx+6)
for j in range(lo,hi):
    b=pm[j]; vwj=vwap(pm[:j+1])[-1]
    mark = ' <== ENTRÉE' if j==idx else ''
    print(f"     {hh(b['t']):6} {b['o']:7.3f} {b['h']:7.3f} {b['l']:7.3f} {b['c']:7.3f} {vwj:7.3f} {int(b['v']):>8}{mark}")
print(f"\n  SOMMET atteint  : {peak:.4f}  (+{(peak-entry_px)/entry_px*100:.1f}% = le MFE)")
print(f"  SORTIE  {hh(exit_t)} ET  @ {exit_px:.4f}  ({reason}, trailing 5% sous le sommet)")
print(f"\n  RÉSULTAT : {pnl:+.2f}%")
print(f"\n  (prix à l'open 9:30 = {rth[0]['o']:.4f} -> ce qu'on aurait eu en tenant = "
      f"{(rth[0]['o']-entry_px)/entry_px*100:+.1f}%)")
