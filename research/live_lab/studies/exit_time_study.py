#!/usr/bin/env python3
"""Heure de sortie (`eod`) comme DIMENSION, pas de 10 min. Live only.

Astuce : eod n'affecte PAS la détection d'entrée -> on détecte les entrées UNE fois par
config d'entrée (gap×heures×repli×capit×HOD×vert×VWAP), puis on balaie eod (10:00->16:00
par 10 min) × type de sortie (eod/trail/tp) a cout quasi nul. Garde-fous habituels + P&L compte.
Sortie : results/exit_time_results.csv + courbe « meilleure heure ». collected_live uniquement.
"""
import os, sys, itertools, time
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(HERE))))
from research.live_lab import backtest as bt
from research.live_lab.leaderboard import EXPCAP, POSCAP, MAXPOS

EODS = list(range(600, 961, 10))          # 10:00 -> 16:00 par 10 min
GAPS = [(5, 10), (10, 20), (5, 20), (5, 50), (3, 10)]
STARTS = [(570, '9:30'), (600, '10:00'), (630, '10:30')]
ENDS = [(720, '>midi'), (955, '>15:55')]
RETR = [0.05, 0.08, 0.10, 0.12]
CAPIT = [-1, 1.3, 1.6, 2.0]
HOD = [('', False), ('hodRTH', True)]
GREEN = [('', False), ('green', True)]
VWAP = [('', None), ('vw<', 'below')]
EXITS = [('eod', dict(exit_mode='eod')),
         ('trail10/2', dict(exit_mode='trail', activate_pct=0.10, trail_pct=0.02)),
         ('tp20', dict(exit_mode='tp', tp_pct=0.20))]
N_MIN = 20
OUT = os.path.join(HERE, '..', 'results', 'exit_time_results.csv')


def hhmm(m): return f"{m//60:02d}:{m%60:02d}"


def main():
    groups, dates = bt.load_groups()
    split = bt.oos_split(dates); tdays = set(d for d in dates if split and d >= split)
    mid = dates[len(dates) // 2]
    stop = bt.LIVE['stop_pct']
    entry_cfgs = list(itertools.product(GAPS, STARTS, ENDS, RETR, CAPIT, HOD, GREEN, VWAP))
    print(f"{len(dates)} séances, OOS≥{split}. {len(entry_cfgs)} configs d'entrée x {len(EXITS)} sorties x {len(EODS)} heures", flush=True)
    rows = []; t0 = time.time()

    for k, ((gmin, gmax), (es, esl), (ee, eel), rp, cr, (hl, hv), (gl, gv), (vl, vv)) in enumerate(entry_cfgs):
        if k and k % 400 == 0:
            pd.DataFrame(rows).to_csv(OUT, index=False)
            print(f"  {k}/{len(entry_cfgs)} ({(time.time()-t0)/60:.0f}min) — {len(rows)} lignes", flush=True)
        P0 = dict(bt.LIVE); P0.update(gap_min=gmin, gap_max=gmax, entry_start=es, entry_end=ee,
                                      retrace_pct=rp, capit_ratio=cr, hod_in_rth=hv,
                                      require_green=gv, vwap_side=vv)
        # DÉTECTION D'ENTRÉES (une seule fois, indépendante de la sortie)
        ents = []
        for g in groups:
            e = bt._entry_index(g, P0)
            if e:
                ents.append((g, e['i'], g['date']))
        if len(ents) < N_MIN:
            continue
        dts = np.array([d for _, _, d in ents])
        # structure jour (pour le P&L compte) : ordre par entry_min dans chaque jour
        emins = np.array([int(g['mins'][i]) for g, i, _ in ents])
        order = np.lexsort((emins, dts))
        n = len(ents); avg_per_day = n / len(set(dts))
        posfrac = min(min(0.02 / stop, POSCAP), EXPCAP / avg_per_day)  # sizing risque 2%

        for exl, exu in EXITS:
            for eod in EODS:
                Pe = dict(P0); Pe.update(exu); Pe['eod'] = eod
                pnl = np.array([bt._pnl(g, i, Pe, slip=True) for g, i, _ in ents])
                exp = pnl.mean()
                sd = pnl.std(ddof=1) if n > 1 else 0.0
                tstat = exp / (sd / np.sqrt(n)) if sd > 0 else 0.0
                e_h1 = pnl[dts < mid].mean() if (dts < mid).any() else 0.0
                e_h2 = pnl[dts >= mid].mean() if (dts >= mid).any() else 0.0
                te_mask = np.array([d in tdays for d in dts])
                e_te = pnl[te_mask].mean() if te_mask.any() else 0.0
                # P&L compte (compounding quotidien, max MAXPOS/jour)
                eq = 1.0; cur = None; cnt = 0; daysum = 0.0
                for idx in order:
                    d = dts[idx]
                    if d != cur:
                        if cur is not None:
                            eq += eq * posfrac * daysum
                        cur = d; cnt = 0; daysum = 0.0
                    if cnt < MAXPOS:
                        daysum += pnl[idx] / 100.0; cnt += 1
                eq += eq * posfrac * daysum
                cpte = (eq - 1) * 100
                rows.append(dict(gap=f"{gmin}-{gmax}", heures=f"{esl}{eel}", repli=rp, capit=cr,
                                 hod=hl or '-', green=gl or '-', vwap=vl or '-', sortie=exl,
                                 eod=hhmm(eod), n=n, exp=round(exp, 2), t=round(tstat, 2),
                                 e_h1=round(e_h1, 2), e_h2=round(e_h2, 2), e_te=round(e_te, 2),
                                 cpte=round(cpte, 1),
                                 robust=bool(e_h1 > 0 and e_h2 > 0 and e_te > 0)))
    r = pd.DataFrame(rows); r.to_csv(OUT, index=False)
    print(f"\nFINI {(time.time()-t0)/60:.0f}min, {len(r)} lignes -> {OUT}", flush=True)

    # ===== COURBE : meilleure heure de sortie (agrégé sur les configs robustes) =====
    print("\n===== HEURE DE SORTIE — CPTE moyen des configs ROBUSTES par heure (tous types) =====", flush=True)
    rob = r[r.robust]
    cur = rob.groupby('eod').agg(nconf=('cpte', 'size'), cpte_moy=('cpte', 'mean'),
                                 exp_moy=('exp', 'mean')).reset_index().sort_values('eod')
    print(cur.to_string(index=False), flush=True)
    print("\n===== Par TYPE de sortie : heure qui maximise le CPTE moyen (robustes) =====", flush=True)
    for exl, _ in EXITS:
        sub = rob[rob.sortie == exl]
        if not len(sub):
            print(f"  {exl}: aucune robuste"); continue
        g = sub.groupby('eod').cpte.mean()
        best = g.idxmax()
        print(f"  {exl:<10} meilleure heure = {best}  (CPTE moy {g.max():+.1f}%) ; a 15:55 = {g.get('15:55', float('nan')):+.1f}%", flush=True)


if __name__ == '__main__':
    main()
