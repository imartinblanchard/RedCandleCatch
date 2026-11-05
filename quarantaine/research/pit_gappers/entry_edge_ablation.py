#!/usr/bin/env python3
"""Attaque de l'edge d'ENTRÉE v3 : ablation des filtres sur le gros dataset pit (OOS).

Constat (19-21/10) : la config v3 (repli 8 + capit 1.3 + dvol 300K + run-up 2 + gap-open 1,
gap 5-10, hold-EOD) montre ~0 edge sur pit (307 tr, t≈0), malgré +2,2%/tr sur 15 j live.
Ici on dissèque : on part de bt.LIVE et on RETIRE / fait VARIER chaque filtre un à un pour
voir lequel aide, lequel tue, et si une config plus simple/différente fait mieux en OOS.

Moteur live exact (bt.simulate + bt.LIVE). Métrique = expectancy/trade (exp) et t-stat,
FULL + TEST OOS (≥2026-05-01). Sortie inchangée (hold-EOD) pour isoler l'entrée.
"""
import os, sys
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
from research.live_lab import backtest as bt
from research.pit_gappers.exit_trail_vs_eod import load_pit_groups

SPLIT = '2026-05-01'

# (label, overrides vs bt.LIVE)
VARIANTS = [
    ('v3 LIVE (baseline)',       {}),
    # — retirer chaque filtre anti-couteau un par un —
    ('sans capitulation',        dict(capit_ratio=-1)),
    ('sans dvol-repli',          dict(pullback_dvol_min=0)),
    ('sans run-up RTH',          dict(runup_min=0)),
    ('sans gap-open',            dict(gap_open_min=None)),
    ('sans AUCUN filtre a-c',    dict(capit_ratio=-1, pullback_dvol_min=0, runup_min=0, gap_open_min=None)),
    # — sweep du repli —
    ('repli 4%',                 dict(retrace_pct=0.04)),
    ('repli 5%',                 dict(retrace_pct=0.05)),
    ('repli 6%',                 dict(retrace_pct=0.06)),
    ('repli 10%',                dict(retrace_pct=0.10)),
    ('repli 12%',                dict(retrace_pct=0.12)),
    ('repli 15%',                dict(retrace_pct=0.15)),
    # — sweep capitulation —
    ('capit 1.0',                dict(capit_ratio=1.0)),
    ('capit 1.6',                dict(capit_ratio=1.6)),
    ('capit 2.0',                dict(capit_ratio=2.0)),
    # — sweep dvol —
    ('dvol 100K',                dict(pullback_dvol_min=100_000)),
    ('dvol 500K',                dict(pullback_dvol_min=500_000)),
    # — bande de gap —
    ('gap 10-20',                dict(gap_min=10.0, gap_max=20.0)),
    ('gap 5-20',                 dict(gap_min=5.0, gap_max=20.0)),
    ('gap 5-50',                 dict(gap_min=5.0, gap_max=50.0)),
    # — run-up plus strict —
    ('run-up 5%',                dict(runup_min=5)),
    # — require green (rebond confirmé) —
    ('bougie verte',             dict(require_green=True)),
]


def row(t, lo=None):
    a = (t if lo is None else t[t.date >= lo]).pnl.to_numpy()
    s = bt.stat(a)
    return s


def main():
    print("Chargement des groupes pit_gappers…")
    groups, dates = load_pit_groups()
    print(f"{len(groups)} ticker-jours, {len(dates)} séances, split OOS ≥ {SPLIT}\n")

    print(f"{'VARIANTE':<24} | {'FULL  n   exp     t    pf':<30} | {'OOS   n   exp     t':<24}")
    print("-" * 86)
    for label, upd in VARIANTS:
        P = dict(bt.LIVE); P.update(upd)
        t = bt.simulate(groups, P, slip=True)
        f = row(t); o = row(t, SPLIT)
        print(f"{label:<24} | n={f['n']:>4} {f['exp']:>+5.2f}% t={f['t']:>+5.2f} pf={f['pf']:>4.2f} | "
              f"n={o['n']:>4} {o['exp']:>+5.2f}% t={o['t']:>+5.2f}")


if __name__ == '__main__':
    main()
