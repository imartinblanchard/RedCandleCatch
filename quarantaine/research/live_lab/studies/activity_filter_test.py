#!/usr/bin/env python3
"""Filtre d'ACTIVITÉ : n'entrer que si le ticker trade (quasi) chaque minute. Live only.

Idée Martin : éviter les tickers avec des minutes mortes. Levier = `active_frac_min`
(causal, ligne 267 backtest.py) = fraction des minutes OUVERTURE->maintenant avec volume>0.
1.0 = une bougie-trade chaque minute ; 0.2 = surtout des minutes vides.
On balaye active_frac_min sur v3, S1, S2. Colonnes compte incluses. collected_live uniquement.
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(HERE))))
from research.live_lab import backtest as bt
from research.live_lab.leaderboard import portfolio

TRAIL = dict(exit_mode='trail', activate_pct=0.10, trail_pct=0.02)
BASES = {
    'v3':          dict(),
    'S1 qualité':  dict(gap_min=5.0, gap_max=10.0, retrace_pct=0.08, capit_ratio=2.0, hod_in_rth=True, **TRAIL),
    'S2 hautefréq': dict(gap_min=5.0, gap_max=50.0, entry_start=630, retrace_pct=0.12, capit_ratio=-1,
                         hod_in_rth=True, **TRAIL),
}
FRACS = [0.0, 0.5, 0.7, 0.8, 0.9, 0.95]


def main():
    groups, dates = bt.load_groups()
    split = bt.oos_split(dates); tdays = [d for d in dates if split and d >= split]
    print(f"{len(dates)} séances, OOS≥{split}. Sizing 2%, slip ON. active_frac_min = fraction mini de minutes actives (open->entrée).\n")
    for bname, bupd in BASES.items():
        print(f"######## {bname} ########")
        print(f"{'active_frac>=':<14}{'n':>4}{'tr/j':>6}{'exp/tr':>8}{'t':>6}{'win':>5}{'pf':>6} | {'OOSexp':>7}{'t':>5} | {'CPTE2%':>8}{'OOS':>7}")
        print('-' * 82)
        for af in FRACS:
            P = dict(bt.LIVE); P.update(bupd); P['active_frac_min'] = af
            t = bt.simulate(groups, P, slip=True)
            if not len(t):
                print(f"{af:<14}  0 trade"); continue
            s = bt.stat(t.pnl.to_numpy()); trj = len(t) / t.date.nunique()
            so = bt.stat(t[t.date >= split].pnl.to_numpy()) if split else s
            p2, _ = portfolio(t, 0.02, P['stop_pct']); p2o, _ = portfolio(t, 0.02, P['stop_pct'], days=tdays)
            print(f"{af:<14}{s['n']:>4}{trj:>6.1f}{s['exp']:>+7.2f}%{s['t']:>+6.2f}{s['win']:>4.0f}%{s['pf']:>6.2f}"
                  f" | {so['exp']:>+6.2f}%{so['t']:>+5.2f} | {p2:>+7.1f}%{p2o:>+6.1f}%")
        print()


if __name__ == '__main__':
    main()
