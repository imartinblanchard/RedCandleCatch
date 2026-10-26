#!/usr/bin/env python3
"""L'activité récente aide-t-elle pour CERTAINES bandes de gap ? (test focalisé, live)

Base fixe : repli 8%, trail 10/2, capit OFF, 9:30->15:55 (volontairement large pour laisser
de la place au filtre). On fait varier gap x recent_active_min {off, >=0.8}. Colonnes compte.
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(HERE))))
from research.live_lab import backtest as bt
from research.live_lab.leaderboard import portfolio

GAPS = [(5, 10), (10, 20), (5, 20), (5, 50), (20, 50), (3, 10)]
BASE = dict(retrace_pct=0.08, capit_ratio=-1, exit_mode='trail', activate_pct=0.10, trail_pct=0.02,
            entry_start=570, entry_end=955)


def main():
    groups, dates = bt.load_groups()
    split = bt.oos_split(dates); tdays = [d for d in dates if split and d >= split]
    print(f"{len(dates)} séances, OOS≥{split}. base: repli8/trail/capitOFF/9:30-15:55, sizing 2%.\n")
    print(f"{'gap':<8}{'activité':<10}{'n':>4}{'tr/j':>6}{'exp/tr':>8}{'t':>6}{'win':>5}{'pf':>6} | {'OOSexp':>7}{'t':>5} | {'CPTE2%':>8}{'OOS':>7}")
    print('-' * 86)
    for gmin, gmax in GAPS:
        for ra, lab in [(0.0, 'off'), (0.8, '>=0.8')]:
            P = dict(bt.LIVE); P.update(BASE)
            P.update(gap_min=gmin, gap_max=gmax, recent_active_min=ra, recent_active_window=10)
            t = bt.simulate(groups, P, slip=True)
            g = f"{gmin}-{gmax}"
            if not len(t):
                print(f"{g:<8}{lab:<10}  0 trade"); continue
            s = bt.stat(t.pnl.to_numpy()); trj = len(t) / t.date.nunique()
            so = bt.stat(t[t.date >= split].pnl.to_numpy()) if split else s
            p2, _ = portfolio(t, 0.02, P['stop_pct']); p2o, _ = portfolio(t, 0.02, P['stop_pct'], days=tdays)
            print(f"{g:<8}{lab:<10}{s['n']:>4}{trj:>6.1f}{s['exp']:>+7.2f}%{s['t']:>+6.2f}{s['win']:>4.0f}%{s['pf']:>6.2f}"
                  f" | {so['exp']:>+6.2f}%{so['t']:>+5.2f} | {p2:>+7.1f}%{p2o:>+6.1f}%")
        print()


if __name__ == '__main__':
    main()
