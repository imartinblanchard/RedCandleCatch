#!/usr/bin/env python3
"""Diagnostic : est-ce qu'on sort trop tot ? Mesure le RUN APRES la sortie, par raison."""
import json, os
import numpy as np, pandas as pd
from collections import defaultdict

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

def trade(df):
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
        # simule et retourne (pnl, reason, exit_idx)
        took=False; rem=1.0; pnl=0.0; prev=r.iloc[i]['mhist']
        for j in range(i+1,n):
            rr=r.iloc[j]
            if rr.l<=stop: pnl+=rem*(stop-entry)/entry*100; return (pnl,'STOP',j,i,entry,r)
            if not took and rr.h>=hod: pnl+=0.5*(hod-entry)/entry*100; rem=0.5; took=True; stop=entry
            bear=prev>0 and rr['mhist']<=0; below=rr.c<rr.ema9
            spike=(rr.c<rr.o) and rr.avgvol5>0 and rr.v>=VOL_SPIKE*rr.avgvol5
            if bear or below or spike:
                reason='MACD' if bear else('EMA9' if below else 'VSPIKE')
                pnl+=rem*(rr.c-entry)/entry*100; return (pnl,reason,j,i,entry,r)
            prev=rr['mhist']
        pnl+=rem*(r.iloc[-1].c-entry)/entry*100; return (pnl,'EOD',n-1,i,entry,r)
    return None

gappers=json.load(open('/home/martin/dev/stock-journal-long/research/gappers.json'))
by=defaultdict(list)
for g in gappers:
    df=load_df(g['ticker'],g['date'])
    if df is None or len(df)<60: continue
    res=trade(df)
    if res is None: continue
    pnl,reason,exit_idx,entry_idx,entry,r=res
    # run APRES la sortie (plus haut atteint apres exit, relatif a l'entree)
    if exit_idx+1<len(r):
        peak_after=r.iloc[exit_idx+1:].h.max()
    else: peak_after=r.iloc[exit_idx].h
    run_after=(peak_after-entry)/entry*100      # ce que le trade valait au pic APRES sortie
    by[reason].append((pnl, run_after))

print(f"{'RAISON':8} {'N':>4} {'P&L moy':>8} {'PIC apres sortie':>16} {'laissé sur table':>16}")
print("-"*58)
allp=[]
for reason in ['STOP','EMA9','VSPIKE','MACD','EOD']:
    t=by.get(reason,[])
    if not t: continue
    allp+=[p for p,_ in t]
    pnl=sum(p for p,_ in t)/len(t)
    run=sum(ra for _,ra in t)/len(t)
    left=run-pnl
    print(f"{reason:8} {len(t):>4} {pnl:>+7.2f}% {run:>+15.1f}% {left:>+15.1f}%")
print("-"*58)
# combien de STOP ont ensuite fait un gros run ?
stops=by.get('STOP',[])
big=sum(1 for _,ra in stops if ra>15)
print(f"\nSur {len(stops)} STOP : {big} ({100*big//max(len(stops),1)}%) ont ensuite depasse +15% (on s'est fait sortir de gagnants)")
print(f"P&L moyen global : {sum(allp)/len(allp):+.2f}%")
