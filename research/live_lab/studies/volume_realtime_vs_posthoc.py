#!/usr/bin/env python3
"""Le volume d'une MÊME bougie 1-min diffère-t-il entre temps réel (signals) et post-clôture (bars) ?

Le bot logge dans signals-*.csv, pour chaque repli vu, la bougie (datetime) + son volume 'v'
TEL QU'IL L'A VU EN DIRECT. On re-cherche cette EXACTE minute (ticker+datetime) dans
bars-*.parquet (volume post-clôture consolidé) et on compare. Ça isole le mécanisme de l'écart :
  - si bars_v >> signals_v -> late prints / tape consolidée (le backtest surestime le volume).
  - si bars_v ≈ signals_v -> l'écart de pb_dvol vient d'ailleurs (fenêtre/nb de bougies).
"""
import os, glob
import numpy as np, pandas as pd

SDIR = 'data/collected_live'


def main():
    rows = []
    for sf in sorted(glob.glob(f'{SDIR}/signals-*.csv')):
        date = os.path.basename(sf)[8:-4]
        bf = f'{SDIR}/bars-{date}.parquet'
        if not os.path.exists(bf):
            continue
        s = pd.read_csv(sf)
        if 'v' not in s.columns or 'candle' not in s.columns:
            continue
        b = pd.read_parquet(bf)[['ticker', 'datetime', 'v']].rename(columns={'v': 'bars_v'})
        s = s[['ticker', 'candle', 'v']].rename(columns={'candle': 'datetime', 'v': 'rt_v'})
        m = s.merge(b, on=['ticker', 'datetime'], how='left')
        m['date'] = date
        rows.append(m)
    if not rows:
        print("aucune donnée signals+bars"); return
    d = pd.concat(rows, ignore_index=True)
    d = d.dropna(subset=['bars_v'])
    d['rt_v'] = d.rt_v.astype(float); d['bars_v'] = d.bars_v.astype(float)
    d = d[d.rt_v > 0]
    print(f"{len(d)} bougies comparées (minute temps réel vs post-clôture)\n")

    d['ratio'] = d.bars_v / d.rt_v
    print("=== Volume post-clôture / volume temps réel (même bougie) ===")
    print(f"  médiane : {d.ratio.median():.2f}x   moyenne : {d.ratio.mean():.2f}x")
    for q in [0.1, 0.25, 0.5, 0.75, 0.9]:
        print(f"    p{int(q*100):>2} : {d.ratio.quantile(q):.2f}x")
    print(f"  % de bougies où post-clôture > temps réel : {(d.bars_v > d.rt_v).mean()*100:.0f}%")
    print(f"  % identiques (ratio≈1, ±2%) : {((d.ratio>0.98)&(d.ratio<1.02)).mean()*100:.0f}%")
    print(f"  volume temps réel total : {d.rt_v.sum()/1e6:.1f}M  | post-clôture : {d.bars_v.sum()/1e6:.1f}M  "
          f"(x{d.bars_v.sum()/d.rt_v.sum():.2f})")
    print("\n=== Exemples (plus gros écarts) ===")
    ex = d.sort_values('ratio', ascending=False).head(12)
    print(ex[['date', 'ticker', 'datetime', 'rt_v', 'bars_v', 'ratio']].to_string(index=False))


if __name__ == '__main__':
    main()
