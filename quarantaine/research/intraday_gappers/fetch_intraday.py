#!/usr/bin/env python3
"""
Étape 2 — Bougies 1-min du sous-ensemble LIQUIDE (vol matinal >= seuil). ISOLÉ.
Groupe par DATE et fetch multi-symboles (1 requête/jour) -> efficace.
Sortie : data/bars_1min.parquet (ticker,date,datetime,o,h,l,c,v)
       + data/meta.json (par ticker-jour : post_open, prev_close, morning_gap)
"""
import os, sys, json, time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from collections import defaultdict
import requests, pandas as pd
sys.path.insert(0, '/home/martin/dev/stock-journal-long')
from bot import config as c

HERE = os.path.dirname(os.path.abspath(__file__)); DATA = os.path.join(HERE, 'data')
ET = ZoneInfo('America/New_York')
H = {'APCA-API-KEY-ID': c.ALPACA_API_KEY_ID, 'APCA-API-SECRET-KEY': c.ALPACA_API_SECRET_KEY}
URL = 'https://data.alpaca.markets/v2/stocks/bars'
VOL_MIN = 500_000

rows_meta = json.load(open(os.path.join(DATA, 'intraday_gappers.json')))
sub = [x for x in rows_meta if x['morn_vol'] >= VOL_MIN]
by_date = defaultdict(list)
meta = {}
for x in sub:
    by_date[x['date']].append(x['ticker'])
    meta[f"{x['ticker']}|{x['date']}"] = {'post_open': x['post_open'],
                                          'prev_close': x['prev_close'], 'morning_gap': x['morning_gap']}
json.dump(meta, open(os.path.join(DATA, 'meta.json'), 'w'))
print(f"{len(sub)} ticker-jours (vol>={VOL_MIN//1000}K), {len(by_date)} dates, "
      f"{len(set(x['ticker'] for x in sub))} tickers", flush=True)

out = []
for di, (date, tickers) in enumerate(sorted(by_date.items())):
    start = date; end = (datetime.fromisoformat(date) + timedelta(days=1)).date().isoformat()
    tickers = list(dict.fromkeys(tickers))
    token = None
    while True:
        params = {'symbols': ','.join(tickers), 'timeframe': '1Min', 'start': start, 'end': end,
                  'feed': 'sip', 'adjustment': 'all', 'limit': 10000}
        if token:
            params['page_token'] = token
        r = requests.get(URL, headers=H, params=params, timeout=60)
        if r.status_code == 429:
            time.sleep(2); continue
        r.raise_for_status(); j = r.json()
        for sym, bars in (j.get('bars') or {}).items():
            for b in bars:
                t = datetime.fromisoformat(b['t'].replace('Z', '+00:00')).astimezone(ET)
                if t.date().isoformat() != date:
                    continue
                out.append((sym, date, t.strftime('%H:%M'), b['o'], b['h'], b['l'], b['c'], b['v']))
        token = j.get('next_page_token')
        if not token:
            break
    if di % 20 == 0:
        print(f"  ...{di}/{len(by_date)} dates, {len(out)} bougies", flush=True)
    time.sleep(0.1)

df = pd.DataFrame(out, columns=['ticker', 'date', 'datetime', 'o', 'h', 'l', 'c', 'v'])
df = df.sort_values(['ticker', 'date', 'datetime']).reset_index(drop=True)
outp = os.path.join(DATA, 'bars_1min.parquet'); df.to_parquet(outp)
print(f"\n✅ {len(df)} bougies, {df.ticker.nunique()} tickers, {df.groupby(['ticker','date']).ngroups} ticker-jours")
print(f"-> {outp}")
