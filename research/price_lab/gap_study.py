#!/usr/bin/env python3
"""Étude DÉDIÉE : y a-t-il un edge dans les GROS gaps (>=20%, en particulier >=30%) ?
Balaie les BANDES DE GAP HAUTES × archétypes × fenêtre × sortie, sur l'univers actuel
(PM-liquidité + exclusions split/acquisition). Réutilise l'engine price_lab (0 volume).
Témoin : bande 10-20. Classé par CPTE compte (FULL) + robustesse (t, OOS, 2 moitiés).
Sortie : results/gap_study_results.csv. Petit n sur les bandes hautes : lire t/OOS, pas un gagnant isolé."""
import os, sys, itertools
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
from research.live_lab import backtest as bt
from research.price_lab import engine as E, signals as S

GAPS = [('10-20', (10, 20)), ('20-30', (20, 30)), ('30-50', (30, 50)),
        ('30-100', (30, 100)), ('50-100', (50, 100)), ('>=30', (30, 9999))]
WINS = [('9:30>15:55', 570, 955), ('10:00>15:55', 600, 955)]
EXITS = {'tp15': dict(exit_mode='tp', tp_pct=0.15), 'tp20': dict(exit_mode='tp', tp_pct=0.20),
         'tp30': dict(exit_mode='tp', tp_pct=0.30),
         'trail10/5': dict(exit_mode='trail', activate_pct=0.10, trail_pct=0.05),
         'eod': dict(exit_mode='eod')}
STOP = 0.10
N_MIN = 15
OUT = os.path.join(HERE, 'results', 'gap_study_results.csv')


def main():
    groups, dates = bt.load_groups()
    liq = E.liquid_groups(groups, thr=0.20)
    split = bt.oos_split(dates)
    names = sys.argv[1:] or list(S.REGISTRY)
    rows = []
    ncfg = len(names) * len(GAPS) * len(WINS) * len(EXITS)
    print(f'{len(liq)} ticker-jours · {len(dates)} séances · OOS depuis {split} · {ncfg} configs')
    k = 0
    for name in names:
        for (gl, (gmin, gmax)), (wl, ws, we) in itertools.product(GAPS, WINS):
            P = dict(gap_min=gmin, gap_max=gmax, entry_start=ws, entry_end=we, stop_pct=STOP)
            ents = E.entries(liq, name, {**E.DEFAULTS, **P})
            for exl, ex in EXITS.items():
                k += 1
                df = E.trades_from(ents, {**E.DEFAULTS, **P, **ex})
                if len(df) < N_MIN:
                    continue
                r = E.evaluate(df, dates, split, stop_pct=STOP)
                if not r:
                    continue
                rows.append(dict(archetype=name, gap=gl, heure=wl, exit=f'{exl}/s10', **r))
            print(f'\r{k}/{ncfg}', end='', flush=True)
    print()
    res = pd.DataFrame(rows)
    res.to_csv(OUT, index=False)
    print(f'-> {OUT} ({len(res)} configs n>={N_MIN})\n')

    # robustesse : OOS positif + 2 moitiés positives + t>=2
    res['robust'] = (res.cpte_oos > 0) & (res.e_h1 > 0) & (res.e_h2 > 0) & (res.t >= 2)
    cols = ['archetype', 'gap', 'heure', 'exit', 'n', 'trj', 'exp', 't', 'win',
            'entry_med', 'cpte', 'cpte_oos', 'e_h1', 'e_h2', 'maxDD', 'robust']
    hi = res[res.gap != '10-20']
    print('=== TOP 15 bandes HAUTES (>=20%), classé CPTE ===')
    print(hi.sort_values('cpte', ascending=False).head(15)[cols].to_string(index=False))
    print('\n=== bandes HAUTES ROBUSTES (OOS+ , 2 moitiés+, t>=2) ===')
    rob = hi[hi.robust].sort_values('cpte', ascending=False)
    print(rob[cols].to_string(index=False) if len(rob) else '  AUCUNE config robuste sur les bandes hautes.')
    print('\n=== témoin 10-20, TOP 5 CPTE ===')
    print(res[res.gap == '10-20'].sort_values('cpte', ascending=False).head(5)[cols].to_string(index=False))


if __name__ == '__main__':
    main()
