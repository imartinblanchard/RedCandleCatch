#!/usr/bin/env python3
"""Portefeuille combiné liq-eod (déployée) + e (gap 10-20) — les deux rentables, ~5% d'overlap.
Union des trades 1/ticker/jour (garde la 1re entrée), sizing 2%, compounding quotidien.
Compare liq-eod seule vs e seule vs combo : CPTE full+OOS (+ annualisé pommes-avec-pommes),
tr/j, exp/tr, DD, win. ⚠️ live only, petit n -> hypothèse. collected_live uniquement."""
import os, sys
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(HERE))))
from research.live_lab import backtest as bt
from research.live_lab.leaderboard import portfolio

TRAIL = dict(exit_mode='trail', activate_pct=0.10, trail_pct=0.02)
LIQEOD = dict(gap_min=5, gap_max=50, entry_start=600, retrace_pct=0.12, capit_ratio=-1,
              hod_in_rth=True, exit_mode='eod')
E = dict(gap_min=10, gap_max=20, entry_start=600, retrace_pct=0.10, capit_ratio=-1,
         hod_in_rth=True, recent_active_min=0.9, recent_active_window=10, **TRAIL)
TY = 252


def sim(groups, upd):
    P = dict(bt.LIVE); P.update(upd)
    return bt.simulate(groups, P, slip=True), P['stop_pct']


def line(lbl, t, stop, dates, tdays):
    pnl = t.pnl.to_numpy(); n = len(pnl)
    cp, dd = portfolio(t, 0.02, stop)
    cpo, _ = portfolio(t, 0.02, stop, days=tdays)
    nd, ndo = len(dates), max(len(tdays), 1)
    print(f"  {lbl:<16} n={n:>3} {n/t.date.nunique():.1f}/j exp={pnl.mean():+.2f}% "
          f"win={(pnl>0).mean()*100:.0f}% | CPTE full {cp:+.1f}% OOS {cpo:+.1f}% "
          f"| ~AN {cp*TY/nd:+.0f}% ~AN_OOS {cpo*TY/ndo:+.0f}% | maxDD {dd:+.1f}%", flush=True)


def main():
    groups, dates = bt.load_groups()
    split = bt.oos_split(dates); tdays = [d for d in dates if split and d >= split]
    print(f"{len(dates)} séances, OOS≥{split} ({len(tdays)} j). Sizing 2%, 1/ticker/jour.\n", flush=True)

    tl, sl = sim(groups, LIQEOD)
    te, se = sim(groups, E)
    both = pd.concat([tl.assign(src='liq-eod'), te.assign(src='e')], ignore_index=True)
    combo = both.sort_values('entry_min').drop_duplicates(['ticker', 'date'], keep='first')
    dup = len(both) - len(combo)

    print("STRATÉGIES SEULES :")
    line('liq-eod seule', tl, sl, dates, tdays)
    line('e seule', te, se, dates, tdays)
    print(f"\nCOMBO (union, {dup} doublon(s) ticker-jour retiré(s)) :")
    line('liq-eod + e', combo, sl, dates, tdays)
    add = combo[combo.src == 'e']
    print(f"\n  e apporte {len(add)} trade(s) que liq-eod n'avait pas "
          f"(exp {add.pnl.mean():+.2f}%) sur {len(te)} trades e au total.", flush=True)
    print("  -> compare ~AN full vs ~AN_OOS (pommes-avec-pommes) ; le CPTE brut OOS a moins de jours.", flush=True)


if __name__ == '__main__':
    main()
