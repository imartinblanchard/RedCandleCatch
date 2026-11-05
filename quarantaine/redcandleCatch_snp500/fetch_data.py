#!/usr/bin/env python3
"""
RedCandleCatch S&P 500 — récupération des données.

1. Liste des constituants ACTUELS du S&P 500 (Wikipedia).
2. ~1 an de bougies JOURNALIÈRES par titre (Alpaca SIP historique, adjustment=all
   -> pas de faux gaps de split/dividende).
Sortie : data/sp500.json  et  data/daily.parquet (colonnes ticker,date,o,h,l,c,v).

⚠️ Biais du survivant ASSUMÉ : constituants actuels -> les titres sortis du S&P 500
dans l'année sont absents. OK pour un v1 (voir README).

Lancer : source .venv/bin/activate && python redcandleCatch_snp500/fetch_data.py
"""
import os, sys, json, time
from datetime import date, timedelta
import requests
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
from bot import config          # réutilise le loader .env + les clés Alpaca

DATA = os.path.join(HERE, 'data')
os.makedirs(DATA, exist_ok=True)
WIKI = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
DAYS = 1830                     # ~5 ans + buffer (test multi-régimes)
BATCH = 100                     # symboles par requête bars


def get_sp500():
    """Symboles du S&P 500 depuis Wikipedia (table id=constituents)."""
    from bs4 import BeautifulSoup
    r = requests.get(WIKI, headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, 'html.parser')
    table = soup.find('table', id='constituents') or soup.find('table', class_='wikitable')
    syms = []
    for row in table.find_all('tr')[1:]:
        cells = row.find_all('td')
        if cells:
            sym = cells[0].get_text(strip=True).replace('\xa0', '')
            if sym:
                syms.append(sym)
    return sorted(set(syms))


def fetch_bars(symbols, start, end):
    """Bougies daily multi-symboles Alpaca (SIP hist, adjustment=all, paginé)."""
    url = f'{config.ALPACA_DATA_URL}/v2/stocks/bars'
    headers = {'APCA-API-KEY-ID': config.ALPACA_API_KEY_ID,
               'APCA-API-SECRET-KEY': config.ALPACA_API_SECRET_KEY}
    rows = []
    for k in range(0, len(symbols), BATCH):
        chunk = symbols[k:k + BATCH]
        token = None
        while True:
            params = {'symbols': ','.join(chunk), 'timeframe': '1Day',
                      'start': start, 'end': end, 'adjustment': 'all',
                      'feed': config.ALPACA_HIST_FEED, 'limit': 10000}
            if token:
                params['page_token'] = token
            resp = requests.get(url, headers=headers, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            for sym, bars in (data.get('bars') or {}).items():
                for b in bars:
                    rows.append((sym, b['t'][:10], b['o'], b['h'], b['l'], b['c'], b['v']))
            token = data.get('next_page_token')
            if not token:
                break
        print(f"  ...{min(k + BATCH, len(symbols))}/{len(symbols)} symboles, {len(rows)} bougies", flush=True)
        time.sleep(0.3)
    return rows


def main():
    print("1. Liste S&P 500 (Wikipedia)...")
    syms = get_sp500()
    print(f"   {len(syms)} constituants")
    json.dump(syms, open(os.path.join(DATA, 'sp500.json'), 'w'))

    end = (date.today() - timedelta(days=1)).isoformat()      # hier (SIP historique)
    start = (date.today() - timedelta(days=DAYS)).isoformat()
    print(f"2. Bougies daily {start} -> {end} (Alpaca SIP, adjustment=all)...")
    rows = fetch_bars(syms, start, end)

    df = pd.DataFrame(rows, columns=['ticker', 'date', 'o', 'h', 'l', 'c', 'v'])
    df = df.sort_values(['ticker', 'date']).reset_index(drop=True)
    out = os.path.join(DATA, 'daily.parquet')
    df.to_parquet(out)
    print(f"\n✅ {len(df)} bougies, {df.ticker.nunique()} titres, "
          f"{df.date.min()} -> {df.date.max()}")
    print(f"   -> {out}")
    manque = sorted(set(syms) - set(df.ticker.unique()))
    if manque:
        print(f"⚠️ {len(manque)} symboles sans données : {manque[:20]}{'...' if len(manque) > 20 else ''}")


if __name__ == '__main__':
    main()
