#!/usr/bin/env python3
"""Définitions ALTERNATIVES de « l'accélération du volume » (capitulation). Live only.

Idées Martin (23/10) : (1) un repli d'UNE seule bougie (flush brutal) peut être bon ;
(2) pas forcément besoin du split moitié/moitié — tester d'autres signaux de volume sur
la BOUGIE DE DIP elle-même : rvol (spike relatif), bar_dvol (gros $-vol), ou rebond vert.
On met le ratio moitié/moitié OFF (capit_ratio=-1) et on le remplace par ces gates.
collected_live uniquement ; colonnes compte incluses.
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
from research.live_lab import backtest as bt
from research.live_lab.leaderboard import portfolio

OFF = dict(capit_ratio=-1)   # retire le split moitié/moitié
VARIANTS = [
    ('v3 (ratio 1.3)',            dict()),
    ('capit OFF (rien)',          dict(OFF)),
    ('OFF + repli 1 bougie',      dict(OFF, capit_min_bars=1)),
    ('OFF + rvol>=2 (dip)',       dict(OFF, rvol_min=2)),
    ('OFF + rvol>=3 (dip)',       dict(OFF, rvol_min=3)),
    ('OFF + bar_dvol>=500K',      dict(OFF, bar_dvol_min=500_000)),
    ('OFF + bar_dvol>=1M',        dict(OFF, bar_dvol_min=1_000_000)),
    ('OFF + bougie verte',        dict(OFF, require_green=True)),
    ('OFF + 1-bougie + rvol>=3',  dict(OFF, capit_min_bars=1, rvol_min=3)),
    ('OFF + 1-bougie + bar_dvol>=1M', dict(OFF, capit_min_bars=1, bar_dvol_min=1_000_000)),
]


def main():
    groups, dates = bt.load_groups()
    split = bt.oos_split(dates)
    tdays = [d for d in dates if split and d >= split]
    print(f"{len(dates)} séances live ({dates[0]}→{dates[-1]}), OOS ≥ {split} ({len(tdays)} j test)")
    print("tout = v3 sauf l'accélération ; sizing 2%, hold-EOD, slip ON\n")
    print(f"{'définition':<30}{'n':>4}{'tr/j':>6}{'exp/tr':>8}{'t':>6}{'win':>5}{'pf':>6}"
          f" | {'OOSexp':>7}{'t':>5} | {'CPTE2%':>8}{'OOS':>7}")
    print('-' * 96)
    for lab, upd in VARIANTS:
        P = dict(bt.LIVE); P.update(upd)
        t = bt.simulate(groups, P, slip=True)
        if not len(t):
            print(f"{lab:<30}   0 trade"); continue
        s = bt.stat(t.pnl.to_numpy()); trday = len(t) / t.date.nunique()
        so = bt.stat(t[t.date >= split].pnl.to_numpy()) if split else s
        p2, _ = portfolio(t, 0.02, P['stop_pct']); p2o, _ = portfolio(t, 0.02, P['stop_pct'], days=tdays)
        print(f"{lab:<30}{s['n']:>4}{trday:>6.1f}{s['exp']:>+7.2f}%{s['t']:>+6.2f}{s['win']:>4.0f}%{s['pf']:>6.2f}"
              f" | {so['exp']:>+6.2f}%{so['t']:>+5.2f} | {p2:>+7.1f}%{p2o:>+6.1f}%")
    print("\nCPTE2% = % gain compte (composé), risque 2%, FULL puis OOS. OOS mince -> indicatif.")


if __name__ == '__main__':
    main()
