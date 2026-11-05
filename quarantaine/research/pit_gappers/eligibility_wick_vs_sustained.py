#!/usr/bin/env python3
"""Gap « en mèche » vs « soutenu » : les entrées qu'ADRX incarne valent-elles le coup ?

Contexte (21/10) : le backtest/bt.LIVE mesure le gap sur le HOD (high) -> il prend des
gappers « en mèche » (high ≥5% mais prix soutenu <5%, ex. ADRX) que le scanner LIVE
(IBKR TOP_PERC_GAIN, %-change courant) ne voit jamais. Question : ces entrées-mèche
rapportent-elles ? Si pire -> le filtre live est bon. Si mieux/égal -> on rate des trades.

Méthode : on prend TOUTES les entrées de bt.LIVE (HOD-based), et pour chacune on
classe selon le gap max atteint sur le CLOSE (prix soutenu) AVANT l'entrée :
  - « soutenu »  : max_close_gap >= 5%  (le live l'aurait probablement vu éligible)
  - « mèche »    : max_close_gap <  5%  (HOD ≥5% uniquement -> live l'a raté)
Puis on compare l'expectancy des deux groupes (FULL + OOS).
"""
import os, sys
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
from research.live_lab import backtest as bt
from research.pit_gappers.exit_trail_vs_eod import load_pit_groups

SPLIT = '2026-05-01'
SUSTAIN = 5.0   # seuil de gap "soutenu" sur le close (= plancher du scanner live)


def main():
    print("Chargement des groupes pit_gappers…")
    groups, dates = load_pit_groups()
    gmap = {(g['tk'], g['date']): g for g in groups}

    t = bt.simulate(groups, dict(bt.LIVE), slip=True)
    print(f"{len(t)} entrées bt.LIVE (HOD-based) sur {len(dates)} séances.\n")

    # classe chaque entrée : gap max sur le CLOSE avant la minute d'entrée
    kinds = []
    for _, r in t.iterrows():
        g = gmap.get((r.ticker, r.date))
        if g is None:
            kinds.append('?'); continue
        mins, c, pc = g['mins'], g['c'], g['pc']
        before = mins < r.entry_min
        if not before.any():
            kinds.append('?'); continue
        max_close_gap = ((np.maximum.accumulate(c[before]) - pc) / pc * 100).max()
        kinds.append('soutenu' if max_close_gap >= SUSTAIN else 'mèche')
    t = t.assign(kind=kinds)

    def rep(df, title):
        print(f"[{title}]")
        for k in ['soutenu', 'mèche']:
            s = bt.stat(df[df.kind == k].pnl.to_numpy())
            print(f"  {k:<8} {bt.fmt(s)}")
        print()

    rep(t, 'FULL')
    rep(t[t.date >= SPLIT], 'TEST OOS (≥'+SPLIT+')')

    # part des entrées "mèche" (celles que le live rate)
    share = (t.kind == 'mèche').mean() * 100
    print(f"Part des entrées « mèche » (que le scanner live raterait) : {share:.0f}%")


if __name__ == '__main__':
    main()
