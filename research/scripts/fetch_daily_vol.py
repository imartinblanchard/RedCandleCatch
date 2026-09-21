#!/usr/bin/env python3
"""Recupere le volume quotidien moyen (20j) de chaque ticker-jour -> daily_cache.
Sert au RVOL = volume cumule (pre-marche) / volume quotidien moyen.
Fetch groupe (multi-symboles) = efficace. adjustment='all'."""
import sys, json, os
from datetime import date, timedelta
from collections import defaultdict
import requests
sys.path.insert(0,'/home/martin/dev/stock-journal-long')
from bot import config as c

H={'APCA-API-KEY-ID':c.ALPACA_API_KEY_ID,'APCA-API-SECRET-KEY':c.ALPACA_API_SECRET_KEY}
R='/home/martin/dev/stock-journal-long/research'; DCACHE=f'{R}/daily_cache'; os.makedirs(DCACHE,exist_ok=True)
g=json.load(open(f'{R}/gappers.json'))
tickers=sorted(set(x['ticker'] for x in g))
START='2026-03-01'; END='2026-08-24'    # marge de 40j avant le 1er gapper (28 avr)
print(f"{len(tickers)} tickers, volume quotidien {START}->{END}")

def daily(symbols):
    out=defaultdict(list)
    params={'symbols':','.join(symbols),'timeframe':'1Day','start':START,'end':END,
            'feed':'sip','adjustment':'all','limit':10000}
    while True:
        r=requests.get('https://data.alpaca.markets/v2/stocks/bars',headers=H,timeout=60,params=params)
        if not r.ok: break
        j=r.json()
        for sym,bars in (j.get('bars') or {}).items(): out[sym].extend(bars)
        tok=j.get('next_page_token')
        if not tok: break
        params['page_token']=tok
    return out

# recupere toutes les bougies journalieres par lot
allbars={}
B=200
for k in range(0,len(tickers),B):
    allbars.update(daily(tickers[k:k+B]))
    if (k//B)%5==0: print(f"  ...{k+B}/{len(tickers)}",flush=True)

# pour chaque ticker-jour de l'univers : moyenne des 20 volumes AVANT la date
n=0
for x in g:
    tk,d=x['ticker'],x['date']
    cf=f'{DCACHE}/{tk}_{d}.json'
    bars=sorted(allbars.get(tk,[]),key=lambda b:b['t'])
    vols=[b['v'] for b in bars if b['t'][:10]<d]     # strictement avant la date
    avg=sum(vols[-20:])/len(vols[-20:]) if vols else 0
    json.dump(avg,open(cf,'w')); n+=1
print(f"TERMINE: {n} volumes moyens caches")
