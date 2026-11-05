#!/usr/bin/env python3
"""Étape 1 (PM consécutif) : par ticker-jour, mesure la FRÉQUENCE de trades en PRÉ-MARCHÉ
orientée "minutes consécutives" (idée Martin 29/10).

PM = 04:00-09:30 (minutes 240-569). Une minute calendaire est ACTIVE si une bougie existe à
cette minute avec v>0. On calcule :
  - pm_frac    : fraction des 330 min PM actives
  - max_consec : plus long enchaînement de minutes consécutives TOUTES actives
  - reachK     : 1re minute (HH:MM ET) où les K dernières minutes sont TOUTES actives (= 1er
                 moment où le gate "K min consécutives" serait satisfait). Vide si jamais atteint.
Sortie CSV + distribution : combien de ticker-jours atteignent K min consécutives, et quand.
collected_live uniquement.
"""
import os, glob
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
DATA = os.path.join(ROOT, 'data', 'collected_live')
OUT = os.path.join(HERE, '..', 'results', 'pm_consec_table.csv')
PM_LO, PM_HI = 240, 570            # 04:00 -> 09:30
KS = [15, 20, 30, 45]


def hhmm(m):
    return f"{m//60:02d}:{m%60:02d}" if m is not None else ""


def main():
    rows = []
    for f in sorted(glob.glob(os.path.join(DATA, 'bars-*.parquet'))):
        df = pd.read_parquet(f).drop_duplicates(['ticker', 'date', 'datetime'])
        df = df[df.datetime.str.len() == 5]
        df['m'] = df.datetime.str.slice(0, 2).astype(int) * 60 + df.datetime.str.slice(3, 5).astype(int)
        pm = df[(df.m >= PM_LO) & (df.m < PM_HI)]
        for (tk, d), g in pm.groupby(['ticker', 'date'], sort=False):
            active = set(int(mm) for mm, vv in zip(g.m, g.v) if vv > 0)   # minutes PM actives
            # vecteur booléen sur toutes les minutes PM
            amin = PM_LO
            run = 0; maxrun = 0; reach = {k: None for k in KS}
            for mm in range(PM_LO, PM_HI):
                run = run + 1 if mm in active else 0
                maxrun = max(maxrun, run)
                for k in KS:
                    if reach[k] is None and run >= k:
                        reach[k] = mm
            row = dict(date=d, ticker=tk, pm_frac=round(len(active) / (PM_HI - PM_LO), 3),
                       max_consec=maxrun, pm_dvol=int((g.v * g.c).sum()))
            for k in KS:
                row[f'reach{k}'] = hhmm(reach[k])
                row[f'reach{k}_min'] = reach[k] if reach[k] is not None else np.nan
            rows.append(row)
    u = pd.DataFrame(rows)
    u.to_csv(OUT, index=False)
    n = len(u)
    print(f"{n} ticker-jours. CSV -> {OUT}\n")
    print("=== max_consec (plus longue série de minutes PM consécutives actives) ===")
    for q in (.5, .75, .9, .95, .99):
        print(f"  p{int(q*100):>2} = {u.max_consec.quantile(q):.0f} min")
    print(f"  max = {u.max_consec.max()} min\n")
    print("=== Combien de ticker-jours atteignent K min CONSÉCUTIVES en PM, et quand ===")
    for k in KS:
        reached = u[u[f'reach{k}_min'].notna()]
        pct = len(reached) / n * 100
        med = reached[f'reach{k}_min'].median()
        print(f"  K={k:>2} min : {len(reached):>5} ticker-jours ({pct:>4.0f}%) | "
              f"heure médiane d'atteinte {hhmm(int(med)) if len(reached) else '--'} | "
              f"dvol PM médian ${reached.pm_dvol.median()/1e6:.1f}M" if len(reached) else
              f"  K={k:>2} min : 0")


if __name__ == '__main__':
    main()
