#!/usr/bin/env python3
"""Tableau consolidé par seuil de $vol sur la bougie de dip :
trades/jour, win%, R/R, exp/tr, pf, TOTAL% (somme mise fixe) et compte $10k @33%/pos."""
import os
from datetime import datetime
import numpy as np
import pandas as pd
import research.backtest_collected as BC
import research.reclassify_from_bars as RC
import research.portfolio_10k as P


def main():
    rc = RC.build()
    lab = {(r.date, r.ticker): r.gap_session for r in rc.itertuples()}
    files = [f for f in sorted(os.listdir(BC.BARS_DIR)) if f.endswith('.parquet')]
    # collecte : (date, entry_dt, exit_dt, pnl%, dvol)
    rows = []
    for f in files:
        date = f[:-8]
        df = pd.read_parquet(os.path.join(BC.BARS_DIR, f))
        for tk, g in df.groupby('ticker', sort=False):
            s = lab.get((date, tk))
            if s not in ('PM', 'post-open'):
                continue
            r = P.trade(g, 0.05 if s == 'PM' else 0.015)   # (entry_dt, exit_dt, pnl_frac, dvol)
            if r:
                rows.append((date, r[0], r[1], r[2] * 100, r[3]))
    D = pd.DataFrame(rows, columns=['date', 'ein', 'xout', 'pnl', 'dvol'])
    ndays = D['date'].nunique()

    print(f"Data collectée (sans biais) | {ndays} jours | dip PM -5% / post-open -1,5% | activation +5%")
    print(f"{'seuil $vol':11}{'n':>4}{'tr/j':>6}{'win%':>6}{'R/R':>6}{'exp/tr':>8}{'pf':>6}"
          f"{'TOTAL%':>8}{'$10k@33%':>10}{'maxDD':>7}")
    print('-' * 72)
    for thr, lb in [(0, 'aucun'), (50000, '>=50K'), (100000, '>=100K'),
                    (200000, '>=200K'), (300000, '>=300K')]:
        sub = D[D.dvol >= thr]
        x = sub['pnl'].values
        if len(x) < 2:
            print(f"{lb:11}  n<2"); continue
        w = x[x > 0]; l = x[x < 0]
        winr = 100 * (x > 0).mean()
        rr = (w.mean() / abs(l.mean())) if len(w) and len(l) else float('nan')
        pf = w.sum() / (-l.sum() or 1e-9)
        exp = x.mean()
        # compte $10k @ 33%/pos max3
        tr = [(datetime.strptime(f'{r.date} {r.ein}', '%Y-%m-%d %H:%M'),
               datetime.strptime(f'{r.date} {r.xout}', '%Y-%m-%d %H:%M'), r.pnl / 100)
              for r in sub.itertuples()]
        tr.sort(key=lambda z: z[0])
        final, maxdd = P.portfolio(tr, 0.33, 3)
        acct = (final / 10000 - 1) * 100
        print(f"{lb:11}{len(x):>4}{len(x)/ndays:>6.1f}{winr:>5.0f}%{rr:>6.2f}{exp:>+7.2f}%{pf:>6.2f}"
              f"{x.sum():>+7.0f}%{acct:>+9.0f}%{maxdd*100:>7.0f}%")


if __name__ == '__main__':
    main()
