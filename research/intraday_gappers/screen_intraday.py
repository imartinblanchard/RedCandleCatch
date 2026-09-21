#!/usr/bin/env python3
"""
Étape 1 — Screen des gappers INTRADAY (post-ouverture). ISOLÉ : n'écrit que dans
research/intraday_gappers/data/. Adapté de research/scripts/screener_gappers.py.

Pour chaque ticker-jour on calcule, en bougies 1H :
  pm_gap      = (plus-haut 04:00-08:59 - clôture veille) / clôture veille   (ancien critère)
  morning_gap = (plus-haut 09:00-11:59 - clôture veille) / clôture veille   (NOUVEAU)
On garde les ticker-jours où morning_gap ∈ [10,20]% et prix 3-20$, avec un flag :
  post_open = True  si pm_gap < 10%  (le titre n'a gappé QU'après l'ouverture = le cas raté)

Sortie : data/intraday_gappers.json
"""
import os, sys, json
from datetime import datetime
from zoneinfo import ZoneInfo
from collections import defaultdict
import requests
sys.path.insert(0, '/home/martin/dev/stock-journal-long')
from bot import config as c

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, 'data'); os.makedirs(DATA, exist_ok=True)
OUT = os.path.join(DATA, 'intraday_gappers.json')     # <-- ISOLÉ

ET = ZoneInfo('America/New_York')
H = {'APCA-API-KEY-ID': c.ALPACA_API_KEY_ID, 'APCA-API-SECRET-KEY': c.ALPACA_API_SECRET_KEY}
DATA_URL = 'https://data.alpaca.markets'; TRADE = 'https://paper-api.alpaca.markets'
START, END = '2025-12-26', '2026-08-24'               # même fenêtre que gappers.json (comparable)
BAND_LO, BAND_HI = 0.10, 0.20                         # bande 10-20% (celle du bot live)
MIN_P, MAX_P = 3.0, 20.0

r = requests.get(f'{TRADE}/v2/assets', headers=H,
                 params={'status': 'active', 'asset_class': 'us_equity'}, timeout=60)
assets = [a['symbol'] for a in r.json() if a.get('tradable')
          and a.get('exchange') in ('NASDAQ', 'NYSE', 'ARCA', 'AMEX')
          and '.' not in a['symbol'] and '/' not in a['symbol']]
print(f"Univers : {len(assets)} symboles", flush=True)


def hourly(symbols):
    out = defaultdict(list); url = f'{DATA_URL}/v2/stocks/bars'
    params = {'symbols': ','.join(symbols), 'timeframe': '1Hour', 'start': START, 'end': END,
              'feed': 'sip', 'adjustment': 'all', 'limit': 10000}
    while True:
        rr = requests.get(url, headers=H, params=params, timeout=90)
        if not rr.ok:
            break
        j = rr.json()
        for sym, bars in (j.get('bars') or {}).items():
            out[sym].extend(bars)
        tok = j.get('next_page_token')
        if not tok:
            break
        params['page_token'] = tok
    return out


rows = []; B = 150
for k in range(0, len(assets), B):
    data = hourly(assets[k:k + B])
    for sym, bars in data.items():
        byday = defaultdict(list)
        for b in bars:
            t = datetime.fromisoformat(b['t'].replace('Z', '+00:00')).astimezone(ET)
            byday[t.date()].append((t, b))
        days = sorted(byday)
        for di in range(1, len(days)):
            prev, today = byday[days[di - 1]], byday[days[di]]
            regs = [b['c'] for t, b in prev if 10 <= t.hour <= 15]
            if not regs:
                continue
            pc = regs[-1]
            if pc <= 0:
                continue
            pm = [b for t, b in today if 4 <= t.hour <= 8]
            morn = [b for t, b in today if 9 <= t.hour <= 11]      # 09:00-11:59
            if not morn:
                continue
            pm_high = max((b['h'] for b in pm), default=pc)
            morn_high = max(b['h'] for b in morn)
            morn_vol = sum(b['v'] for b in morn)
            pm_gap = (pm_high - pc) / pc
            morn_gap = (morn_high - pc) / pc
            if BAND_LO <= morn_gap < BAND_HI and MIN_P <= morn_high <= MAX_P:
                rows.append({'ticker': sym, 'date': days[di].isoformat(),
                             'pm_gap': round(pm_gap * 100, 1), 'morning_gap': round(morn_gap * 100, 1),
                             'post_open': bool(pm_gap < BAND_LO),
                             'morn_high': round(morn_high, 3), 'morn_vol': int(morn_vol),
                             'prev_close': round(pc, 3)})
    if (k // B) % 5 == 0:
        print(f"  ...{k + B}/{len(assets)}, {len(rows)} ticker-jours", flush=True)

json.dump(rows, open(OUT, 'w'))
po = sum(1 for x in rows if x['post_open'])
print(f"\n✅ {len(rows)} ticker-jours en bande 10-20% le matin")
print(f"   dont POST-OPEN (gap PM <10%, le cas raté par le bot) : {po} ({100*po/max(len(rows),1):.0f}%)")
print(f"   dont déjà PM-gappers (gap PM >=10%) : {len(rows)-po}")
print(f"-> {OUT}")
