#!/usr/bin/env python3
"""
Collecteur de DATA de recherche — TOUS les tickers qui passent nos filtres (PM + post-open).

Chaque jour, le dashboard écrit `redcandlecatch-eligible-YYYY-MM-DD.json` (sticky) avec les
métadonnées de chaque ticker éligible AU MOMENT où il devient éligible (temps réel ->
SANS biais du survivant, contrairement à candles.parquet historique).

Ce script transforme ces fichiers en un vrai jeu de données de recherche :
  1. `data/collected/eligibles.csv`  — table MAÎTRE (une ligne par ticker-jour) avec toutes
     les métadonnées + `is_premarket` (added < 09:31 -> gapper PM ; sinon runner post-open).
  2. `data/collected/bars/YYYY-MM-DD.parquet` — bougies 1-min 04:00-16:00 de chaque éligible
     du jour (o,h,l,c,v), récupérées via Alpaca SIP historique. Permet de backtester/analyser.

Idempotent : ne re-télécharge pas les bougies d'un jour déjà collecté (sauf --force).

    python -m bot.collect_eligibles                 # tous les jours éligibles non encore collectés
    python -m bot.collect_eligibles --date 2026-09-17
    python -m bot.collect_eligibles --no-bars        # métadonnées seulement (rapide, pas d'Alpaca)
    python -m bot.collect_eligibles --force          # re-télécharge même si déjà présent
"""
import argparse
import glob
import json
import os
from datetime import datetime

import pandas as pd

from bot import config
from bot.alpaca_scanner import ET, _get_bars

PREOPEN_CUTOFF = '09:31'       # même seuil que redcandlecatch_terminator : PM vs post-open
BARS_START = (4, 0)           # 04:00 ET
BARS_END = (16, 0)           # 16:00 ET (clôture régulière)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COMPUTED = os.path.join(ROOT, 'data', 'computed')
COLLECTED = os.path.join(ROOT, 'data', 'collected')
BARS_DIR = os.path.join(COLLECTED, 'bars')
MASTER = os.path.join(COLLECTED, 'eligibles.csv')

# champs de métadonnées conservés depuis le fichier d'éligibles
META_FIELDS = ['added', 'gap', 'price', 'pm_vol', 'pm_minutes', 'chart_rating',
               'volume_rating', 'float_rating', 'float_shares', 'inst_pct',
               'ssr', 'dollar_vol', 'reason']


def _eligible_files():
    return sorted(glob.glob(os.path.join(COMPUTED, 'redcandlecatch-eligible-*.json')))


def _date_of(path):
    return os.path.basename(path)[len('redcandlecatch-eligible-'):-len('.json')]


def build_master():
    """(Re)construit la table maître depuis TOUS les fichiers d'éligibles."""
    rows = []
    for path in _eligible_files():
        date = _date_of(path)
        try:
            data = json.load(open(path))
        except (json.JSONDecodeError, OSError):
            continue
        for tk, info in (data or {}).items():
            added = (info or {}).get('added') or ''
            row = {'date': date, 'ticker': tk,
                   'is_premarket': (not added) or (added < PREOPEN_CUTOFF)}
            for f in META_FIELDS:
                row[f] = (info or {}).get(f)
            rows.append(row)
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows).sort_values(['date', 'ticker']).reset_index(drop=True)
    os.makedirs(COLLECTED, exist_ok=True)
    df.to_csv(MASTER, index=False)
    return df


def fetch_day_bars(date, tickers):
    """Bougies 1-min 04:00-16:00 pour chaque ticker du jour -> DataFrame long."""
    day = datetime.strptime(date, '%Y-%m-%d').replace(tzinfo=ET)
    start = day.replace(hour=BARS_START[0], minute=BARS_START[1])
    end = day.replace(hour=BARS_END[0], minute=BARS_END[1])
    out = []
    for tk in tickers:
        try:
            data = _get_bars(f'/v2/stocks/{tk}/bars', {
                'timeframe': '1Min',
                'start': start.astimezone(ET).isoformat(),
                'end': end.astimezone(ET).isoformat(),
                'adjustment': 'raw',
                'limit': 1000,
            })
        except Exception as e:                       # noqa: BLE001 — un ticker qui échoue ne bloque pas le jour
            print(f"    ! {tk}: {e}")
            continue
        for bar in data.get('bars') or []:
            ts = datetime.fromisoformat(bar['t'].replace('Z', '+00:00')).astimezone(ET)
            if not (start <= ts < end):
                continue
            out.append({'ticker': tk, 'date': date, 'datetime': ts.strftime('%H:%M'),
                        'o': bar['o'], 'h': bar['h'], 'l': bar['l'],
                        'c': bar['c'], 'v': bar['v']})
    return pd.DataFrame(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--date', help='un seul jour YYYY-MM-DD (défaut : tous)')
    ap.add_argument('--no-bars', action='store_true', help='métadonnées seulement')
    ap.add_argument('--force', action='store_true', help='re-télécharge les bougies déjà présentes')
    args = ap.parse_args()

    master = build_master()
    if master.empty:
        print("Aucun fichier d'éligibles trouvé."); return
    n_pm = int(master['is_premarket'].sum()); n_po = len(master) - n_pm
    print(f"Table maître : {MASTER}")
    print(f"  {len(master)} ticker-jours  ({n_pm} PM / {n_po} post-open)  "
          f"sur {master['date'].nunique()} jours\n")

    if args.no_bars:
        return

    os.makedirs(BARS_DIR, exist_ok=True)
    dates = [args.date] if args.date else sorted(master['date'].unique())
    for date in dates:
        out_path = os.path.join(BARS_DIR, f'{date}.parquet')
        if os.path.exists(out_path) and not args.force:
            print(f"{date} : bougies déjà collectées (--force pour refaire)"); continue
        tickers = sorted(master[master['date'] == date]['ticker'].unique())
        print(f"{date} : téléchargement des bougies de {len(tickers)} tickers…")
        bars = fetch_day_bars(date, tickers)
        if bars.empty:
            print(f"    (aucune bougie — Alpaca n'a rien renvoyé)"); continue
        bars.to_parquet(out_path, index=False)
        print(f"    -> {len(bars)} bougies, {bars['ticker'].nunique()} tickers -> {out_path}")


if __name__ == '__main__':
    main()
