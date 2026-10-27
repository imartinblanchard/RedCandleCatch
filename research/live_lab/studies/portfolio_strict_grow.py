#!/usr/bin/env python3
"""Atteindre ~5 tr/j AVEC filtre d'activité STRICT en empilant PLUS de stratégies. Live only.

Idée Martin : chaque strat stricte (recent_active 0.9 = trade quasi chaque minute) donne peu de
trades, donc on en empile plusieurs pour atteindre ~5/j. Pool élargi (~24), filtre strict,
sélection GLOUTONNE (on ajoute à chaque étape la strat qui maximise le CPTE combiné) -> on voit
trades/j ET CPTE monter étape par étape. collected_live uniquement.
"""
import os, sys, itertools
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(HERE))))
from research.live_lab import backtest as bt
from research.live_lab.leaderboard import portfolio

RA = 0.9
TRAIL = dict(exit_mode='trail', activate_pct=0.10, trail_pct=0.02)
GAPS = [(3, 10), (5, 10), (5, 20), (10, 20), (20, 50), (5, 50)]
STARTS = [570, 600]
# 2 presets par (gap,start) : repli8 (capit selon gap) et repli12 sans-capit + vert
MIN_N = 8


def build_pool():
    pool = {}
    for (gm, gx) in GAPS:
        for st in STARTS:
            cap = 1.6 if gx <= 10 else -1
            pool[f"{gm}-{gx}/{st}/r8"] = dict(gap_min=gm, gap_max=gx, entry_start=st, retrace_pct=0.08, capit_ratio=cap)
            pool[f"{gm}-{gx}/{st}/r12g"] = dict(gap_min=gm, gap_max=gx, entry_start=st, retrace_pct=0.12, capit_ratio=-1, require_green=True)
    return pool


def combine(dfs):
    allt = pd.concat(dfs, ignore_index=True)
    return allt.sort_values('entry_min').drop_duplicates(['ticker', 'date'], keep='first')


def main():
    groups, dates = bt.load_groups()
    split = bt.oos_split(dates); tdays = [d for d in dates if split and d >= split]
    pool = build_pool()
    print(f"{len(dates)} séances, recent_active={RA}, hodRTH, trail. Pool={len(pool)}.\n", flush=True)
    sims = {}
    for name, upd in pool.items():
        P = dict(bt.LIVE); P.update(upd, **TRAIL, hod_in_rth=True, recent_active_min=RA, recent_active_window=10)
        t = bt.simulate(groups, P, slip=True)
        if len(t) >= MIN_N and t.pnl.mean() > 0:
            sims[name] = t[['ticker', 'date', 'entry_min', 'pnl']]
    print(f"{len(sims)} stratégies survivent au filtre strict (n>={MIN_N}, exp>0).\n", flush=True)

    # sélection GLOUTONNE : on ajoute la strat qui maximise le CPTE combiné
    chosen = []; chosen_df = []; best = -1e9; remaining = dict(sims)
    print("Étape | +stratégie                 | trades/j | exp/tr | CPTE | OOS")
    print("-" * 76, flush=True)
    while remaining:
        bc = None
        for name, df in remaining.items():
            comb = combine(chosen_df + [df])
            cp, _ = portfolio(comb, 0.02, 0.10)
            if cp > (bc[1] if bc else best):
                bc = (name, cp, comb)
        if not bc or bc[1] <= best + 0.01:
            break
        name, cp, comb = bc
        chosen.append(name); chosen_df.append(remaining.pop(name)); best = cp
        trj = len(comb) / comb.date.nunique()
        exp = comb.pnl.mean()
        cpo, _ = portfolio(comb, 0.02, 0.10, days=tdays)
        print(f"  {len(chosen):>2}  | {name:<26} | {trj:>5.1f}/j  | {exp:>+5.2f}% | {cp:>+5.1f}% | {cpo:>+5.1f}%", flush=True)
    print(f"\nPortefeuille retenu ({len(chosen)} strat) : {', '.join(chosen)}", flush=True)
    comb = combine(chosen_df); trj = len(comb) / comb.date.nunique()
    cp, dd = portfolio(comb, 0.02, 0.10); cpo, _ = portfolio(comb, 0.02, 0.10, days=tdays)
    print(f"-> {len(comb)} trades, {trj:.1f}/j, exp {comb.pnl.mean():+.2f}%, CPTE {cp:+.1f}% / OOS {cpo:+.1f}%, maxDD {dd:+.1f}%", flush=True)


if __name__ == '__main__':
    main()
