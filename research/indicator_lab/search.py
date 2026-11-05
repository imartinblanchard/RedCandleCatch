#!/usr/bin/env python3
"""Recherche COMPLÈTE famille INDICATEURS, lancée chaque soir de bourse. Balaie LARGEMENT, en
combinaison : archétype × bande de gap × seuil rvol (rvol_gate, le vrai levier) × fenêtre d'entrée
fine (début/fin) × SORTIE (eod/trail/tp, plusieurs réglages). Univers freq-filtré (titres tradables
live). Optimisé : entrées détectées UNE fois par config d'entrée, sorties balayées par-dessus (gratuit).

Classé par CPTE (capital final, ce qui compte) + robustesse (t-stat, e_trim non-fragile). OOS = suivi.
⚠️ petit n (~25 séances) + bcp de combos = FAUX POSITIFS : lire la PERSISTANCE dans le temps + le live.
Sortie : results/indicator_search_results.csv. Argument optionnel = sous-ensemble d'archétypes."""
import os, sys, itertools
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(HERE))))
from research.live_lab import backtest as bt
from . import engine as E
from . import signals as S

GAPS = [('all', (-100, 9999)), ('0-50', (0, 50)), ('50+', (50, 9999))]
RVOL = [0, 5, 10, 20, 30, 60, 100]                          # rvol_gate : le levier de qualité (incl. 60+)
PM_THRS = [0.20, 0.30, 0.40, 0.50, 0.60]                    # seuil univers PM-liquidité = DIMENSION (04/11,
                                                            # demande Martin) : plus haut = univers + propre
STARTS = {'9:30': 570, '9:45': 585, '10:00': 600}
ENDS = {'10:30': 630, 'midi': 720, '15:55': 955}
EXITS = {'eod': dict(exit_mode='eod'),
         'trail10/2': dict(exit_mode='trail', activate_pct=0.10, trail_pct=0.02),
         'trail5/2': dict(exit_mode='trail', activate_pct=0.05, trail_pct=0.02),
         'trail10/5': dict(exit_mode='trail', activate_pct=0.10, trail_pct=0.05),
         'tp20': dict(exit_mode='tp', tp_pct=0.20),
         'tp30': dict(exit_mode='tp', tp_pct=0.30)}
N_MIN = 15


def main():
    names = sys.argv[1:] or list(S.REGISTRY)
    tag = '_' + '_'.join(names) if sys.argv[1:] else ''
    groups, dates = bt.load_groups()
    UNIV = {thr: E.liquid_groups(groups, thr=thr) for thr in PM_THRS}    # univers par seuil PM (DIMENSION)
    split = bt.oos_split(dates)
    wins = [(f"{sl}>{el}", ss, ee) for (sl, ss), (el, ee) in itertools.product(STARTS.items(), ENDS.items()) if ss < ee]
    n_entry = len(names) * len(PM_THRS) * len(GAPS) * len(RVOL) * len(wins)
    print(f"{len(dates)} séances. Seuils PM {[f'{t:.0%}' for t in PM_THRS]} "
          f"(tj: {[len(UNIV[t]) for t in PM_THRS]}). {n_entry} configs d'ENTRÉE "
          f"× {len(EXITS)} sorties = {n_entry*len(EXITS)} combos.\n", flush=True)
    rows = []; k = 0
    for name in names:
        for thr in PM_THRS:
            liq = UNIV[thr]
            for (gl, (gmin, gmax)), rv, (wl, ws, we) in itertools.product(GAPS, RVOL, wins):
                k += 1
                ents = E.entries(liq, name, dict(gap_min=gmin, gap_max=gmax, entry_start=ws,
                                                 entry_end=we, rvol_gate=float(rv)))
                if len(ents) < N_MIN:
                    continue
                for el, ex in EXITS.items():
                    df = E.trades_from(ents, ex)
                    r = E.evaluate(df, dates, split, stop_pct=0.10)
                    if not r or r['n'] < N_MIN:
                        continue
                    robust = (r['t'] >= 2.0 and r['e_trim'] > 0 and r['e_h1'] > 0 and r['e_h2'] > 0)
                    rows.append(dict(archetype=name, gap=gl, rvol=rv, heure=wl, exit=el, pm_thr=thr, robust=robust, **r))
        print(f"  {name} terminé ({k}/{n_entry} entrées, {len(rows)} lignes)", flush=True)
    d = pd.DataFrame(rows)
    out = os.path.join(HERE, 'results', f'indicator_search{tag}_results.csv')
    d.to_csv(out, index=False)
    cols = ['archetype', 'gap', 'rvol', 'heure', 'exit', 'pm_thr', 'n', 'trj', 'exp', 't', 'e_trim',
            'win', 'pf', 'maxDD', 'cpte', 'cpte_oos']
    print(f"\n{len(d)} combos n>={N_MIN}. {int(d.robust.sum()) if len(d) else 0} robustes (t>=2, e_trim>0, 2 moitiés>0).")
    base = d[d.robust] if (len(d) and d.robust.any()) else d
    if len(base):
        print("\n########## TOP 25 par CPTE (robustes) ##########")
        print(base.sort_values('cpte', ascending=False).head(25).to_string(
            index=False, columns=[c for c in cols if c in base]), flush=True)
    print(f"\nCSV: {out}", flush=True)


if __name__ == '__main__':
    main()
