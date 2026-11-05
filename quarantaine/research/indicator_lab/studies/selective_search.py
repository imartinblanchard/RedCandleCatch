#!/usr/bin/env python3
"""Verrouille les conditions causales trouvées (studies/selectivity.py) comme VRAIES règles
d'entrée et re-valide avec tous les garde-fous : OOS, exp>0 sur les 2 moitiés, non-fragile,
CPTE full/OOS + annualisé. Univers = freq-filtré, tous gaps, 1re heure. Classé par STABILITÉ.

Trieurs : bb_breakout -> macd_hist_min ; vwap_reclaim -> rvol_gate ; + cap de gap (petits gaps
= meilleurs). ⚠️ live only, in-sample 23 j, sélection -> hypothèses. collected_live uniquement."""
import os, sys, itertools
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(HERE)))))
from research.live_lab import backtest as bt
from research.indicator_lab import engine as E

TRAIL = dict(exit_mode='trail', activate_pct=0.10, trail_pct=0.02)
EOD = dict(exit_mode='eod')
BASE = dict(entry_start=570, entry_end=630)             # 1re heure
GAPCAPS = [('g<=20', 20.0), ('g<=50', 50.0), ('g-all', 9999.0)]
# grilles de trieur par archétype (seuils causaux issus de selectivity.py)
GRID = {
    'bb_breakout':  ('macd_hist_min', [0.0, 0.02, 0.03]),
    'vwap_reclaim': ('rvol_gate', [1.0, 30.0, 60.0, 110.0]),
}
N_MIN = 20


def main():
    groups, dates = bt.load_groups()
    liq = E.liquid_groups(groups)
    split = bt.oos_split(dates)
    print(f"{len(dates)} séances, OOS≥{split}, univers freq-filtré={len(liq)} ticker-jours.\n", flush=True)
    rows = []
    for name, (knob, vals) in GRID.items():
        for (gl, gmax), kv, (el, ex) in itertools.product(GAPCAPS, vals, [('trail', TRAIL), ('eod', EOD)]):
            P = dict(BASE, gap_max=gmax, **{knob: kv}, **ex)
            df = E.simulate(liq, name, P)
            r = E.evaluate(df, dates, split, stop_pct=0.10)
            if not r or r['n'] < N_MIN:
                continue
            stable = (r['e_h1'] > 0 and r['e_h2'] > 0 and r['e_te'] > 0 and r['t'] >= 2.5
                      and r['maxDD'] > -8 and r['n_te'] >= 8)
            rows.append(dict(archetype=name, gap=gl, knob=f"{knob.split('_')[0]}>={kv:g}",
                             exit=el, stable=stable, **r))
    d = pd.DataFrame(rows)
    out = os.path.join(os.path.dirname(HERE), 'results', 'selective_search_results.csv')
    d.to_csv(out, index=False)
    cols = ['archetype', 'gap', 'knob', 'exit', 'n', 'trj', 'exp', 't', 'win', 'pf',
            'e_h1', 'e_h2', 'e_te', 'e_trim', 'maxDD', 'cpte', 'cpte_ann', 'cpte_oos_ann']
    print(f"{len(d)} combos n>={N_MIN}. {int(d.stable.sum())} STABLES "
          f"(exp>0 2 moitiés + OOS>0 + t>=2.5 + DD>-8%).\n", flush=True)
    # classement par stabilité : CPTE haut, DD bas, h1≈h2 régulier
    d['reg'] = (d.e_h1 - d.e_h2).abs()
    st = d[d.stable].sort_values(['cpte'], ascending=False)
    show = st if len(st) else d.sort_values('cpte', ascending=False)
    print(("STABLES" if len(st) else "AUCUN stable — top CPTE") + " (par CPTE) :")
    print(show.head(20).to_string(index=False, columns=cols), flush=True)
    print(f"\nLEGENDE: e_h1/e_h2=exp 1re/2e moitié (régularité) | e_te=exp OOS | e_trim=sans 3 meilleurs")
    print(f"  cpte=%compte 2% | cpte_ann/oos_ann=annualisé x252/j (COMPARER, pas prévoir)")
    print(f"CSV: {out}", flush=True)


if __name__ == '__main__':
    main()
