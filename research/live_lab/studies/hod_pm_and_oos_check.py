#!/usr/bin/env python3
"""(1) Isole les trades où le HOD est fait en PM vs en séance (RTH) et compare leur perf.
(2) Compare cpte full vs OOS en "pommes avec pommes" (par jour + par trade), vu que l'OOS a
    moins de jours/trades (remarque Martin 29/10). Base = la famille liq-eod. Live only."""
import os, sys
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(HERE))))
from research.live_lab import backtest as bt
from research.live_lab.leaderboard import portfolio


def base_P():
    P = dict(bt.LIVE)
    P.update(gap_min=5.0, gap_max=50.0, entry_start=600, entry_end=955, retrace_pct=0.12,
             capit_ratio=-1, require_green=False, vwap_side=None, exit_mode='eod')
    return P


def stat(pnl):
    pnl = np.asarray(pnl, float); n = len(pnl)
    if not n: return (0, 0.0, 0.0, 0.0)
    return (n, pnl.mean(), (pnl > 0).mean() * 100,
            pnl[pnl > 0].sum() / (-pnl[pnl < 0].sum() or 1e-9))


def main():
    groups, dates = bt.load_groups()
    split = bt.oos_split(dates)
    is_days = [d for d in dates if d < split]
    oos_days = [d for d in dates if d >= split]

    # (1) HOD-en-PM vs HOD-en-séance  (full univers, config liq-eod sans le filtre HOD)
    print("=" * 70)
    print("(1) HOD fait en PRÉ-MARCHÉ vs EN SÉANCE (gap5-50/10:00/repli12/noCapit, full univers)")
    P = base_P(); P['hod_in_rth'] = False
    t_all = bt.simulate(groups, P, slip=True)
    P2 = base_P(); P2['hod_in_rth'] = True
    t_rth = bt.simulate(groups, P2, slip=True)
    key = lambda df: set(zip(df.ticker, df.date))
    rth_keys = key(t_rth)
    t_all['hod_pm'] = ~t_all.apply(lambda r: (r.ticker, r.date) in rth_keys, axis=1)
    pm = t_all[t_all.hod_pm]; rt = t_all[~t_all.hod_pm]
    for lbl, sub in [('HOD en SÉANCE (hodRTH=on)', rt), ('HOD en PRÉ-MARCHÉ', pm), ('TOUS (hodRTH=off)', t_all)]:
        n, e, w, pf = stat(sub.pnl)
        cp, dd = portfolio(sub, 0.02, P['stop_pct']) if n else (0, 0)
        print(f"  {lbl:28s} n={n:3d}  exp={e:+5.2f}%  win={w:3.0f}%  pf={pf:4.1f}  cpte={cp:+5.1f}%  maxDD={dd:+5.1f}%")
    print("  -> si HOD-en-PM a une exp négative/faible, le filtre hodRTH a raison de l'exclure.")

    # (2) Pommes avec pommes : full vs OOS, normalisé par jour + par trade (config liq-eod complète)
    print("\n" + "=" * 70)
    print(f"(2) CPTE full vs OOS — {len(dates)} séances total, dont IS={len(is_days)} / OOS={len(oos_days)} (split {split})")
    Pf = base_P(); Pf['hod_in_rth'] = True
    t = bt.simulate(groups, Pf, slip=True)
    for lbl, days in [('FULL (toutes séances)', dates), ('IN-SAMPLE (avant split)', is_days), ('OOS (après split)', oos_days)]:
        sub = t[t.date.isin(days)]
        n = len(sub); nd = len(days)
        e = sub.pnl.mean() if n else 0.0
        cp, _ = portfolio(t, 0.02, Pf['stop_pct'], days=days)    # MÊME sizing (basé sur full), appliqué à ces jours
        print(f"  {lbl:24s} jours={nd:2d}  trades={n:3d}  exp/tr={e:+5.2f}%  "
              f"CPTE={cp:+6.1f}%  -> CPTE/jour={cp/max(nd,1):+5.2f}%  CPTE/trade={cp/max(n,1):+5.2f}%")
    print("  -> compare exp/tr (IS vs OOS) et CPTE/jour (IS vs OOS) : ÇA c'est pommes-avec-pommes.")
    print("     Le CPTE brut OOS est plus petit SURTOUT car il couvre moins de jours.")


if __name__ == '__main__':
    main()
