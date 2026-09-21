#!/usr/bin/env python3
"""Construit le profil de RVOL time-of-day (14 jours) pour chaque ticker-jour.

Pour chaque ticker, on recupere l'historique intraday (5-min) et on batit, pour
chaque date de gap, la MOYENNE du volume cumule par minute sur les 14 jours de
bourse precedents. -> rvol_cache/{ticker}_{date}.json = {'grid':[...], 'base':[...]}

Le vrai RVOL par bougie = cumvol(T) aujourd'hui / base(T) (profil moyen 14j).
"""
import sys, json, os, time
from collections import defaultdict
import requests
sys.path.insert(0,'/home/martin/dev/stock-journal-long')
from bot import config as c
import pandas as pd

H={'APCA-API-KEY-ID':c.ALPACA_API_KEY_ID,'APCA-API-SECRET-KEY':c.ALPACA_API_SECRET_KEY}
R='/home/martin/dev/stock-journal-long/research'; RCACHE=f'{R}/rvol_cache'; os.makedirs(RCACHE,exist_ok=True)
g=json.load(open(sys.argv[1] if len(sys.argv)>1 else f'{R}/gappers.json'))
by_ticker=defaultdict(list)
for x in g: by_ticker[x['ticker']].append(x['date'])
START='2025-12-01'; END='2026-08-24'          # couvre le lookback 14j des gaps de debut janvier
GRID=list(range(240,991,5))     # 04:00 -> 16:30, pas de 5 min (minute-du-jour ET)
NDAYS=14
print(f"{len(by_ticker)} tickers | profil {NDAYS}j, grille {GRID[0]//60:02d}:00-{GRID[-1]//60:02d}:00",flush=True)

def fetch_5min(sym):
    """Toutes les bougies 5-min du ticker sur la periode (paginé). None si echec transitoire."""
    out=[]; params={'timeframe':'5Min','start':START,'end':END,'feed':'sip',
                     'adjustment':'all','limit':10000}
    url=f'https://data.alpaca.markets/v2/stocks/{sym}/bars'
    for attempt in range(3):
        ok=True; out=[]; params.pop('page_token',None)
        while True:
            r=requests.get(url,headers=H,timeout=60,params=params)
            if r.status_code==429 or r.status_code>=500:
                ok=False; time.sleep(2*(attempt+1)); break
            if not r.ok: return []          # 4xx defini -> pas de data
            j=r.json(); out.extend(j.get('bars') or [])
            tok=j.get('next_page_token')
            if not tok: break
            params['page_token']=tok
        if ok: return out
    return None                             # echec transitoire persistant

def day_grid(bars):
    """bars d'UNE journee -> volume cumule aligne sur GRID (forward-fill)."""
    mv=defaultdict(float)
    for b in bars:
        et=pd.Timestamp(b['t']).tz_convert('America/New_York')
        mv[et.hour*60+et.minute]+=b['v']
    cum=0.0; j=0; ks=sorted(mv); res=[]
    for gm in GRID:
        while j<len(ks) and ks[j]<=gm: cum+=mv[ks[j]]; j+=1
        res.append(cum)
    return res

done=skip=fail=0
for n,(tk,dates) in enumerate(sorted(by_ticker.items())):
    if all(os.path.exists(f'{RCACHE}/{tk}_{gd}.json') for gd in set(dates)):
        done+=len(set(dates)); continue           # deja en cache -> skip
    bars=fetch_5min(tk)
    if bars is None: fail+=1; continue
    # regroupe par date ET
    byd=defaultdict(list)
    for b in bars:
        et=pd.Timestamp(b['t']).tz_convert('America/New_York')
        byd[et.strftime('%Y-%m-%d')].append(b)
    grids={d:day_grid(bs) for d,bs in byd.items()}
    alld=sorted(grids)
    for gd in set(dates):
        priors=[d for d in alld if d<gd and grids[d][-1]>0][-NDAYS:]
        if not priors: skip+=1; continue
        base=[sum(grids[d][k] for d in priors)/len(priors) for k in range(len(GRID))]
        json.dump({'grid':GRID,'base':[round(x,1) for x in base]},
                  open(f'{RCACHE}/{tk}_{gd}.json','w'))
        done+=1
    if n%150==0: print(f"  ...{n}/{len(by_ticker)} | ok={done} skip={skip} fail={fail}",flush=True)
print(f"TERMINE: {done} profils | {skip} sans historique | {fail} tickers en echec",flush=True)
