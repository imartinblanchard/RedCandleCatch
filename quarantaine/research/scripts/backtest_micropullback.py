#!/usr/bin/env python3
"""
Backtest POINT-IN-TIME de la strategie Micro Pullback (spec Ross).

Rigueur anti-look-ahead : a chaque minute, on ne regarde QUE les donnees jusqu'a
cet instant (indicateurs causaux, HOD courant, perf courante, volume cumule).
Aucun filtre d'univers base sur des agregats de fin de pre-marche.

Univers = research/gappers.json (runners >=10% depuis l'open 04:00). Ce sont juste
les candidats a charger ; la decision de trade est 100% point-in-time.
"""
import json, os, sys, requests
import numpy as np, pandas as pd
from collections import Counter
sys.path.insert(0, '/home/martin/dev/stock-journal-long')
from bot import config as c

R='/home/martin/dev/stock-journal-long/research'
CACHE=f'{R}/bars_cache'; DCACHE=f'{R}/daily_cache'; os.makedirs(DCACHE, exist_ok=True)
H={'APCA-API-KEY-ID':c.ALPACA_API_KEY_ID,'APCA-API-SECRET-KEY':c.ALPACA_API_SECRET_KEY}

# ------- PARAMETRES (spec Ross, ajustables) -------
MIN_PRICE, MAX_PRICE = 2.0, 20.0
MIN_PERF   = 0.10        # hausse >=10% depuis l'open 04:00 (point-in-time)
RVOL_MIN   = 5.0         # volume cumule / volume quotidien moyen (point-in-time)
WIN_START, WIN_END = (7,0), (10,0)   # ET
RR_MIN     = 2.0         # R:R >= 1:2
AVG_VOL_DAYS = 20

def load_1min(tk,d):
    f=f"{CACHE}/{tk}_{d}.json"
    if not os.path.exists(f): return None
    df=pd.DataFrame(json.load(open(f)))
    if df.empty or len(df)<20: return None
    df['t']=pd.to_datetime(df['t']); df=df.set_index('t').sort_index()
    df['et']=df.index.tz_convert('America/New_York')
    return df

def avg_daily_vol(tk,d):
    """Volume quotidien moyen (20j avant la date). Pour le RVOL. Cache disque."""
    cf=f"{DCACHE}/{tk}_{d}.json"
    if os.path.exists(cf): return json.load(open(cf))
    from datetime import date, timedelta
    dd=date.fromisoformat(d)
    try:
        r=requests.get(f"{c.ALPACA_DATA_URL}/v2/stocks/{tk}/bars",headers=H,timeout=15,
            params={'timeframe':'1Day','start':(dd-timedelta(days=40)).isoformat(),
                    'end':(dd-timedelta(days=1)).isoformat(),'feed':'sip','adjustment':'all','limit':40})
        vols=[b['v'] for b in (r.json().get('bars') or [])] if r.ok else []
    except Exception: vols=[]
    avg=sum(vols[-AVG_VOL_DAYS:])/len(vols[-AVG_VOL_DAYS:]) if vols else 0
    json.dump(avg,open(cf,'w')); return avg

def indicators(df):
    """Indicateurs CAUSAUX (chaque valeur n'utilise que passe+present)."""
    tp=(df.h+df.l+df.c)/3
    df['vwap']=(tp*df.v).cumsum()/df.v.cumsum().replace(0,np.nan)
    df['ema9']=df.c.ewm(span=9,adjust=False).mean()
    e12=df.c.ewm(span=12,adjust=False).mean(); e26=df.c.ewm(span=26,adjust=False).mean()
    df['macd']=e12-e26; df['sig']=df['macd'].ewm(span=9,adjust=False).mean()
    df['hod']=df.h.cummax()                 # plus-haut de la seance JUSQU'ICI
    df['cumvol']=df.v.cumsum()              # volume cumule depuis l'open
    return df

def in_window(t): return WIN_START<=(t.hour,t.minute)<WIN_END

def is_topping_tail(bar):
    """Longue meche haute d'epuisement (shooting star)."""
    body=abs(bar.c-bar.o); upper=bar.h-max(bar.c,bar.o); rng=bar.h-bar.l
    return rng>0 and upper>2*body and upper>0.6*rng

