#!/usr/bin/env python3
"""MACD DAILY par ticker -> flag par ticker-jour : croisement haussier recent ?
Point-in-time : n'utilise que les cloturees AVANT la date du gap.
Sortie: research/daily_macd.json = { 'TICKER|YYYY-MM-DD': {'cross':bool,'above':bool} }"""
import sys, json, os
from collections import defaultdict
import requests
sys.path.insert(0,'/home/martin/dev/stock-journal-long')
from bot import config as c
import pandas as pd, numpy as np

H={'APCA-API-KEY-ID':c.ALPACA_API_KEY_ID,'APCA-API-SECRET-KEY':c.ALPACA_API_SECRET_KEY}
R='/home/martin/dev/stock-journal-long/research'
g=json.load(open(f'{R}/gappers.json'))
by_ticker=defaultdict(set)
for x in g: by_ticker[x['ticker']].add(x['date'])
tickers=sorted(by_ticker)
START='2026-01-01'; END='2026-08-24'   # warmup large pour un MACD daily stable
L=3                                    # croisement dans les L dernieres seances avant D
print(f"{len(tickers)} tickers, MACD daily {START}->{END}",flush=True)

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

allbars={}
for k in range(0,len(tickers),200):
    allbars.update(daily(tickers[k:k+200]))
    print(f"  ...{k+200}/{len(tickers)}",flush=True)

flags={}
for tk,dates in by_ticker.items():
    bars=sorted(allbars.get(tk,[]),key=lambda b:b['t'])
    if len(bars)<35:
        for d in dates: flags[f'{tk}|{d}']={'cross':False,'above':False}
        continue
    s=pd.DataFrame(bars); s['d']=s['t'].str.slice(0,10); c_=s['c']
    macd=c_.ewm(span=12,adjust=False).mean()-c_.ewm(span=26,adjust=False).mean()
    sig=macd.ewm(span=9,adjust=False).mean()
    above=(macd>sig); cross=above & (~above.shift(1).fillna(False))   # croisement vers le haut
    s['above']=above.values; s['cross']=cross.values
    for d in dates:
        prior=s[s['d']<d]                          # STRICTEMENT avant la date du gap
        if len(prior)==0: flags[f'{tk}|{d}']={'cross':False,'above':False}; continue
        flags[f'{tk}|{d}']={'cross':bool(prior['cross'].iloc[-L:].any()),
                            'above':bool(prior['above'].iloc[-1])}
json.dump(flags,open(f'{R}/daily_macd.json','w'))
n_cross=sum(v['cross'] for v in flags.values()); n_above=sum(v['above'] for v in flags.values())
print(f"TERMINE: {len(flags)} ticker-jours | croisement<={L}j: {n_cross} | macd>sig: {n_above}",flush=True)
