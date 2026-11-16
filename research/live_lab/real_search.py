#!/usr/bin/env python3
"""Recherche LARGE sur l'univers COMPLET des gappers 3-500% (bars-*.parquet = universe.json,
TOUS les gappers, pas seulement ceux qu'on trade). Balaie archétype × bande de gap × fenêtre
d'entrée × sortie × stop × seuil PM-liq, et classe par ROBUSTESSE (OOS + 2 moitiés + t) puis CPTE.
But (Martin) : juger les stratégies sur l'univers large PUIS choisir le déploiement avec les bons
filtres (gap, fréquence PM). Les FILTRES (gap band, PM-liq) sont des DIMENSIONS de la recherche.

⚠️ petit n (45 séances) + milliers de combos = FAUX POSITIFS massifs : lire t-stat / 2 moitiés /
OOS, JAMAIS un gagnant isolé. Réutilise le moteur price_lab (engine) — aucune logique dupliquée.
Sortie : research/live_lab/results/real_search-results.csv

Usage : python -m research.live_lab.real_search
"""
import os, sys, itertools
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
from research.live_lab import backtest as bt
from research.price_lab import engine as E, signals as S

PM_LO, PM_HI = 480, 570          # 8:00 -> 9:30 ET (fréquence PM)

ARCHES = list(S.REGISTRY)
APARAMS = {'rsi_bounce': dict(rsi_lo=20), 'rsi_divergence': dict(div_win=20),
           'williams_bounce': dict(wr_lo=-80), 'orb_breakout': dict(orb_win=15)}
GAPS = [('3-10', 3, 10), ('5-10', 5, 10), ('10-20', 10, 20), ('3-20', 3, 20), ('all', -100, 9999)]
WINS = [('9:30>midi', 570, 720), ('9:30>15:55', 570, 955)]
EXITS = {'tp15': dict(exit_mode='tp', tp_pct=0.15), 'tp20': dict(exit_mode='tp', tp_pct=0.20),
         'trail10/5': dict(exit_mode='trail', activate_pct=0.10, trail_pct=0.05), 'eod': dict(exit_mode='eod')}
STOPS = [0.08, 0.10]
THRS = [0.20, 0.35]
N_MIN = 30
OUT = os.path.join(HERE, 'results', 'real_search-results.csv')


def main():
    groups, dates = bt.load_groups()          # univers LARGE 3-500 (bars-*.parquet = universe.json)
    ex = E.excluded_set()
    groups = [g for g in groups if (g['tk'], g['date']) not in ex]
    # pm_frac précalculé une fois par ticker-jour (filtrage seuil = cheap ensuite)
    for g in groups:
        g['_pm'] = sum(1 for mn, vv in zip(g['mins'], g['v']) if PM_LO <= mn < PM_HI and vv > 0) / (PM_HI - PM_LO)
    split = bt.oos_split(dates)
    ncfg = len(ARCHES) * len(GAPS) * len(WINS) * len(EXITS) * len(STOPS) * len(THRS)
    print(f"univers RÉEL : {len(groups)} ticker-jours · {len(dates)} séances · OOS {split} · {ncfg} configs", flush=True)

    rows = []
    k = 0
    for thr in THRS:
        liq = [g for g in groups if g['_pm'] >= thr]
        for name in ARCHES:
            ap = APARAMS.get(name, {})
            for (gl, gmin, gmax), (wl, ws, we) in itertools.product(GAPS, WINS):
                for stp in STOPS:
                    for exl, ex_ in EXITS.items():
                        k += 1
                        P = dict(gap_min=gmin, gap_max=gmax, entry_start=ws, entry_end=we, stop_pct=stp, **ap, **ex_)
                        df = E.simulate(liq, name, P)
                        if len(df) < N_MIN:
                            continue
                        r = E.evaluate(df, dates, split, stop_pct=stp)
                        if not r:
                            continue
                        r['robust'] = bool(r['e_h1'] > 0 and r['e_h2'] > 0 and r['t'] >= 2 and r['cpte_oos'] > 0)
                        rows.append(dict(archetype=name, gap=gl, heure=wl, exit=f'{exl}/s{int(stp*100)}', pm=thr,
                                         **{c: r[c] for c in ['n', 'trj', 'exp', 't', 'win', 'entry_med',
                                            'cpte', 'cpte_oos', 'e_h1', 'e_h2', 'maxDD', 'robust']}))
                if k % 200 < len(EXITS) * len(STOPS):
                    print(f"\r{k}/{ncfg}", end='', flush=True)
    print()
    res = pd.DataFrame(rows)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    res.to_csv(OUT, index=False)
    cols = ['archetype', 'gap', 'heure', 'exit', 'pm', 'n', 'trj', 'exp', 't', 'win', 'cpte', 'cpte_oos', 'e_h1', 'e_h2', 'maxDD']
    print(f"-> {OUT} ({len(res)} configs n>={N_MIN})\n")
    rob = res[res.robust].sort_values('cpte', ascending=False)
    print(f"=== ROBUSTES (OOS+ , 2 moitiés+, t>=2) : {len(rob)} ===")
    print(rob[cols].head(20).to_string(index=False) if len(rob) else "  AUCUNE config robuste sur l'univers réel.")
    print("\n=== TOP 15 par CPTE (robuste ou non — lire t/OOS) ===")
    print(res.sort_values('cpte', ascending=False).head(15)[cols].to_string(index=False))


if __name__ == '__main__':
    main()
