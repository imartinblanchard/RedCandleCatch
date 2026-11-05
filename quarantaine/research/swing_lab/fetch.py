#!/usr/bin/env python3
"""Récupère l'historique DAILY (Alpaca SIP, SPLIT-ADJUSTED) d'un ou plusieurs titres -> parquet,
pour la recherche SWING multi-titres (research/swing_lab/). Réutilise bot.alpaca_scanner._get_bars
(auth + fallback SIP/IEX). Split-adjusted = indispensable (évite les ruptures de prix aux splits).

Univers par défaut = ETF indices + secteurs SPDR : SANS biais du survivant (l'ETF gère ses
composants dans le temps), historique long -> plusieurs régimes (2018, 2020, 2022). Données isolées
dans data/research/swing/ (PAS collected_live, qui est l'univers live des gappers).

Usage :
  python -m research.swing_lab.fetch --universe            # tout l'univers ETF (~10 ans)
  python -m research.swing_lab.fetch --ticker NVDA --years 3
"""
import os, sys, argparse
from datetime import datetime, timezone, timedelta
import pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
from bot import alpaca_scanner as al
from research.swing_lab.universes import UNIVERSES

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(HERE)), 'data', 'research', 'swing')


def fetch_daily(ticker: str, years: float) -> pd.DataFrame:
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=int(years * 365.25) + 7)
    rows, token = [], None
    while True:
        params = {'timeframe': '1Day', 'start': start.isoformat(), 'end': end.isoformat(),
                  'adjustment': 'split', 'limit': 10000}
        if token:
            params['page_token'] = token
        data = al._get_bars(f'/v2/stocks/{ticker}/bars', params)
        for b in (data.get('bars') or []):
            rows.append(dict(date=b['t'][:10], o=b['o'], h=b['h'], l=b['l'], c=b['c'], v=b['v']))
        token = data.get('next_page_token')
        if not token:
            break
    return pd.DataFrame(rows).drop_duplicates('date').sort_values('date').reset_index(drop=True)


def save(ticker: str, years: float):
    df = fetch_daily(ticker, years)
    if not len(df):
        print(f"  ❌ {ticker}: aucune bougie (permissions ?)"); return None
    out = os.path.join(DATA_DIR, f'{ticker.lower()}_daily.parquet')
    df.to_parquet(out, index=False)
    print(f"  {ticker:<5} {len(df):>5} séances  {df.date.iloc[0]}..{df.date.iloc[-1]}  "
          f"close {df.c.iloc[-1]:.2f}")
    return df


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--ticker', default=None, help='un seul titre')
    ap.add_argument('--universe', choices=list(UNIVERSES), help='univers du registre (etf, nasdaq100)')
    ap.add_argument('--years', type=float, default=10)
    a = ap.parse_args()
    os.makedirs(DATA_DIR, exist_ok=True)
    tickers = UNIVERSES[a.universe] if a.universe else [a.ticker or 'NVDA']
    print(f"Fetch daily (split-adjusted, ~{a.years:.0f} ans) : {len(tickers)} titre(s) -> {DATA_DIR}")
    for tk in tickers:
        try:
            save(tk, a.years)
        except Exception as e:
            print(f"  ⚠️ {tk}: {e}")


if __name__ == '__main__':
    main()
