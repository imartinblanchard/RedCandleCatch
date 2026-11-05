#!/usr/bin/env python3
"""Backtest de la strategie MICRO PULLBACK (prompt Ross) sur nos donnees SIP Alpaca (cache).
Construit VWAP/EMA9-20-200/MACD/tendance 5min, applique l'univers, calcule P&L."""
import json, os, csv
import numpy as np
import pandas as pd

CACHE='/home/martin/dev/stock-journal-long/research/bars_cache'
CHECKLIST='/home/martin/dev/stock-journal-long/data/long-checklist.csv'

# --- parametres (spec du prompt) ---
MIN_PRICE, MAX_PRICE = 2.0, 20.0
MIN_GAP = 25.0            # %
RR_MIN = 2.0             # 1:2
VOL_SPIKE = 2.0          # spike vendeur
WIN_START, WIN_END = (7,0), (10,0)   # ET

def load_df(tk,d):
    f=f"{CACHE}/{tk}_{d}.json"
    if not os.path.exists(f): return None
    df=pd.DataFrame(json.load(open(f)))
    if df.empty: return None
    df['t']=pd.to_datetime(df['t'])
    return df.set_index('t').sort_index()

def indics(df):
    tp=(df.h+df.l+df.c)/3
    df['vwap']=(tp*df.v).cumsum()/df.v.cumsum().replace(0,np.nan)
    df['ema9']=df.c.ewm(span=9,adjust=False).mean()
    df['ema20']=df.c.ewm(span=20,adjust=False).mean()
    df['ema200']=df.c.ewm(span=200,adjust=False).mean()
    e12=df.c.ewm(span=12,adjust=False).mean(); e26=df.c.ewm(span=26,adjust=False).mean()
    df['macd']=e12-e26; df['macd_sig']=df['macd'].ewm(span=9,adjust=False).mean()
    df['mhist']=df['macd']-df['macd_sig']
    df['hod']=df.h.cummax()
    df['avgvol5']=df.v.rolling(5).mean().shift(1)
    # tendance 5-min : EMA9(5m) > EMA20(5m)
    d5=df[['o','h','l','c','v']].resample('5min').agg({'o':'first','h':'max','l':'min','c':'last','v':'sum'}).dropna()
    up5=(d5.c.ewm(span=9,adjust=False).mean() > d5.c.ewm(span=20,adjust=False).mean())
    df['trend5']=up5.reindex(df.index,method='ffill').fillna(False)
    return df

def in_window(t):
    return WIN_START <= (t.hour,t.minute) < WIN_END

def backtest_symbol(df):
    df=indics(df); r=df.reset_index(); n=len(r)
    for i in range(6,n):
        row=r.iloc[i]; t=row['t']
        if not in_window(t): continue
        # setup (Section 3)
        if not (row.c>row.vwap and row.ema9>row.ema20>row.ema200
                and row.macd>0 and row.macd>row.macd_sig and bool(row.trend5)):
            continue
        # micro pullback finissant en i-1 (Section 4)
        p1=r.iloc[i-1]; p2=r.iloc[i-2]
        if not (p1.c<p1.o): continue          # derniere bougie doit etre rouge
        if p2.c<p2.o:                          # 2 rouges
            if r.iloc[i-3].c<r.iloc[i-3].o: continue   # 3e rouge -> pas micro
            pb=[p2,p1]; imp=r.iloc[i-5:i-2]
        else:                                  # 1 rouge
            pb=[p1]; imp=r.iloc[i-4:i-1]
        if len(imp)<2: continue
        if not (imp.iloc[-1].c>imp.iloc[0].c and (imp.c>=imp.o).sum()>=1): continue  # impulsion up
        imp_vol=imp.v.mean(); pb_vol=np.mean([x.v for x in pb])
        if not (imp_vol>0 and pb_vol<imp_vol): continue          # volume repli < impulsion
        pb_high=max(x.h for x in pb); pb_low=min(x.l for x in pb)
        if row.h<pb_high: continue             # trigger : cassure du high du pullback
        entry=pb_high; stop=pb_low; hod=r.iloc[i-1].hod; risk=entry-stop
        if risk<=0 or (hod-entry) < RR_MIN*risk: continue        # gate R:R 1:2
        return simulate(r,i,entry,stop,hod)
    return None

def simulate(r,i,entry,stop,hod):
    n=len(r); took=False; rem=1.0; pnl=0.0; prev_hist=r.iloc[i]['mhist']
    for j in range(i+1,n):
        row=r.iloc[j]
        if row.l<=stop:                         # stop
            pnl+=rem*(stop-entry)/entry*100; return (pnl,'STOP')
        if not took and row.h>=hod:             # TP1 : 50% au HOD
            pnl+=0.5*(hod-entry)/entry*100; rem=0.5; took=True; stop=entry  # breakeven runner
        bearish=prev_hist>0 and row['mhist']<=0
        below9=row.c<row.ema9
        spike=(row.c<row.o) and (row.avgvol5>0) and (row.v>=VOL_SPIKE*row.avgvol5)
        if bearish or below9 or spike:          # sorties d'urgence (Section 6)
            reason='MACD' if bearish else ('EMA9' if below9 else 'VSPIKE')
            pnl+=rem*(row.c-entry)/entry*100; return (pnl,reason)
        prev_hist=row['mhist']
    pnl+=rem*(r.iloc[-1].c-entry)/entry*100; return (pnl,'EOD')

# --- univers : les gappers historiques (deja filtres gap>=25% & prix 2-20$) ---
gappers=json.load(open('/home/martin/dev/stock-journal-long/research/gappers.json'))
universe=[(g['ticker'], g['date']) for g in gappers]
print(f"Univers gappers historiques : {len(universe)} lignes (jan-aout 2026)")

trades=[]; nodata=0; nosetup=0
for tk,d in universe:
    df=load_df(tk,d)
    if df is None or len(df)<60: nodata+=1; continue
    res=backtest_symbol(df)
    if res is None: nosetup+=1
    else: trades.append((tk,d)+res)

print(f"sans data: {nodata} | sans setup: {nosetup} | TRADES: {len(trades)}\n")
if trades:
    pnls=[t[2] for t in trades]; wins=[p for p in pnls if p>0]
    from collections import Counter
    print(f"Taux de reussite : {len(wins)}/{len(trades)} = {100*len(wins)//len(trades)}%")
    print(f"P&L moyen/trade  : {sum(pnls)/len(pnls):+.2f}%")
    print(f"Cumule           : {sum(pnls):+.1f}%")
    print(f"Sorties          : {dict(Counter(t[3] for t in trades))}")
    print("\nMeilleurs / pires :")
    for t in sorted(trades,key=lambda x:x[2],reverse=True)[:4]:
        print(f"  {t[2]:+6.1f}%  {t[0]:6} {t[1]} ({t[3]})")
    for t in sorted(trades,key=lambda x:x[2])[:4]:
        print(f"  {t[2]:+6.1f}%  {t[0]:6} {t[1]} ({t[3]})")
