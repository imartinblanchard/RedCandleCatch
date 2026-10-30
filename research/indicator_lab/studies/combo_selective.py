#!/usr/bin/env python3
"""Compare 3 options : (A) liq-eod seule (repli déployé), (B) vwap_reclaim(rvol>=60) seule
(candidate sélective), (C) combo A+B (union 1/ticker-jour, sizing 2%). CPTE full/OOS + annualisé
pommes-avec-pommes, DD, fréquence. ⚠️ live only, in-sample 23 j, hypothèse. collected_live only."""
import os, sys
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(HERE)))))
from research.live_lab import backtest as bt
from research.live_lab.leaderboard import portfolio
from research.indicator_lab import engine as E

TY = 252


def line(lbl, t, dates, tdays):
    pnl = t.pnl.to_numpy(); n = len(pnl)
    cp, dd = portfolio(t, 0.02, 0.10); cpo, _ = portfolio(t, 0.02, 0.10, days=tdays)
    nd, ndo = len(dates), max(len(tdays), 1)
    print(f"  {lbl:<32} n={n:>4} {n/t.date.nunique():>4.1f}/j exp={pnl.mean():+.2f}% win={(pnl>0).mean()*100:>3.0f}% "
          f"| CPTE {cp:+6.1f}% OOS {cpo:+6.1f}% | ~AN {cp*TY/nd:+5.0f}% ~AN_OOS {cpo*TY/ndo:+5.0f}% | maxDD {dd:+5.1f}%",
          flush=True)


def main():
    groups, dates = bt.load_groups()
    liq = E.liquid_groups(groups)
    split = bt.oos_split(dates); tdays = [d for d in dates if split and d >= split]
    print(f"{len(dates)} séances, OOS≥{split} ({len(tdays)} j). Sizing 2%, 1/ticker-jour.\n", flush=True)

    Pl = dict(bt.LIVE); Pl.update(gap_min=5, gap_max=50, entry_start=600, retrace_pct=0.12,
                                  capit_ratio=-1, hod_in_rth=True, exit_mode='eod')
    tl = bt.simulate(groups, Pl, slip=True)
    tv = E.simulate(liq, 'vwap_reclaim', dict(entry_start=570, entry_end=630, rvol_gate=60.0,
                                              exit_mode='trail', activate_pct=0.10, trail_pct=0.02))
    both = pd.concat([tl[['ticker', 'date', 'entry_min', 'pnl']],
                      tv[['ticker', 'date', 'entry_min', 'pnl']]], ignore_index=True)
    combo = both.sort_values('entry_min').drop_duplicates(['ticker', 'date'], keep='first')
    dup = len(both) - len(combo)

    print("A) liq-eod seule (repli déployé) :")
    line('liq-eod', tl, dates, tdays)
    print("\nB) vwap_reclaim(rvol>=60) seule (candidate) :")
    line('vwap_reclaim rvol>=60', tv, dates, tdays)
    print(f"\nC) COMBO A+B (union, {dup} doublon(s) retiré(s)) :")
    line('liq-eod + vwap_reclaim', combo, dates, tdays)

    ov = len(set(zip(tl.ticker, tl.date)) & set(zip(tv.ticker, tv.date)))
    print(f"\n  overlap liq-eod/vwap_reclaim : {ov} trades communs (sur {len(tv)} vwap / {len(tl)} liq-eod)", flush=True)
    print("  -> si B seule ~ combo et > A, la bascule 'vwap_reclaim only' se défend ; "
          "si combo > A et > B, les garder toutes deux.", flush=True)


if __name__ == '__main__':
    main()
