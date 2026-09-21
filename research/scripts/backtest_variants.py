#!/usr/bin/env python3
"""Compare des variantes : fenetre plus tot, RVOL 3x, gate volume cumule 150K (point-in-time).
Precharge les donnees une fois, puis rejoue chaque config."""
import json, os, sys
import numpy as np, pandas as pd
from collections import Counter
sys.path.insert(0, '/home/martin/dev/stock-journal-long/research/scripts')
from backtest_micropullback import load_1min, avg_daily_vol, indicators, is_topping_tail

R='/home/martin/dev/stock-journal-long/research'
MIN_PRICE,MAX_PRICE=2.0,20.0; MIN_PERF=0.10; RR_MIN=2.0

def walk(r, avg_dvol, win_start, win_end, rvol_min, min_cumvol):
    n=len(r); day_open=r.iloc[0].o
    if day_open<=0: return None
    for i in range(6,n):
        row=r.iloc[i]; t=row['et']
        if not (win_start<=(t.hour,t.minute)<win_end): continue
        price=row.c
        perf=(price-day_open)/day_open
        rvol=(row.cumvol/avg_dvol) if avg_dvol>0 else 0
        # --- contexte point-in-time (+ gate volume cumule) ---
        if not (perf>=MIN_PERF and MIN_PRICE<=price<=MAX_PRICE and price>row.vwap
                and price>row.ema9 and row.macd>0 and row.macd>row.sig
                and rvol>=rvol_min and row.cumvol>=min_cumvol):
            continue
        p1=r.iloc[i-1]; p2=r.iloc[i-2]
        if not (p1.c<p1.o): continue
        if p2.c<p2.o:
            if r.iloc[i-3].c<r.iloc[i-3].o: continue
            pb=[p2,p1]; imp=r.iloc[i-5:i-2]
        else: pb=[p1]; imp=r.iloc[i-4:i-1]
        if len(imp)<2 or not (imp.iloc[-1].c>imp.iloc[0].c and (imp.c>=imp.o).sum()>=1): continue
        imp_vol=imp.v.mean(); pb_vol=np.mean([x.v for x in pb])
        if not (imp_vol>0 and pb_vol<imp_vol): continue
        pb_high=max(x.h for x in pb); pb_low=min(x.l for x in pb)
        if row.h<pb_high: continue
        entry=pb_high; stop=pb_low; hod=r.iloc[i-1].hod
        if entry-stop<=0 or (hod-entry)<RR_MIN*(entry-stop): continue
        for j in range(i+1,n):
            rr=r.iloc[j]
            if rr.l<=stop: return (stop-entry)/entry*100,'STOP'
            if rr.h>=hod:  return (hod-entry)/entry*100,'TP'
            if ((rr.c<rr.o and rr.v>imp_vol) or rr.macd<rr.sig or rr.c<rr.ema9 or is_topping_tail(rr)):
                return (rr.c-entry)/entry*100,'EXIT'
        return (r.iloc[-1].c-entry)/entry*100,'EOD'
    return None

# --- precharge une seule fois (df+indicateurs+avg_dvol) ---
print("Prechargement des donnees...")
gappers=json.load(open(f'{R}/gappers.json'))
data=[]
for g in gappers:
    df=load_1min(g['ticker'],g['date'])
    if df is None: continue
    df=indicators(df).reset_index()
    data.append((walk_r:=df, avg_daily_vol(g['ticker'],g['date'])))
print(f"{len(data)} runners charges\n")

configs=[
 ((7,0),(10,0),5.0,0,      "ACTUEL: 7-10h, rvol5, no gate"),
 ((7,0),(10,0),3.0,0,      "rvol 3x, 7-10h"),
 ((6,0),(10,0),3.0,0,      "rvol 3x, DES 6h"),
 ((4,0),(10,0),3.0,0,      "rvol 3x, DES 4h"),
 ((4,0),(10,0),3.0,150_000,"rvol 3x, 4h + gate 150K"),
 ((6,0),(10,0),3.0,150_000,"rvol 3x, 6h + gate 150K"),
]
print(f"{'CONFIG':32} {'N':>4} {'WIN':>4} {'P&L moy':>8} {'CUMULE':>8}")
print("-"*62)
for ws,we,rv,gate,label in configs:
    res=[]
    for r,adv in data:
        x=walk(r,adv,ws,we,rv,gate)
        if x: res.append(x[0])
    if not res: print(f"{label:32} 0 trade"); continue
    wins=sum(1 for p in res if p>0)
    print(f"{label:32} {len(res):>4} {100*wins//len(res):>3}% {sum(res)/len(res):>+7.2f}% {sum(res):>+7.0f}%")
