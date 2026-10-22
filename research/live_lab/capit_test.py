#!/usr/bin/env python3
"""Enlever (ou varier) le filtre de capitulation — sur NOS DONNÉES LIVE uniquement.

v3 actuel = capit_ratio 1,3. On teste OFF (-1), 1,0, 1,3, 1,6, 2,0, tout le reste identique.
Rendement/tr, t, OOS, trades/jour, et P&L compte % (sizing contraint capital, risque 2%).
collected_live seulement (règle 21/10).
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
from research.live_lab import backtest as bt
from research.live_lab.leaderboard import portfolio

VARIANTS = [
    ('capit OFF (-1)', -1),
    ('capit 1.0',      1.0),
    ('capit 1.3 (v3)', 1.3),
    ('capit 1.6',      1.6),
    ('capit 2.0',      2.0),
]


def main():
    groups, dates = bt.load_groups()
    split = bt.oos_split(dates)
    test_days = [d for d in dates if split and d >= split]
    print(f"{len(dates)} séances live ({dates[0]}→{dates[-1]}), OOS ≥ {split} ({len(test_days)} j test)")
    print("tout = v3 sauf capit ; sizing risque 2%, hold-EOD, slip ON\n")
    print(f"{'capit':<16}{'n':>4}{'tr/j':>6}{'exp/tr':>8}{'t':>6}{'win':>5}{'pf':>6} | {'OOS n':>6}{'OOS exp':>8}{'t':>6} | {'CPTE 2%':>8}{'CPTE OOS':>9}")
    print('-' * 100)
    for label, cr in VARIANTS:
        P = dict(bt.LIVE); P['capit_ratio'] = cr
        t = bt.simulate(groups, P, slip=True)
        if not len(t):
            print(f"{label:<16} 0 trade"); continue
        s = bt.stat(t.pnl.to_numpy()); trday = len(t) / t.date.nunique()
        so = bt.stat(t[t.date >= split].pnl.to_numpy()) if split else s
        pr, _ = portfolio(t, 0.02, P['stop_pct'])
        pro, _ = portfolio(t, 0.02, P['stop_pct'], days=test_days)
        print(f"{label:<16}{s['n']:>4}{trday:>6.1f}{s['exp']:>+7.2f}%{s['t']:>+6.2f}{s['win']:>4.0f}%{s['pf']:>6.2f} | "
              f"{so['n']:>6}{so['exp']:>+7.2f}%{so['t']:>+6.2f} | {pr:>+7.1f}%{pro:>+8.1f}%")


if __name__ == '__main__':
    main()
