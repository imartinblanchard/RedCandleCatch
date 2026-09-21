#!/usr/bin/env python3
"""Validation HORS ECHANTILLON : TRAIN=jan-avr, TEST=mai-aout. Configs entree basse + stop large + trail."""
import json, os
import numpy as np, pandas as pd

CACHE='/home/martin/dev/stock-journal-long/research/bars_cache'
RR_MIN=2.0; STOP_PCT=0.12; TRAIL=0.15; WIN_START,WIN_END=(7,0),(10,0)
SPLIT='2026-05-01'   # train < SPLIT <= test

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
    df['macd']=e12-e26; df['macd_sig']=df['macd'].ewm(span=9,adjust=False).mean()
    df['hod']=df.h.cummax()
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
        return dict(r=r,i=i,pb_high=max(x.h for x in pb),pb_low=min(x.l for x in pb),pb_close=pb[-1].c)
    return None

def sim(su, mode):
    r=su['r']; i=su['i']; n=len(r); ph,pl=su['pb_high'],su['pb_low']
    if mode=='break_high':
        if r.iloc[i].h<ph: return None
        entry=ph
    elif mode=='pb_close': entry=su['pb_close']
    elif mode=='pb_low':   entry=pl
    if mode!='break_high' and entry<pl: return None
    stop=entry*(1-STOP_PCT); hod=r.iloc[i-1].hod
    if entry-stop<=0 or (hod-entry)<RR_MIN*(entry-stop): return None
    peak=entry
    for j in range(i,n):
        rr=r.iloc[j]; peak=max(peak,rr.h)
        eff=max(stop, peak*(1-TRAIL))
        if rr.l<=eff: return (eff-entry)/entry*100
    return (r.iloc[-1].c-entry)/entry*100

gappers=json.load(open('/home/martin/dev/stock-journal-long/research/gappers.json'))
setups=[]
for g in gappers:
    df=load_df(g['ticker'],g['date'])
    if df is None or len(df)<60: continue
    s=find_setup(df)
    if s: setups.append((s,g['date']))
train=[s for s,d in setups if d<SPLIT]; test=[s for s,d in setups if d>=SPLIT]
print(f"Setups: {len(setups)}  |  TRAIN (jan-avr): {len(train)}  |  TEST (mai-aout): {len(test)}\n")

def stats(subset, mode):
    res=[sim(s,mode) for s in subset]; res=[x for x in res if x is not None]
    if not res: return (0,0,0,0)
    wins=[p for p in res if p>0]
    return (len(res),100*len(wins)//len(res),sum(res)/len(res),sum(res))

print(f"{'CONFIG':24} {'PERIODE':10} {'N':>4} {'WIN':>4} {'P&L moy':>8} {'CUMULE':>8}")
print("-"*66)
for mode,label in [('break_high','Cassure + stop-12 + trail'),
                   ('pb_close','Close rouge + stop-12 + trail'),
                   ('pb_low','Bas repli + stop-12 + trail')]:
    for name,subset in [('TRAIN',train),('TEST',test)]:
        n,wr,avg,cum=stats(subset,mode)
        print(f"{label:24} {name:10} {n:>4} {wr:>3}% {avg:>+7.2f}% {cum:>+7.0f}%")
    print()
