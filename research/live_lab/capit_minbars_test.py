#!/usr/bin/env python3
"""2e paramètre de la capitulation : capit_min_bars (longueur mini du repli). Live only.

La capitulation = dollar-vol moyen 2e moitié / 1re moitié du repli > ratio (1,3), calculé
sur n_pull bougies, avec n_pull >= capit_min_bars (=4 en v3). On a testé le RATIO ; ici on
balaie capit_min_bars (2..8), ratio fixe à 1,3, tout le reste = v3. Colonnes compte incluses.
collected_live uniquement.
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
from research.live_lab import backtest as bt
from research.live_lab.leaderboard import portfolio

MINBARS = [2, 3, 4, 5, 6, 8]   # 4 = v3


def main():
    groups, dates = bt.load_groups()
    split = bt.oos_split(dates)
    tdays = [d for d in dates if split and d >= split]
    print(f"{len(dates)} séances live ({dates[0]}→{dates[-1]}), OOS ≥ {split} ({len(tdays)} j test)")
    print("capit_ratio=1.3 fixe ; on balaie capit_min_bars ; reste = v3 ; sizing 2%, hold-EOD, slip ON\n")
    print(f"{'min_bars':<9}{'n':>4}{'tr/j':>6}{'exp/tr':>8}{'t':>6}{'win':>5}{'pf':>6}"
          f" | {'OOSexp':>7}{'t':>5} | {'CPTE2%':>8}{'OOS':>7} | {'CPTE1%':>8}{'OOS':>7}")
    print('-' * 100)
    for mb in MINBARS:
        P = dict(bt.LIVE); P['capit_min_bars'] = mb
        t = bt.simulate(groups, P, slip=True)
        if not len(t):
            print(f"{str(mb)+(' (v3)' if mb==4 else ''):<9} 0 trade"); continue
        s = bt.stat(t.pnl.to_numpy()); trday = len(t) / t.date.nunique()
        so = bt.stat(t[t.date >= split].pnl.to_numpy()) if split else s
        p2, _ = portfolio(t, 0.02, P['stop_pct']); p2o, _ = portfolio(t, 0.02, P['stop_pct'], days=tdays)
        p1, _ = portfolio(t, 0.01, P['stop_pct']); p1o, _ = portfolio(t, 0.01, P['stop_pct'], days=tdays)
        lab = f"{mb}" + (" (v3)" if mb == 4 else "")
        print(f"{lab:<9}{s['n']:>4}{trday:>6.1f}{s['exp']:>+7.2f}%{s['t']:>+6.2f}{s['win']:>4.0f}%{s['pf']:>6.2f}"
              f" | {so['exp']:>+6.2f}%{so['t']:>+5.2f} | {p2:>+7.1f}%{p2o:>+6.1f}% | {p1:>+7.1f}%{p1o:>+6.1f}%")
    print("\nCPTE = % gain compte (composé), risque 2% puis 1%, FULL puis OOS.")


if __name__ == '__main__':
    main()