def backtest_one(df, avg_dvol, prev_close):
    df=indicators(df); r=df.reset_index(); n=len(r)
    if not prev_close or prev_close<=0: return None
    for i in range(6,n):
        row=r.iloc[i]; t=row['et']
        if not in_window(t): continue
        price=row.c
        # --- CONTEXTE (point-in-time) ---
        # hausse mesuree VS CLOTURE VEILLE (comme un scanner "% gainers")
        perf=(price-prev_close)/prev_close
        rvol=(row.cumvol/avg_dvol) if avg_dvol>0 else 0
        if not (perf>=MIN_PERF and MIN_PRICE<=price<=MAX_PRICE and price>row.vwap
                and price>row.ema9 and row.macd>0 and row.macd>row.sig and rvol>=RVOL_MIN):
            continue
        # --- MICRO PULLBACK finissant en i-1 ---
        p1=r.iloc[i-1]; p2=r.iloc[i-2]
        if not (p1.c<p1.o): continue                    # derniere bougie rouge
        if p2.c<p2.o:                                    # 2 rouges
            if r.iloc[i-3].c<r.iloc[i-3].o: continue     # 3e rouge -> pas micro
            pb=[p2,p1]; imp=r.iloc[i-5:i-2]
        else: pb=[p1]; imp=r.iloc[i-4:i-1]               # 1 rouge
        if len(imp)<2 or not (imp.iloc[-1].c>imp.iloc[0].c and (imp.c>=imp.o).sum()>=1): continue
        imp_vol=imp.v.mean(); pb_vol=np.mean([x.v for x in pb])
        if not (imp_vol>0 and pb_vol<imp_vol): continue  # volume repli < impulsion
        pb_high=max(x.h for x in pb); pb_low=min(x.l for x in pb)
        if row.h<pb_high: continue                       # trigger : cassure du high du pullback
        entry=pb_high; stop=pb_low                       # PLUS de HOD : on entre sur la cassure
        if entry-stop<=0: continue                       # stop valide (plus de gate R:R vs HOD)
        # --- GESTION (forward) : stop + sorties d'urgence (plus de TP=HOD) ---
        for j in range(i+1,n):
            rr=r.iloc[j]
            if rr.l<=stop: return (stop-entry)/entry*100,'STOP',rvol
            red_hi_vol=(rr.c<rr.o) and rr.v>imp_vol      # bougie rouge a gros volume
            macd_cross=rr.macd<rr.sig
            below9=rr.c<rr.ema9
            topping=is_topping_tail(rr)
            if red_hi_vol or macd_cross or below9 or topping:
                reason='REDVOL' if red_hi_vol else ('MACD' if macd_cross else ('EMA9' if below9 else 'TAIL'))
                return (rr.c-entry)/entry*100,reason,rvol
        return (r.iloc[-1].c-entry)/entry*100,'EOD',rvol
    return None

# ------- RUN -------
if __name__=='__main__':
    gappers=json.load(open(f'{R}/gappers.json'))
    trades=[]; nodata=0
    for k,g in enumerate(gappers,1):
        df=load_1min(g['ticker'],g['date'])
        if df is None: nodata+=1; continue
        adv=avg_daily_vol(g['ticker'],g['date'])
        res=backtest_one(df,adv,g.get('prev_close'))
        if res: trades.append((g['ticker'],g['date'])+res)
        if k%100==0: print(f"  ...{k}/{len(gappers)} ({len(trades)} trades)",flush=True)

    print(f"\n{'='*56}")
    print(f"Univers: {len(gappers)} | sans data: {nodata} | TRADES: {len(trades)}")
    if trades:
        pnls=[t[2] for t in trades]; wins=[p for p in pnls if p>0]
        print(f"Reussite: {len(wins)}/{len(trades)} = {100*len(wins)//len(trades)}%")
        print(f"P&L moyen/trade: {sum(pnls)/len(pnls):+.2f}%  | cumule: {sum(pnls):+.0f}%")
        print(f"Sorties: {dict(Counter(t[3] for t in trades))}")
        print("Meilleurs / pires:")
        for t in sorted(trades,key=lambda x:x[2],reverse=True)[:4]:
            print(f"  {t[2]:+6.1f}%  {t[0]:6} {t[1]} ({t[3]}) rvol {t[4]:.0f}x")
        for t in sorted(trades,key=lambda x:x[2])[:3]:
            print(f"  {t[2]:+6.1f}%  {t[0]:6} {t[1]} ({t[3]})")
