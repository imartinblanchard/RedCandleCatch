#!/usr/bin/env python3
"""
Composition POINT-IN-TIME du S&P 500 + récupération des bougies des titres manquants.

1. Lit la composition historique (hanshof, date->liste de tickers).
2. Construit la membership sur notre fenêtre -> data/sp500_pit.json (liste {date,tickers}).
3. Récupère les bougies daily des tickers qui étaient dans l'indice mais qu'on n'a pas
   encore (les 'sortis'). Convertit BRK-B -> BRK.B pour Alpaca.
4. Rapporte : récupérés (démotions qui tradent encore) vs vides (rachetés/délistés = le
   trou résiduel qu'Alpaca ne sert pas).
Sortie : data/daily_pit.parquet (union des bougies) + data/sp500_pit.json.

Lancer : source .venv/bin/activate && python redcandleCatch_snp500/fetch_pit.py
"""
import os, sys, json, re
import pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.dirname(HERE))
import fetch_data                      # réutilise fetch_bars
from datetime import date, timedelta

DATA = os.path.join(HERE, 'data')
START, END = '2021-09-13', '2026-09-14'
VALID = re.compile(r'^[A-Z]{1,5}(\.[A-Z])?$')


def to_alpaca(sym):                    # BRK-B -> BRK.B ; None si symbole malformé
    s = sym.strip().replace('-', '.')
    return s if VALID.match(s) else None


def main():
    h = pd.read_csv(os.path.join(DATA, 'sp500_hist_hanshof.csv'))
    h['date'] = pd.to_datetime(h['date'])
    start, end = pd.Timestamp(START), pd.Timestamp(END)
    before = h[h.date < start].tail(1)
    win = pd.concat([before, h[(h.date >= start) & (h.date <= end)]])

    # membership point-in-time (convertie en tickers Alpaca)
    pit = []
    univ = set()
    for _, r in win.iterrows():
        tks = sorted({s for s in (to_alpaca(t) for t in r['tickers'].split(',')) if s})
        pit.append({'date': r['date'].date().isoformat(), 'tickers': tks})
        univ |= set(tks)
    json.dump(pit, open(os.path.join(DATA, 'sp500_pit.json'), 'w'))
    print(f"Membership point-in-time : {len(pit)} snapshots, univers {len(univ)} tickers")

    have = set(pd.read_parquet(os.path.join(DATA, 'daily.parquet')).ticker.unique())
    to_fetch = sorted(univ - have)
    print(f"On a déjà {len(have)} tickers ; à récupérer : {len(to_fetch)}")

    rows = fetch_data.fetch_bars(to_fetch, START, END) if to_fetch else []
    add = pd.DataFrame(rows, columns=['ticker', 'date', 'o', 'h', 'l', 'c', 'v'])
    got = set(add.ticker.unique())
    missing = sorted(set(to_fetch) - got)

    print(f"\n>> RÉCUPÉRÉS (tradent encore) : {len(got)}")
    print(f">> VIDES chez Alpaca (rachetés/délistés = trou résiduel) : {len(missing)}")
    print(f"   {missing}")

    # parquet union
    base = pd.read_parquet(os.path.join(DATA, 'daily.parquet'))
    allp = pd.concat([base, add]).drop_duplicates(['ticker', 'date']).sort_values(['ticker', 'date'])
    out = os.path.join(DATA, 'daily_pit.parquet')
    allp.to_parquet(out)
    print(f"\n✅ daily_pit.parquet : {allp.ticker.nunique()} titres, {len(allp)} bougies -> {out}")

    # taux de couverture du trou
    gap = len(univ - have)
    print(f"\nCouverture du trou du survivant : {len(got)}/{gap} récupérés "
          f"({100*len(got)/gap:.0f}%), {len(missing)} irrécupérables ({100*len(missing)/len(univ):.0f}% de l'univers).")


if __name__ == '__main__':
    main()
