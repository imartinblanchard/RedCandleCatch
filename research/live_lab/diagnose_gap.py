#!/usr/bin/env python3
"""Pourquoi l'écart backtest v3 (+2%) vs résultats réels (négatif) ? Décomposition.

Pour les séances v3-era (gap 5-10, hold-EOD), on compare le JOURNAL réel au BACKTEST
(bt.LIVE) sur les MÊMES dates. Trois buckets :
  - COMMUN : ticker pris par les deux -> écart de P&L = slippage de FILL (entrée/sortie).
  - BACKTEST-ONLY : trades que le backtest prend mais que le bot a ratés (temps réel) -> effet SÉLECTION.
  - JOURNAL-ONLY : trades pris en réel mais pas par le backtest (rare).
Dit si le gap vient des ORDRES (fill) ou de la SÉLECTION de trades.
LIVE data uniquement.
"""
import os, sys
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
from research.live_lab import backtest as bt

J = 'data/computed/redcandlecatch-journal.csv'


def main():
    j = pd.read_csv(J)
    j = j[(j['mode'] == 'LIVE') & (j['date'] >= '2026-10-07') & (j['gap'] <= 10)].copy()  # v3-era (gap 5-10)
    jdates = sorted(j.date.unique())
    print(f"Journal v3-era : {len(j)} trades réels sur {len(jdates)} séances ({jdates[0]}..{jdates[-1]})")
    print(f"  P&L réel moyen : {j.pnl_pct.mean():+.2f}%/tr  (somme {j.pnl_pct.sum():+.1f}%)\n")

    groups, dates = bt.load_groups()
    # backtest v3 restreint aux séances où le bot a réellement tradé
    g2 = [g for g in groups if g['date'] in set(jdates)]
    bt_t = bt.simulate(g2, dict(bt.LIVE), slip=True)
    print(f"Backtest v3 sur ces MÊMES {len(jdates)} séances : {len(bt_t)} trades, exp {bt_t.pnl.mean():+.2f}%/tr\n")

    jk = j.set_index(['date', 'ticker'])
    bk = bt_t.set_index(['date', 'ticker'])
    common = sorted(set(jk.index) & set(bk.index))
    bt_only = sorted(set(bk.index) - set(jk.index))
    j_only = sorted(set(jk.index) - set(bk.index))

    print("=== COMMUN (pris par les DEUX) -> mesure le slippage de FILL ===")
    if common:
        rows = []
        for key in common:
            jr = jk.loc[key]; br = bk.loc[key]
            jr = jr.iloc[0] if isinstance(jr, pd.DataFrame) else jr
            br = br.iloc[0] if isinstance(br, pd.DataFrame) else br
            rows.append((key[1], key[0], float(br['entry']), float(jr['entry']),
                         float(br['pnl']), float(jr['pnl_pct'])))
        d = pd.DataFrame(rows, columns=['ticker', 'date', 'bt_entry', 'real_entry', 'bt_pnl', 'real_pnl'])
        d['entry_slip%'] = (d.real_entry - d.bt_entry) / d.bt_entry * 100
        d['pnl_gap'] = d.real_pnl - d.bt_pnl
        print(d.to_string(index=False))
        print(f"\n  slippage entrée moyen : {d['entry_slip%'].mean():+.2f}%  | écart P&L moyen (réel−bt) : {d.pnl_gap.mean():+.2f}%/tr")
    else:
        print("  (aucun trade commun)")

    print(f"\n=== BACKTEST-ONLY (backtest prend, bot RATE) -> effet SÉLECTION : {len(bt_only)} trades ===")
    if bt_only:
        bo = bk.loc[bt_only][['entry_time', 'entry', 'gap', 'pnl']].reset_index()
        print(bo.to_string(index=False))
        print(f"  P&L moyen de ces trades ratés : {bo.pnl.mean():+.2f}%/tr (somme {bo.pnl.sum():+.1f}%)")

    print(f"\n=== JOURNAL-ONLY (bot prend, backtest NON) : {len(j_only)} ===")
    if j_only:
        jo = jk.loc[j_only][['entry_time', 'entry', 'gap', 'pnl_pct', 'reason']].reset_index()
        print(jo.to_string(index=False))

    print("\n=== VERDICT ===")
    print(f"  réel {j.pnl_pct.mean():+.2f}%/tr  vs  backtest(mêmes jours) {bt_t.pnl.mean():+.2f}%/tr")
    if common:
        print(f"  part FILL (trades communs, écart P&L) : {d.pnl_gap.mean():+.2f}%/tr")
    if bt_only:
        print(f"  part SÉLECTION (trades ratés) : {bo.pnl.mean():+.2f}%/tr sur {len(bt_only)} trades que le bot n'a pas pris")


if __name__ == '__main__':
    main()
