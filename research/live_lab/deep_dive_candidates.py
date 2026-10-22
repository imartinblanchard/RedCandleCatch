#!/usr/bin/env python3
"""Approfondissement des pistes du sweep live + colonne P&L COMPTE (sizing).

Pour chaque config candidate (sur collected_live) : expectancy/tr, OOS, trades/jour,
ROBUSTESSE (retrait des 3 meilleurs trades), et surtout le **P&L COMPTE %** sous le
sizing contraint par le capital (leaderboard.portfolio) : la taille de position dépend
du nb de trades/jour ET du risque -> posfrac = min(risque/stop, budget/trades_jour, plafond).
Compounding quotidien, max 10 pos/jour, slippage ON. FULL + OOS, à risque 2% et 1%.

LIVE DATA UNIQUEMENT (règle 21/10).
"""
import os, sys
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
from research.live_lab import backtest as bt
from research.live_lab.leaderboard import portfolio

# pistes à creuser (overrides vs bt.LIVE)
CANDIDATES = [
    ('v3 LIVE (actuel)',        dict()),
    ('A: repli10 gap5-20 eod',  dict(retrace_pct=0.10, gap_max=20.0, capit_ratio=1.3, pullback_dvol_min=0)),
    ('A2: repli10 gap5-20 capit1.6 eod', dict(retrace_pct=0.10, gap_max=20.0, capit_ratio=1.6, pullback_dvol_min=0)),
    ('A-trail: repli10 gap5-20 trail', dict(retrace_pct=0.10, gap_max=20.0, capit_ratio=1.3, pullback_dvol_min=0,
                                             exit_mode='trail', activate_pct=0.10, trail_pct=0.02)),
    ('B: repli5 sans-capit gap5-10 trail', dict(retrace_pct=0.05, capit_ratio=-1, pullback_dvol_min=0,
                                                 exit_mode='trail', activate_pct=0.10, trail_pct=0.02)),
    ('B-eod: repli5 sans-capit gap5-10 eod', dict(retrace_pct=0.05, capit_ratio=-1, pullback_dvol_min=0)),
]


def acct(t, risk, stop, days=None):
    pr, dd = portfolio(t, risk, stop, days=days)
    return pr, dd


def trim_top(t, k):
    """retire les k trades au plus gros pnl (test de fragilité à la queue droite)."""
    if len(t) <= k:
        return t.iloc[0:0]
    idx = t.pnl.nlargest(k).index
    return t.drop(idx)


def main():
    groups, dates = bt.load_groups()
    split = bt.oos_split(dates)
    test_days = [d for d in dates if split and d >= split]
    print(f"{len(dates)} séances live ({dates[0]}→{dates[-1]}), OOS ≥ {split} ({len(test_days)} j test)")
    print("P&L COMPTE = portefeuille composé, sizing contraint capital (posfrac=min(risque/stop, budget/tr_jour, 20%)), slip ON\n")

    hdr = (f"{'CONFIG':<36} {'n':>4} {'tr/j':>5} {'exp/tr':>7} {'t':>5} | "
           f"{'OOS n':>5} {'OOS exp':>7} {'t':>5} | {'CPTE 2% F':>9} {'CPTE 2% OOS':>11} {'CPTE 1% F':>9} | "
           f"{'exp -top3':>9} {'CPTE2% -top3':>12}")
    print(hdr); print('-' * len(hdr))

    for label, upd in CANDIDATES:
        P = dict(bt.LIVE); P.update(upd)
        t = bt.simulate(groups, P, slip=True)
        if not len(t):
            print(f"{label:<36}  0 trade"); continue
        s = bt.stat(t.pnl.to_numpy()); trday = len(t) / t.date.nunique()
        te = t[t.date >= split] if split else t
        so = bt.stat(te.pnl.to_numpy()) if len(te) else {'n': 0, 'exp': 0, 't': 0}
        pr2, dd2 = acct(t, 0.02, P['stop_pct'])
        pr2o, _ = acct(t, 0.02, P['stop_pct'], days=test_days)
        pr1, _ = acct(t, 0.01, P['stop_pct'])
        tt = trim_top(t, 3)
        st = bt.stat(tt.pnl.to_numpy()) if len(tt) else {'exp': 0}
        pr2t, _ = acct(tt, 0.02, P['stop_pct']) if len(tt) else (0, 0)
        print(f"{label:<36} {s['n']:>4} {trday:>5.1f} {s['exp']:>+6.2f}% {s['t']:>+5.2f} | "
              f"{so['n']:>5} {so['exp']:>+6.2f}% {so['t']:>+5.2f} | "
              f"{pr2:>+8.1f}% {pr2o:>+10.1f}% {pr1:>+8.1f}% | "
              f"{st['exp']:>+8.2f}% {pr2t:>+11.1f}%")
    print("\nCPTE 2% F = P&L compte % période complète à risque 2% ; OOS = sur les jours de test ;")
    print("CPTE 1% F = idem risque 1% ; -top3 = en retirant les 3 meilleurs trades (fragilité).")


if __name__ == '__main__':
    main()
