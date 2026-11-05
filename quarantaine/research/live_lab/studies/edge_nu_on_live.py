#!/usr/bin/env python3
"""L'edge « repli nu » (découvert sur pit) appliqué à NOS données live (collected_live).

Compare, sur nos ~16 séances live : la v3 actuelle (avec filtres anti-couteau) vs le
repli nu (sans filtres) vs repli nu + matin seulement (09:30-10:00). Donne exp/tr,
trades/jour, et profit portefeuille avec sizing contraint par le capital (leaderboard).

⚠️ n live minuscule -> indicatif, pas une preuve. Le gros échantillon = pit.
"""
import os, sys
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(HERE))))  # racine projet (studies/ = +1 niveau)
from research.live_lab import backtest as bt
from research.live_lab.leaderboard import portfolio, RISKS

BARE = dict(capit_ratio=-1, pullback_dvol_min=0, runup_min=0, gap_open_min=None)
CONFIGS = [
    ('v3 LIVE (actuel, filtres)', dict(bt.LIVE)),
    ('repli nu (sans filtres)',   dict(bt.LIVE, **BARE)),
    ('repli nu + matin 9:30-10h', dict(bt.LIVE, **BARE, entry_end=600)),
]


def main():
    groups, dates = bt.load_groups()
    split = bt.oos_split(dates)
    test_days = [d for d in dates if split and d >= split]
    print(f"{len(dates)} séances live ({dates[0]}→{dates[-1]}), split OOS ≥ {split} ({len(test_days)} j test)")
    print("sizing risque 2%, stop 10%, hold-EOD, slippage ON\n")

    for label, P in CONFIGS:
        t = bt.simulate(groups, P, slip=True)
        n = len(t)
        if not n:
            print(f"■ {label}: 0 trade\n"); continue
        s = bt.stat(t.pnl.to_numpy())
        tr_day = n / t.date.nunique()
        te = t[t.date >= split] if split else t
        so = bt.stat(te.pnl.to_numpy()) if len(te) else {'n': 0, 'exp': 0, 't': 0}
        prof, dd = portfolio(t, 0.02, P['stop_pct'])
        prof_oos, _ = portfolio(t, 0.02, P['stop_pct'], days=test_days)
        print(f"■ {label}")
        print(f"    FULL : n={s['n']:>3}  exp={s['exp']:>+5.2f}%/tr  t={s['t']:>+5.2f}  win={s['win']:>3.0f}%  pf={s['pf']:.2f}  | {tr_day:.1f} trades/jour")
        print(f"    OOS  : n={so['n']:>3}  exp={so['exp']:>+5.2f}%/tr  t={so['t']:>+5.2f}")
        print(f"    PORTEFEUILLE (risque 2%) : profit FULL {prof:>+6.1f}%  (maxDD {dd:>+5.1f}%)  |  profit OOS {prof_oos:>+6.1f}%")
        print()


if __name__ == '__main__':
    main()
