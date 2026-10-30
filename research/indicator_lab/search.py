#!/usr/bin/env python3
"""Recherche par GRILLE sur les entrées par indicateurs : chaque archétype × bande de gap ×
fenêtre horaire × seuil rvol × mode de sortie. Évalue avec la MÊME discipline que live_lab :
OOS (2e moitié), exp>0 sur les deux moitiés, non-fragile (e_trim), n>=N_MIN. Classe par CPTE.

⚠️ live only, petit n (~23 séances) + grille large => hypothèses à surveiller, PAS à déployer.
Sortie : results/indicator_search_results.csv + robustes affichés. Lancer en background."""
import os, sys, itertools
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(HERE))))
from research.live_lab import backtest as bt
from . import engine as E
from . import signals as S

# Univers = freq-filtré (latepm>=0.20), TOUS GAPS. 'all' = aucune bande (ton intention) ;
# les splits servent de diagnostic pour voir si une zone de gap porte l'edge.
GAPS = [('all', (-100, 9999)), ('0-50', (0, 50)), ('50+', (50, 9999))]
WINS = {'journée': (570, 955), 'open-1h': (570, 630), 'des-10h': (600, 955)}
RVOL = [1.0, 2.0, 3.0]
EXITS = {'eod': dict(exit_mode='eod'),
         'trail10/2': dict(exit_mode='trail', activate_pct=0.10, trail_pct=0.02)}
N_MIN = 15          # univers freq-filtré = plus petit ; n plus bas toléré (caveat assumé)


def main():
    names = sys.argv[1:] or list(S.REGISTRY)      # sous-ensemble d'archétypes en argument (sinon tous)
    tag = '_' + '_'.join(names) if sys.argv[1:] else ''
    groups, dates = bt.load_groups()
    groups = E.liquid_groups(groups)              # univers freq-filtré = titres tradables live
    split = bt.oos_split(dates)
    print(f"{len(dates)} séances, OOS≥{split}. UNIVERS FREQ-FILTRÉ = {len(groups)} ticker-jours. "
          f"Archétypes={len(names)} × gap{len(GAPS)} × win{len(WINS)} × rvol{len(RVOL)} × exit{len(EXITS)} "
          f"= {len(names)*len(GAPS)*len(WINS)*len(RVOL)*len(EXITS)} combos.\n", flush=True)
    rows = []
    for name in names:
        for (gl, (gmin, gmax)), (wl, (ws, we)), rv, (el, ex) in itertools.product(
                GAPS, WINS.items(), RVOL, EXITS.items()):
            P = dict(gap_min=gmin, gap_max=gmax, entry_start=ws, entry_end=we, rvol_min=rv, **ex)
            df = E.simulate(groups, name, P)
            r = E.evaluate(df, dates, split, stop_pct=0.10)
            if not r or r['n'] < N_MIN:
                continue
            # e_trim RETIRÉ du garde dur (retirer 3 trades écrase un petit n = pas révélateur) ;
            # on le garde en COLONNE pour info. Garde = exp>0 2 moitiés + OOS>0 + t>=2 + n_te.
            robust = (r['e_h1'] > 0 and r['e_h2'] > 0 and r['e_te'] > 0
                      and r['t'] >= 2.0 and r['n_te'] >= 8)
            rows.append(dict(archetype=name, gap=gl, heure=wl, rvol=rv, exit=el,
                             robust=robust, **r))
        print(f"  {name} terminé ({len(rows)} lignes cumulées)", flush=True)
    d = pd.DataFrame(rows)
    out = os.path.join(HERE, 'results', f'indicator_search{tag}_results.csv')
    d.to_csv(out, index=False)
    cols = ['archetype', 'gap', 'heure', 'rvol', 'exit', 'n', 'trj', 'exp', 't', 'win',
            'pf', 'e_te', 'e_trim', 'maxDD', 'cpte', 'cpte_ann', 'cpte_oos_ann']
    print(f"\n{len(d)} combos n>={N_MIN}. {int(d.robust.sum())} ROBUSTES.", flush=True)
    rob = d[d.robust].sort_values('cpte', ascending=False)
    if len(rob):
        print("\n########## ROBUSTES (par CPTE) ##########")
        print(rob.head(20).to_string(index=False, columns=[c for c in cols if c in rob]), flush=True)
    else:
        print("\nAUCUN combo robuste — les entrées par indicateurs n'ont pas d'edge à ces réglages.", flush=True)
        print("TOP 10 par exp/tr (même négatifs) pour voir ce qui s'en rapproche :")
        print(d.sort_values('exp', ascending=False).head(10).to_string(
            index=False, columns=[c for c in cols if c in d]), flush=True)
    print(f"\nCSV: {out}", flush=True)


if __name__ == '__main__':
    main()
