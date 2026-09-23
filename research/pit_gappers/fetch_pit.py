#!/usr/bin/env python3
"""PIT rebuild — Phase 2 : fetch 1-min des ticker-jours candidats (Phase 1).

RÉSUMABLE : écrit un parquet par DATE dans data/bars/YYYY-MM-DD.parquet ; saute les dates
déjà faites. Ainsi un crash à mi-parcours ne perd rien. Le replay (Phase 3) lit tous ces
fichiers. prev_close vient de candidates.json (pas besoin de meta séparé).

1-min 04:00-20:00 ET, feed=sip, adjustment=all. Groupé par date, sous-lots de symboles.
"""
import os, sys, json, time, glob
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from collections import defaultdict
import requests, pandas as pd
sys.path.insert(0, '/home/martin/dev/stock-journal-long')
from bot import config as c

HERE = os.path.dirname(os.path.abspath(__file__)); DATA = os.path.join(HERE, 'data')
BARS_DIR = os.path.join(DATA, 'bars'); os.makedirs(BARS_DIR, exist_ok=True)
ET = ZoneInfo('America/New_York')
H = {'APCA-API-KEY-ID': c.ALPACA_API_KEY_ID, 'APCA-API-SECRET-KEY': c.ALPACA_API_SECRET_KEY}
URL = 'https://data.alpaca.markets/v2/stocks/bars'
SYM_BATCH = 100                     # symboles par requête (limite longueur URL)


def fetch_date(date, tickers):
    """Toutes les bougies 1-min de `date` pour `tickers` (04:00-20:00 ET)."""
    start = date; end = (datetime.fromisoformat(date) + timedelta(days=1)).date().isoformat()
    rows = []
    for k in range(0, len(tickers), SYM_BATCH):
        sub = tickers[k:k + SYM_BATCH]
        token = None
        while True:
            params = {'symbols': ','.join(sub), 'timeframe': '1Min', 'start': start, 'end': end,
                      'feed': 'sip', 'adjustment': 'all', 'limit': 10000}
            if token:
                params['page_token'] = token
            r = requests.get(URL, headers=H, params=params, timeout=90)
            if r.status_code == 429:
                time.sleep(2); continue
            r.raise_for_status(); j = r.json()
            for sym, bars in (j.get('bars') or {}).items():
                for b in bars:
                    t = datetime.fromisoformat(b['t'].replace('Z', '+00:00')).astimezone(ET)
                    if t.date().isoformat() != date:
                        continue
                    mn = t.hour * 60 + t.minute
                    if not (240 <= mn < 1200):        # 04:00-20:00
                        continue
                    rows.append((sym, date, t.strftime('%H:%M'), b['o'], b['h'], b['l'], b['c'], b['v']))
            token = j.get('next_page_token')
            if not token:
                break
    return rows


def main():
    cand = json.load(open(os.path.join(DATA, 'candidates.json')))
    by_date = defaultdict(list)
    for x in cand:
        by_date[x['date']].append(x['ticker'])
    dates = sorted(by_date)
    done = {os.path.basename(p)[:-8] for p in glob.glob(os.path.join(BARS_DIR, '*.parquet'))}
    todo = [d for d in dates if d not in done]
    print(f"{len(cand)} ticker-jours, {len(dates)} dates. Déjà fait: {len(done)}. À faire: {len(todo)}", flush=True)

    for i, date in enumerate(todo):
        tickers = list(dict.fromkeys(by_date[date]))
        try:
            rows = fetch_date(date, tickers)
        except Exception as e:
            print(f"  !! {date}: erreur {e} -> skip (sera repris au prochain run)", flush=True)
            continue
        df = pd.DataFrame(rows, columns=['ticker', 'date', 'datetime', 'o', 'h', 'l', 'c', 'v'])
        df = df.sort_values(['ticker', 'datetime']).reset_index(drop=True)
        df.to_parquet(os.path.join(BARS_DIR, f'{date}.parquet'))
        print(f"  [{i+1}/{len(todo)}] {date}: {len(tickers)} tickers, {len(df)} bougies", flush=True)
        time.sleep(0.1)

    total = len(glob.glob(os.path.join(BARS_DIR, '*.parquet')))
    print(f"\n✅ {total}/{len(dates)} dates fetchées -> {BARS_DIR}/", flush=True)
    if total < len(dates):
        print("⚠️ Incomplet : relance le script pour reprendre les dates manquantes.", flush=True)


if __name__ == '__main__':
    main()
