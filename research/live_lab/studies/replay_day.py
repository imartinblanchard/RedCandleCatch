#!/usr/bin/env python3
"""Rejoue la CONFIG LIVE actuelle (liq-eod + vwap_reclaim, filtre PM-liq 0.20) sur UNE séance
collectée, pour voir les trades que le bot AURAIT pris. PM-liquidité calculée EN LIGNE depuis les
bougies (comme le terminator), pas via le CSV (qui peut ne pas couvrir la date).
⚠️ bougies POST-CLÔTURE (volume complet) -> BORNE SUPÉRIEURE : le live (volume temps réel) en prend
MOINS, surtout vwap (rvol≥60 sensible). Usage : python -m research.live_lab.studies.replay_day 2026-11-02"""
import os, sys
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(HERE))))
from research.live_lab import backtest as bt
from research.indicator_lab import engine as E

TRAIL = dict(exit_mode='trail', activate_pct=0.10, trail_pct=0.02)
LIQEOD = dict(gap_min=5, gap_max=50, entry_start=600, retrace_pct=0.12, capit_ratio=-1,
              hod_in_rth=True, exit_mode='eod')


def pm_liq(g):                       # fraction des minutes 8:00-9:30 (480-570) avec un trade
    m = g['mins']; v = g['v']; mask = (m >= 480) & (m < 570)
    return (v[mask] > 0).sum() / 90.0


def main():
    date = sys.argv[1] if len(sys.argv) > 1 else '2026-11-02'
    groups, _ = bt.load_groups()
    gd = [g for g in groups if g['date'] == date]
    if not gd:
        print(f"❌ pas de données pour {date} (bars-{date}.parquet collecté ?)"); return
    gl = [g for g in gd if pm_liq(g) >= 0.20]
    print(f"Séance {date} : {len(gd)} ticker-jours collectés, {len(gl)} passent le filtre PM-liq (>=20%).\n")

    tl = bt.simulate(gl, {**bt.LIVE, **LIQEOD}, slip=True)
    tv = E.simulate(gl, 'vwap_reclaim', dict(entry_start=570, entry_end=630, rvol_gate=60.0, **TRAIL))

    def show(name, t, cols):
        print(f"── {name} : {len(t)} trade(s) ──")
        if len(t):
            print(t[cols].to_string(index=False))
            print(f"   total {t.pnl.sum():+.2f}%  (exp/tr {t.pnl.mean():+.2f}%, "
                  f"win {(t.pnl>0).mean()*100:.0f}%)")
        print()
    show("TRACK 1  liq-eod (repli)", tl, ['ticker', 'entry_time', 'entry', 'gap', 'drop', 'pnl'])
    show("TRACK 2  vwap_reclaim rvol>=60", tv, ['ticker', 'entry_time', 'entry', 'gap', 'rvol', 'pnl'])

    n = len(tl) + len(tv); tot = (tl.pnl.sum() if len(tl) else 0) + (tv.pnl.sum() if len(tv) else 0)
    print(f"TOTAL {date} : {n} trade(s), P&L brut cumulé {tot:+.2f}% (1 action, borne SUP vs live réel).")
    print("⚠️ Replay post-clôture = volume COMPLET -> le bot live en aurait pris MOINS (volume temps réel).")


if __name__ == '__main__':
    main()
