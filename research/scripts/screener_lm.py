#!/usr/bin/env python3
"""Screener DERNIER MOIS avec prix 0.25-20$ (inclut les penny stocks).
Meme logique que screener_gappers.py mais fenetre courte + prix bas. -> research/lm/gappers.json"""
import sys, json, time
from datetime import datetime
from zoneinfo import ZoneInfo
from collections import defaultdict
import requests
sys.path.insert(0, '/home/martin/dev/stock-journal-long')
from bot import config as c

ET=ZoneInfo('America/New_York')
H={'APCA-API-KEY-ID':c.ALPACA_API_KEY_ID,'APCA-API-SECRET-KEY':c.ALPACA_API_SECRET_KEY}
DATA='https://data.alpaca.markets'; TRADE='https://paper-api.alpaca.markets'
START='2026-07-21'; END='2026-08-24'         # dernier mois (buffer pour la cloture veille)
KEEP_FROM='2026-07-24'                        # ne garder que les gaps a partir de cette date
MIN_GAP=0.10; MIN_P,MAX_P=0.25,20.0           # <-- PRIX 0.25-20$
OUT='/home/martin/dev/stock-journal-long/research/lm/gappers.json'

r=requests.get(f'{TRADE}/v2/assets',headers=H,params={'status':'active','asset_class':'us_equity'},timeout=60)
assets=[a['symbol'] for a in r.json() if a.get('tradable') and a.get('exchange') in ('NASDAQ','NYSE','ARCA','AMEX')
        and '.' not in a['symbol'] and '/' not in a['symbol']]
print(f"Univers : {len(assets)} symboles",flush=True)

def hourly(symbols):
    out=defaultdict(list); url=f'{DATA}/v2/stocks/bars'
    params={'symbols':','.join(symbols),'timeframe':'1Hour','start':START,'end':END,
            'feed':'sip','adjustment':'all','limit':10000}
    while True:
        rr=requests.get(url,headers=H,params=params,timeout=90)
        if not rr.ok: break
        j=rr.json()
        for sym,bars in (j.get('bars') or {}).items(): out[sym].extend(bars)
        tok=j.get('next_page_token')
        if not tok: break
        params['page_token']=tok
    return out

gappers=[]; B=150
for k in range(0,len(assets),B):
    data=hourly(assets[k:k+B])
    for sym,bars in data.items():
        byday=defaultdict(list)
        for b in bars:
            t=datetime.fromisoformat(b['t'].replace('Z','+00:00')).astimezone(ET)
            byday[t.date()].append((t,b))
        days=sorted(byday)
        for di in range(1,len(days)):
            if days[di].isoformat()<KEEP_FROM: continue
            prev=byday[days[di-1]]; today=byday[days[di]]
            regs=[b['c'] for t,b in prev if 10<=t.hour<=15]
            if not regs: continue
            prev_close=regs[-1]
            if prev_close<=0: continue
            pmbars=sorted([(t,b) for t,b in today if 4<=t.hour<=8], key=lambda x:x[0])
            if not pmbars: continue
            pm_open=pmbars[0][1]['o']
            pm_high=max(b['h'] for _,b in pmbars); pm_vol=sum(b['v'] for _,b in pmbars)
            gap=(pm_high-prev_close)/prev_close
            perf_open=(pm_high-pm_open)/pm_open if pm_open>0 else 0
            if gap>=MIN_GAP and MIN_P<=pm_high<=MAX_P:
                gappers.append({'ticker':sym,'date':days[di].isoformat(),
                                'gap':round(gap*100,1),'perf_open':round(perf_open*100,1),
                                'pm_open':round(pm_open,3),'pm_high':round(pm_high,3),
                                'pm_vol':int(pm_vol),'prev_close':round(prev_close,3)})
    if (k//B)%5==0: print(f"  ...{k+B}/{len(assets)}, {len(gappers)} gappers",flush=True)
    time.sleep(0.05)

json.dump(gappers,open(OUT,'w'))
dates=sorted(set(g['date'] for g in gappers)); tickers=sorted(set(g['ticker'] for g in gappers))
sub2=sum(1 for g in gappers if g['pm_high']<2.0)
print(f"\n{'='*50}")
print(f"Gappers >=10%, prix 0.25-20$, {dates[0]}->{dates[-1]} : {len(gappers)} ({len(tickers)} tickers uniques)")
print(f"  dont pm_high < 2$ (NOUVEAUX penny) : {sub2}")
print(f"-> {OUT}")
