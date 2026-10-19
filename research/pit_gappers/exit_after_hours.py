#!/usr/bin/env python3
"""Tenir APRÈS 15:55 (after-hours same-day) : heure de sortie fixe vs trailing stop.

Question Martin (19/10) : au lieu de sortir forcé à 15:55, et si on gardait la
position dans l'after-hours (jusqu'à 20:00) ? Et dans cette tranche, mieux avec
un trailing stop ou une heure de sortie FIXE ?

Les bars pit vont jusqu'à 19:59 -> testable sur le GROS dataset (165 séances).
Moteur live exact (live_lab.backtest), entrée v3 identique, seul l'horizon/la
règle de sortie change. Le stop -10% tourne dans tous les cas.

⚠️ L'after-hours a des spreads larges + bougies éparses : le modèle de slippage
(0,015/prix) et la détection de stop bougie-par-bougie SOUS-ESTIMENT le coût réel.
Lire les chiffres AH comme une BORNE SUPÉRIEURE (encore plus qu'en RTH).
"""
import os, sys
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
from research.live_lab import backtest as bt
from research.pit_gappers.exit_trail_vs_eod import load_pit_groups, seg

SPLIT = '2026-05-01'

# (label, eod_cutoff_min, exit_mode)  — eod = minute de sortie forcée (955=15:55 … 1200=20:00)
VARIANTS = [
    ('15:55 FIXE (actuel)',  955,  'eod'),
    ('16:00 FIXE (close)',   960,  'eod'),
    ('16:30 FIXE',           990,  'eod'),
    ('17:00 FIXE',          1020,  'eod'),
    ('18:00 FIXE',          1080,  'eod'),
    ('20:00 FIXE (fin AH)', 1200,  'eod'),
    ('trail 10/2 →15:55',    955,  'trail'),
    ('trail 10/2 →20:00',   1200,  'trail'),
]


def main():
    print("Chargement des groupes pit_gappers…")
    groups, dates = load_pit_groups()
    print(f"{len(groups)} ticker-jours, {len(dates)} séances ({dates[0]} → {dates[-1]}), split OOS ≥ {SPLIT}")
    print("⚠️  Chiffres after-hours = borne SUPÉRIEURE (spreads AH non modélisés).\n")

    print(f"{'SORTIE':<22} | {'FULL':^38} | {'TEST OOS (≥'+SPLIT+')':^38}")
    print("-" * 104)
    base_full = base_oos = None
    for label, cutoff, mode in VARIANTS:
        P = dict(bt.LIVE, exit_mode=mode, eod=cutoff, activate_pct=0.10, trail_pct=0.02)
        t = bt.simulate(groups, P, slip=True)
        sf = bt.stat(seg(t, None, None).pnl.to_numpy())
        so = bt.stat(seg(t, SPLIT, None).pnl.to_numpy())
        if base_full is None:            # ligne 1 = 15:55 actuel = référence
            base_full, base_oos = sf['exp'], so['exp']
        df = sf['exp'] - base_full; do = so['exp'] - base_oos
        print(f"{label:<22} | n={sf['n']:>4} exp={sf['exp']:>+5.2f}% t={sf['t']:>+5.2f} "
              f"pf={sf['pf']:>4.2f} Δ={df:>+5.2f} | "
              f"n={so['n']:>4} exp={so['exp']:>+5.2f}% t={so['t']:>+5.2f} pf={so['pf']:>4.2f} Δ={do:>+5.2f}")

    print("\nΔ = écart d'expectancy/trade vs la sortie 15:55 actuelle (même entrée).")


if __name__ == '__main__':
    main()
