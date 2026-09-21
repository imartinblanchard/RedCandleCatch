#!/usr/bin/env python3
"""
Screener PROPRE (v2) — repart a neuf. Corrige le bug des reverse splits.

- adjustment='all' (prix ajustes splits+dividendes) -> plus de faux gaps de split
- gap mesure sur le PLUS-HAUT DU PRE-MARCHE (04:00-09:00) vs cloture veille
  -> capture les runners qui montent tot puis fadent avant l'open 9:30
- gap >= 10% (proche du vrai scan de Ross), prix 2-20$
- enregistre pm_high ET pm_volume pour filtrer la liquidite APRES (sans re-scanner)

Sortie : research/gappers.json
"""
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
START='2025-12-26'; END='2026-08-24'        # ETENDU jusqu'a janvier 2026 (buffer pour cloture veille)
MIN_GAP=0.10; MIN_P,MAX_P=2.0,20.0           # gap >=10% VS CLOTURE VEILLE (comme un scanner), prix 2-20$
OUT='/home/martin/dev/stock-journal-long/research/gappers.json'

r=requests.get(f'{TRADE}/v2/assets',headers=H,params={'status':'active','asset_class':'us_equity'},timeout=60)
assets=[a['symbol'] for a in r.json() if a.get('tradable') and a.get('exchange') in ('NASDAQ','NYSE','ARCA','AMEX')
        and '.' not in a['symbol'] and '/' not in a['symbol']]
print(f"Univers : {len(assets)} symboles",flush=True)

def hourly(symbols):
    out=defaultdict(list); url=f'{DATA}/v2/stocks/bars'
    params={'symbols':','.join(symbols),'timeframe':'1Hour','start':START,'end':END,
            'feed':'sip','adjustment':'all','limit':10000}       # <-- LE FIX
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
            prev=byday[days[di-1]]; today=byday[days[di]]
            regs=[b['c'] for t,b in prev if 10<=t.hour<=15]     # cloture reguliere de la veille
            if not regs: continue
            prev_close=regs[-1]
            if prev_close<=0: continue
            pmbars=sorted([(t,b) for t,b in today if 4<=t.hour<=8], key=lambda x:x[0])
            if not pmbars: continue
            pm_open=pmbars[0][1]['o']
            pm_high=max(b['h'] for _,b in pmbars); pm_vol=sum(b['v'] for _,b in pmbars)
            # % vs CLOTURE VEILLE = ce qu'un scanner "% gainers" standard affiche
            gap=(pm_high-prev_close)/prev_close
            perf_open=(pm_high-pm_open)/pm_open if pm_open>0 else 0   # (info) hausse depuis 04:00
            if gap>=MIN_GAP and MIN_P<=pm_high<=MAX_P:
                gappers.append({'ticker':sym,'date':days[di].isoformat(),
                                'gap':round(gap*100,1),'perf_open':round(perf_open*100,1),
                                'pm_open':round(pm_open,3),'pm_high':round(pm_high,3),
                                'pm_vol':int(pm_vol),'prev_close':round(prev_close,3)})
    if (k//B)%5==0:
        print(f"  ...{k+B}/{len(assets)}, {len(gappers)} gappers",flush=True)
    time.sleep(0.05)

json.dump(gappers,open(OUT,'w'))
dates=sorted(set(g['date'] for g in gappers))
print(f"\n{'='*50}")
print(f"GAINERS >=10% vs cloture veille (comme un scanner), prix 2-20$ : {len(gappers)}")
print(f"sur {len(dates)} jours, du {dates[0]} au {dates[-1]}")
# apercu du filtrage volume possible
for thr in (250_000,500_000,1_000_000):
    n=sum(1 for g in gappers if g['pm_vol']>=thr)
    print(f"  dont vol PM >= {thr//1000}K : {n}")
print(f"-> research/gappers.json")
