#!/usr/bin/env python3
"""ÉTAPE 4 du pipeline point-in-time : construit les fichiers de gappers PAR BANDE.

Pour chaque jour et chaque titre de `tradable-DATE.json` qui a des bougies dans `bars-DATE.parquet` :
  - gap par minute = (max-high-courant − prev_close)/prev_close  [high-based, comme le scanner live]
  - on ne regarde que les bougies À PARTIR de `added` (point-in-time : jamais avant qu'on l'ait vu)
  - pour CHAQUE bande qu'il atteint après `added`, on note la 1re minute où le gap y entre
    = `band_arrival`. Un titre peut donc apparaître dans plusieurs bandes (le gap bouge).

Sortie : research/live_lab/bands/band-<lo>-<hi>.parquet (tous jours agrégés), colonnes
  ticker, date, band, band_arrival_min, band_arrival_ts (timestamp COMPLET, non-ambigu).

Lecture seule sur les données ; n'écrit QUE dans research/live_lab/bands/. 11-16 exclu (partiel).
Usage : python -m research.live_lab.build_bands        (ou exécuter le fichier)
"""
import os, sys, json, glob
import numpy as np, pandas as pd

ROOT = os.getcwd()                                   # lancé depuis la racine du projet
COLLECTED = os.path.join(ROOT, 'data', 'collected_live')
COMPUTED = os.path.join(ROOT, 'data', 'computed')
OUTDIR = os.path.join(ROOT, 'research', 'live_lab', 'bands')
BANDS = [(3, 5), (5, 7), (7, 10), (10, 14), (14, 20),     # bandes BASSES (edge visé)
         (20, 30), (30, 50), (50, 100), (100, 500)]       # bandes HAUTES (vue complète 3-500)
EXCLUDE_DAYS = {'2026-11-16'}                         # capture partielle
MIN_BARS = 5                                         # titre ignoré si trop peu de bougies


def _mins(hhmm_series):
    s = hhmm_series.astype(str)
    return (s.str.slice(0, 2).astype(int) * 60 + s.str.slice(3, 5).astype(int)).to_numpy()


def _added_min(added):
    if not added or ':' not in str(added):
        return None
    h, m = str(added).split(':')[:2]
    return int(h) * 60 + int(m)


def build_day(day):
    barp = os.path.join(COLLECTED, f'bars-{day}.parquet')
    trp = os.path.join(COMPUTED, f'tradable-{day}.json')
    metap = os.path.join(COLLECTED, f'meta-{day}.json')
    if not (os.path.exists(barp) and os.path.exists(trp)):
        return []
    tradable = json.load(open(trp))
    meta = json.load(open(metap)) if os.path.exists(metap) else {}
    df = pd.read_parquet(barp)
    rows = []
    for tk, info in tradable.items():
        g = df[df.ticker == tk]
        if len(g) < MIN_BARS:
            continue                                  # pas (assez) de bougies = non couvert
        pc = meta.get(tk, {}).get('prev_close')
        if not pc:
            continue
        amin = _added_min(info.get('added'))
        if amin is None:
            continue
        g = g.sort_values('datetime')
        mins = _mins(g['datetime'])
        h = g['h'].to_numpy(float)
        hod = np.maximum.accumulate(h)                # plus-haut courant (causal)
        gap = (hod - pc) / pc * 100.0                 # gap high-based par minute
        pit = mins >= amin                            # point-in-time : à partir de `added`
        for lo, hi in BANDS:
            inband = pit & (gap >= lo) & (gap < hi)
            idx = np.argmax(inband)                   # 1re minute vraie
            if inband[idx]:
                am = int(mins[idx])
                rows.append(dict(ticker=tk, date=day, band=f'{lo}-{hi}',
                                 band_arrival_min=am,
                                 band_arrival_ts=f'{day} {am // 60:02d}:{am % 60:02d}'))
    return rows


def main():
    os.makedirs(OUTDIR, exist_ok=True)
    days = sorted(os.path.basename(f)[5:15] for f in glob.glob(os.path.join(COLLECTED, 'bars-*.parquet')))
    days = [d for d in days if d not in EXCLUDE_DAYS]
    all_rows = []
    for d in days:
        r = build_day(d)
        all_rows += r
        if r:
            print(f"  {d}: {len(r)} (titre×bande)", flush=True)
    full = pd.DataFrame(all_rows)
    if not len(full):
        print("AUCUNE ligne produite."); return
    print(f"\nTOTAL {len(full)} (titre×bande) sur {full.date.nunique()} jours\n")
    print("répartition par bande :")
    for (lo, hi) in BANDS:
        b = full[full.band == f'{lo}-{hi}']
        outp = os.path.join(OUTDIR, f'band-{lo}-{hi}.parquet')
        b.to_parquet(outp, index=False)
        med = int(b.band_arrival_min.median()) if len(b) else 0
        print(f"  {lo}-{hi:>2} : {len(b):>5} titres-jours · arrivée médiane "
              f"{med // 60:02d}:{med % 60:02d} · {b.date.nunique()} jours -> {os.path.relpath(outp, ROOT)}")


if __name__ == '__main__':
    main()
