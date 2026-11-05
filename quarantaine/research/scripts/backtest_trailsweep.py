#!/usr/bin/env python3
"""Test stop plus large + trailing 'runner' pour capturer le MFE. Entree micro-pullback inchangee."""
import json, os
import numpy as np, pandas as pd
from collections import Counter

CACHE='/home/martin/dev/stock-journal-long/research/bars_cache'
MIN_GAP=25.0; RR_MIN=2.0; VOL_SPIKE=2.0; WIN_START,WIN_END=(7,0),(10,0)

def load_df(tk,d):
    f=f"{CACHE}/{tk}_{d}.json"
    if not os.path.exists(f): return None
    df=pd.DataFrame(json.load(open(f)))
    if df.empty: return None
    df['t']=pd.to_datetime(df['t']); return df.set_index('t').sort_index()

def indics(df):
    tp=(df.h+df.l+df.c)/3
    df['vwap']=(tp*df.v).cumsum()/df.v.cumsum().replace(0,np.nan)
    df['ema9']=df.c.ewm(span=9,adjust=False).mean(); df['ema20']=df.c.ewm(span=20,adjust=False).mean()
    df['ema200']=df.c.ewm(span=200,adjust=False).mean()
    e12=df.c.ewm(span=12,adjust=False).mean(); e26=df.c.ewm(span=26,adjust=False).mean()
    df['macd']=e12-e26; df['macd_sig']=df['macd'].ewm(span=9,adjust=False).mean(); df['mhist']=df['macd']-df['macd_sig']
    df['hod']=df.h.cummax(); df['avgvol5']=df.v.rolling(5).mean().shift(1)
    d5=df[['o','h','l','c','v']].resample('5min').agg({'o':'first','h':'max','l':'min','c':'last','v':'sum'}).dropna()
    up5=(d5.c.ewm(span=9,adjust=False).mean()>d5.c.ewm(span=20,adjust=False).mean())
    df['trend5']=up5.reindex(df.index,method='ffill').fillna(False); return df

def in_window(t): return WIN_START<=(t.hour,t.minute)<WIN_END

def find_setup(df):
    df=indics(df); r=df.reset_index(); n=len(r)
    for i in range(6,n):
        row=r.iloc[i]
        if not in_window(row['t']): continue
        if not (row.c>row.vwap and row.ema9>row.ema20>row.ema200 and row.macd>0 and row.macd>row.macd_sig and bool(row.trend5)): continue
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
        return r,i,entry,stop,hod
    return None

def sim(setup, stop_mode, use_tp1, runner):
    r,i,entry,pb_low,hod=setup; n=len(r)
    if stop_mode=='pullback': base=pb_low
    else: base=entry*(1-float(stop_mode[3:])/100)
    took=False; rem=1.0; pnl=0.0; peak=entry; prev=r.iloc[i]['mhist']
    tr=float(runner[5:])/100 if runner.startswith('trail') else None
    for j in range(i+1,n):
        rr=r.iloc[j]; peak=max(peak,rr.h)
        eff=base
        if tr is not None: eff=max(base, peak*(1-tr))
        if rr.l<=eff: pnl+=rem*(eff-entry)/entry*100; return pnl
        if use_tp1 and not took and rr.h>=hod:
            pnl+=0.5*(hod-entry)/entry*100; rem=0.5; took=True; base=max(base,entry)
        if runner=='aggressive':
            bear=prev>0 and rr['mhist']<=0; below=rr.c<rr.ema9
            spike=(rr.c<rr.o) and rr.avgvol5>0 and rr.v>=VOL_SPIKE*rr.avgvol5
            if bear or below or spike: pnl+=rem*(rr.c-entry)/entry*100; return pnl
        elif runner=='ema20close':
            if rr.c<rr.ema20: pnl+=rem*(rr.c-entry)/entry*100; return pnl
        prev=rr['mhist']
    pnl+=rem*(r.iloc[-1].c-entry)/entry*100; return pnl

gappers=json.load(open('/home/martin/dev/stock-journal-long/research/gappers.json'))
setups=[]
for g in gappers:
    df=load_df(g['ticker'],g['date'])
    if df is None or len(df)<60: continue
    s=find_setup(df)
    if s: setups.append(s)
print(f"{len(setups)} setups\n")

combos=[
 ('pct12',False,'trail 8', 'stop -12% + trail 8%'),
 ('pct12',False,'trail 10','stop -12% + trail 10%'),
 ('pct12',False,'trail 12','stop -12% + trail 12%'),
 ('pct12',False,'trail 15','stop -12% + trail 15%'),
 ('pct12',False,'trail 18','stop -12% + trail 18%'),
 ('pct10',False,'trail 10','stop -10% + trail 10%'),
 ('pct15',False,'trail 12','stop -15% + trail 12%'),
]
print(f"{'STRATEGIE':34} {'WIN':>4} {'P&L moy':>8} {'CUMULE':>8} {'gain moy WIN':>12}")
print("-"*72)
for sm,tp1,run,label in combos:
    res=[sim(s,sm,tp1,run) for s in setups]
    wins=[p for p in res if p>0]
    wavg=sum(wins)/len(wins) if wins else 0
    print(f"{label:34} {100*len(wins)//len(res):>3}% {sum(res)/len(res):>+7.2f}% {sum(res):>+7.0f}% {wavg:>+11.1f}%")
