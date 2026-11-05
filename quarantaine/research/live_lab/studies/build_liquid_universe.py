#!/usr/bin/env python3
"""Étape 1 : construit l'univers LIQUIDE = tickers-jours qui tradent assez souvent (fréquence).

Par (ticker, date), sur les bougies RTH (9:30-15:59), on mesure :
  - active_frac = fraction des 390 minutes RTH avec un trade (v>0)  <-- la "fréquence"
  - dvol_rth    = $-volume total RTH
On écrit results/liquid_universe.csv (date, ticker, active_frac, dvol_rth) et on montre la
distribution + le nb de tickers-jours retenus à plusieurs seuils. collected_live uniquement.
"""
import os, sys, glob
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, '..', '..', '..', 'data', 'collected_live')
# chemin robuste : remonter à la racine projet
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
DATA = os.path.join(ROOT, 'data', 'collected_live')
OUT = os.path.join(HERE, '..', 'results', 'liquid_universe.csv')
RTH_MIN, RTH_MAX = 570, 960          # 9:30 -> 16:00
RTH_LEN = RTH_MAX - RTH_MIN          # 390 minutes


def main():
    rows = []
    for f in sorted(glob.glob(os.path.join(DATA, 'bars-*.parquet'))):
        df = pd.read_parquet(f).drop_duplicates(['ticker', 'date', 'datetime'])
        df = df[df.datetime.str.len() == 5]
        df['m'] = df.datetime.str.slice(0, 2).astype(int) * 60 + df.datetime.str.slice(3, 5).astype(int)
        rth = df[(df.m >= RTH_MIN) & (df.m < RTH_MAX)]
        for (tk, d), g in rth.groupby(['ticker', 'date'], sort=False):
            active = int((g.v > 0).sum())
            rows.append(dict(date=d, ticker=tk, active_frac=round(active / RTH_LEN, 3),
                             dvol_rth=int((g.v * g.c).sum())))
    u = pd.DataFrame(rows)
    u.to_csv(OUT, index=False)
    print(f"{len(u)} ticker-jours (toutes séances). CSV -> {OUT}\n")
    print("=== Distribution de active_frac (fréquence = % minutes RTH avec trade) ===")
    for q in [0.1, 0.25, 0.5, 0.75, 0.9, 0.95]:
        print(f"  p{int(q*100):>2} : {u.active_frac.quantile(q):.2f}")
    print(f"  moyenne : {u.active_frac.mean():.2f}\n")
    print("=== Nb de ticker-jours RETENUS selon le seuil de fréquence ===")
    for thr in [0.3, 0.5, 0.6, 0.7, 0.8, 0.9]:
        kept = u[u.active_frac >= thr]
        print(f"  active_frac >= {thr:.1f} : {len(kept):>5} ticker-jours ({len(kept)/len(u)*100:>4.0f}%) "
              f"| dvol médian ${kept.dvol_rth.median()/1e6:.1f}M")


if __name__ == '__main__':
    main()
