#!/usr/bin/env python3
"""ÉTAPE 6 (portée B) : générateur complet POINT-IN-TIME, par bande.

Pour chaque fichier `bands/band-<lo>-<hi>.parquet` (étape 4) :
  - univers = ses ticker-jours ; pour chacun, 1re entrée autorisée = son `band_arrival_min`.
  - on teste TOUS les combos de 1-2 briques (~24 briques) × fenêtre × liquidité × sortie × stop,
    exactement comme `strategy_gen`, MAIS entrée ≥ band_arrival (point-in-time), SANS re-gate de gap
    (le fichier de bande EST l'appartenance).
  - robustesse OOS + 2 moitiés + t ; on enregistre aussi open_pct/entry_med.

Crash-safe : checkpoint par bande (append CSV + done). Réutilise le prep caché de strategy_gen.
Sortie : research/live_lab/results/search_bands-results.csv (colonne `band`).

Usage : python -m research.live_lab.search_bands            (run complet)
        python -m research.live_lab.search_bands --calib     (1re bande puis stop, mesure le temps)
"""
import os, sys, time, glob, argparse
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
from research.live_lab import strategy_gen as sg
from research.live_lab import backtest as bt
from research.price_lab import engine as E

BANDS_DIR = os.path.join(HERE, 'bands')
OUT = os.path.join(HERE, 'results', 'search_bands-results.csv')
DONE = os.path.join(HERE, 'results', 'search_bands-done.txt')


def entries_pit(band_prepped, ci, cj, ws, we, liqkind, liqarg):
    """1re bougie passant prix/fenêtre/liquidité ET briques, À PARTIR de band_arrival (point-in-time).
    PAS de gate de gap (l'appartenance vient du fichier de bande). band_prepped = [(elem, amin)]."""
    out = []
    for e, amin in band_prepped:
        if liqkind == 'pm' and e['pm'] < liqarg:
            continue
        mask = e['prims'][ci] if cj is None else (e['prims'][ci] & e['prims'][cj])
        start = max(ws, amin)
        gate = ((e['mins'] >= start) & (e['mins'] <= we) & (e['c'] >= 3.0) & (e['c'] <= 20.0) & mask)
        if liqkind == 'entry':
            gate = gate & (e[liqarg[0]] >= liqarg[1])
        idx = np.argmax(gate)
        if gate[idx]:
            out.append((e, int(idx)))
    return out


def run_band(band_prepped, dates, split, bandlabel, cmb):
    rows = []
    for ci, cj in cmb:
        nm = sg.NAMES[ci] + ('' if cj is None else ' & ' + sg.NAMES[cj])
        for wl, ws, we in sg.WINS:
            for liql, lk, la in sg.LIQ:
                ents = entries_pit(band_prepped, ci, cj, ws, we, lk, la)
                for exl, stp, r in sg.eval_exits(ents, dates, split):
                    rows.append(dict(regle=nm, band=bandlabel, heure=wl, liq=liql,
                                     exit=f'{exl}/s{int(stp*100)}',
                                     **{c: r[c] for c in ['n', 'trj', 'exp', 't', 'win',
                                        'gain_moy', 'perte_moy', 'rr', 'open_pct', 'entry_med',
                                        'cpte', 'cpte_oos', 'e_h1', 'e_h2', 'maxDD', 'robust']}))
    return rows


def _done():
    return set(open(DONE).read().split()) if os.path.exists(DONE) else set()


def main(calib=False):
    groups, dates = bt.load_groups()
    ex = E.excluded_set()
    groups = [g for g in groups if (g['tk'], g['date']) not in ex]
    split = bt.oos_split(dates)
    cmb = sg.combos()
    print(f"univers {len(groups)} ticker-jours · {len(dates)} séances · OOS {split}", flush=True)
    prepped = sg.prep_cached(groups)
    idx = {(e['g']['tk'], e['g']['date']): e for e in prepped}

    band_files = sorted(glob.glob(os.path.join(BANDS_DIR, 'band-*.parquet')))
    done = _done()
    for bf in band_files:
        label = os.path.basename(bf)[len('band-'):-len('.parquet')]
        if label in done:
            print(f"[{label}] déjà fait -> skip", flush=True); continue
        bdf = pd.read_parquet(bf)
        band_prepped = [(idx[(t, d)], int(a)) for t, d, a in
                        zip(bdf.ticker, bdf.date, bdf.band_arrival_min) if (t, d) in idx]
        print(f"[{label}] {len(bdf)} titres-jours | couverts par prep {len(band_prepped)}", flush=True)
        if not band_prepped:
            with open(DONE, 'a') as f: f.write(label + '\n')
            continue
        t0 = time.time()
        rows = run_band(band_prepped, dates, split, label, cmb)
        pd.DataFrame(rows).to_csv(OUT, mode='a', header=not os.path.exists(OUT), index=False)
        with open(DONE, 'a') as f: f.write(label + '\n')
        print(f"[{label}] ✅ {len(rows)} lignes en {(time.time()-t0)/60:.1f} min -> checkpoint", flush=True)
        if calib:
            print("CALIB : stop après 1 bande.", flush=True); return
    print(f"\nTERMINÉ -> {OUT}", flush=True)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--calib', action='store_true')
    a = ap.parse_args()
    main(calib=a.calib)
