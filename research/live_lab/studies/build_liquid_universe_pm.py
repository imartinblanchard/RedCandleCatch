#!/usr/bin/env python3
"""Univers LIQUIDE *CAUSAL* : fréquence de trades mesurée dans le PRÉ-MARCHÉ seulement.

Idée (Martin, 29/10) : pour rendre le filtre de liquidité utilisable EN LIVE (pas de look-ahead),
on juge la liquidité d'un titre sur son activité PRÉ-MARCHÉ. À l'open on connaît déjà le verdict,
bien avant l'entrée (10:00). Si le titre ne trade pas déjà en fréquence élevée en PM -> on l'écarte.

Par (ticker, date), fenêtres :
  - PM complet   04:00-09:30 (330 min)
  - PM tardif    08:00-09:30 (90 min)   <- plus prédictif de la liquidité à l'open
  - PM proche    09:00-09:30 (30 min)
On écrit date,ticker + pour chaque fenêtre : active_min (nb min avec trade), active_frac, dvol.
Puis distribution + nb de ticker-jours retenus à plusieurs seuils. collected_live uniquement.
"""
import os, glob
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
DATA = os.path.join(ROOT, 'data', 'collected_live')
OUT = os.path.join(HERE, '..', 'results', 'liquid_universe_pm.csv')
WINDOWS = {'pm': (240, 570), 'latepm': (480, 570), 'near': (540, 570)}   # minutes ET


def main():
    rows = []
    for f in sorted(glob.glob(os.path.join(DATA, 'bars-*.parquet'))):
        df = pd.read_parquet(f).drop_duplicates(['ticker', 'date', 'datetime'])
        df = df[df.datetime.str.len() == 5]
        df['m'] = df.datetime.str.slice(0, 2).astype(int) * 60 + df.datetime.str.slice(3, 5).astype(int)
        for (tk, d), g in df.groupby(['ticker', 'date'], sort=False):
            row = dict(date=d, ticker=tk)
            for name, (lo, hi) in WINDOWS.items():
                w = g[(g.m >= lo) & (g.m < hi)]
                act = int((w.v > 0).sum())
                row[f'{name}_active'] = act
                row[f'{name}_frac'] = round(act / (hi - lo), 3)
                row[f'{name}_dvol'] = int((w.v * w.c).sum())
            rows.append(row)
    u = pd.DataFrame(rows)
    u.to_csv(OUT, index=False)
    n = len(u)
    print(f"{n} ticker-jours. CSV -> {OUT}\n")
    for name in WINDOWS:
        fr = u[f'{name}_frac']
        print(f"=== {name}_frac (fréquence PM, {WINDOWS[name][0]//60}:00-{WINDOWS[name][1]//60}:{WINDOWS[name][1]%60:02d}) ===")
        print("  quantiles  " + "  ".join(f"p{int(q*100)}={fr.quantile(q):.2f}" for q in (.25, .5, .75, .9)))
        has_any = int((u[f'{name}_active'] > 0).sum())
        print(f"  ticker-jours avec AU MOINS 1 trade dans la fenêtre : {has_any} ({has_any/n*100:.0f}%)")
        for thr in [0.2, 0.3, 0.5, 0.7]:
            kept = u[fr >= thr]
            print(f"    frac >= {thr:.1f} : {len(kept):>5} ({len(kept)/n*100:>3.0f}%) | dvol médian ${kept[f'{name}_dvol'].median()/1e6:.1f}M")
        print()


if __name__ == '__main__':
    main()
