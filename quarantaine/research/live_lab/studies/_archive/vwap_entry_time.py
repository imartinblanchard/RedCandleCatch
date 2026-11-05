#!/usr/bin/env python3
"""vwap_reclaim (rvol>=60) : effet de l'HEURE d'entrée, par tranches de 5 min. Sur nos données live
(univers freq-filtré). (1) P&L moyen par tranche de 5 min (quelles minutes paient, lesquelles sont
du bruit). (2) Sweep du DÉBUT de fenêtre : si on ne trade qu'À PARTIR DE X (fin 10:30), que donne
exp/win/CPTE ? -> dit s'il faut sauter les toutes premières minutes (9:30-9:32 très bruitées).
⚠️ live only, petit n -> indicatif."""
import os, sys
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(HERE)))))
from research.live_lab import backtest as bt
from research.live_lab.leaderboard import portfolio
from research.indicator_lab import engine as E

TRAIL = dict(exit_mode='trail', activate_pct=0.10, trail_pct=0.02)


def main():
    groups, dates = bt.load_groups()
    liq = E.liquid_groups(groups)
    split = bt.oos_split(dates); tdays = [d for d in dates if split and d >= split]
    print(f"{len(dates)} séances, univers freq-filtré. vwap_reclaim rvol>=60, sortie TRAIL.\n", flush=True)

    # (1) P&L par tranche de 5 min (fenêtre complète 9:30-10:30)
    t = E.simulate(liq, 'vwap_reclaim', dict(entry_start=570, entry_end=630, rvol_gate=60.0, **TRAIL))
    t['bkt'] = (t.entry_min // 5) * 5
    print("=== (1) P&L par tranche de 5 min (fenêtre 9:30-10:30) ===")
    print(f"    {'tranche':>8}{'n':>5}{'exp/tr':>9}{'win%':>7}{'somme':>9}")
    for bkt, g in t.groupby('bkt'):
        hh, mm = bkt // 60, bkt % 60
        print(f"    {hh:02d}:{mm:02d}-{(bkt+5)//60:02d}:{(bkt+5)%60:02d}{len(g):>5}"
              f"{g.pnl.mean():>+8.2f}%{(g.pnl>0).mean()*100:>6.0f}%{g.pnl.sum():>+8.1f}%")

    # (2) sweep du début de fenêtre (fin fixe 10:30)
    print("\n=== (2) Si on ne trade QU'À PARTIR DE X (fin 10:30) ===")
    print(f"    {'dès':>6}{'n':>5}{'/j':>5}{'exp/tr':>9}{'win%':>7}{'CPTE':>8}{'maxDD':>8}")
    for es in range(570, 626, 5):
        tt = E.simulate(liq, 'vwap_reclaim', dict(entry_start=es, entry_end=630, rvol_gate=60.0, **TRAIL))
        if not len(tt):
            continue
        cp, dd = portfolio(tt, 0.02, 0.10)
        tag = '  <- actuel' if es == 570 else ''
        print(f"    {es//60:02d}:{es%60:02d}{len(tt):>5}{len(tt)/tt.date.nunique():>5.1f}"
              f"{tt.pnl.mean():>+8.2f}%{(tt.pnl>0).mean()*100:>6.0f}%{cp:>+7.1f}%{dd:>+7.1f}%{tag}")
    print("\n-> si l'exp/tr et le CPTE MONTENT en démarrant plus tard, les 1res minutes sont du bruit à éviter.")


if __name__ == '__main__':
    main()
