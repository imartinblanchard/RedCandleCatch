#!/usr/bin/env python3
"""Recherche COMPLÈTE famille REPLI, lancée chaque soir de bourse. Balaie en combinaison :
ENTRÉE (gap × heure début/fin × repli × capitulation × HOD-séance × bougie verte × VWAP × activité)
ET SORTIE (stop × mode eod/trail/tp × réglages) — la sortie était le gros TROU (figée avant).
Optimisé : entrées détectées UNE fois par config d'entrée, sorties balayées par-dessus (gratuit).

Classé par CPTE (capital final) + robustesse (t-stat, e_trim non-fragile, exp>0 sur les 2 moitiés).
⚠️ données courtes (~25 séances) × dizaines de milliers de combos = FAUX POSITIFS énormes : lire la
PERSISTANCE dans le temps (track_robust) + le forward-test LIVE, jamais un gagnant isolé.
collected_live uniquement. CSV -> results/strategy_search_full_results.csv."""
import os, sys, time, itertools
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(HERE))))
from research.live_lab import backtest as bt
from research.live_lab.leaderboard import portfolio
from research.indicator_lab.engine import liquid_groups    # univers freq-filtré = ce qu'on trade

N_MIN = 20
# ── dimensions d'ENTRÉE ──
GAPS   = [(5, 10), (10, 20), (5, 20), (5, 50), (3, 10)]
STARTS = [(570, '9:30'), (600, '10:00'), (630, '10:30')]
ENDS   = [(720, '>midi'), (955, '>15:55')]
RETR   = [0.05, 0.08, 0.10, 0.12]
CAPIT  = [-1, 1.3, 1.6, 2.0]
HOD    = [('', False), ('hodRTH', True)]
GREEN  = [('', False), ('green', True)]
VWAP   = [('', None), ('vw<', 'below')]
RECACT = [('', 0.0), ('rAct80', 0.8)]
# ── dimensions de SORTIE (le gros ajout) : stop × mode ──
STOPS = [0.08, 0.10, 0.12]
EMODES = {'eod': dict(exit_mode='eod'),
          'tr5/2': dict(exit_mode='trail', activate_pct=0.05, trail_pct=0.02),
          'tr10/2': dict(exit_mode='trail', activate_pct=0.10, trail_pct=0.02),
          'tr10/5': dict(exit_mode='trail', activate_pct=0.10, trail_pct=0.05),
          'tr15/3': dict(exit_mode='trail', activate_pct=0.15, trail_pct=0.03),
          'tp15': dict(exit_mode='tp', tp_pct=0.15),
          'tp20': dict(exit_mode='tp', tp_pct=0.20),
          'tp30': dict(exit_mode='tp', tp_pct=0.30)}
EXITS = [(f"{el}/s{int(s*100)}", {**ex, 'stop_pct': s}) for el, ex in EMODES.items() for s in STOPS]
OUT = os.path.join(HERE, '..', 'results', 'strategy_search_full_results.csv')


def substat(a):
    a = np.asarray(a, float); n = len(a)
    if n < 2: return (n, (a.mean() if n else 0.0), 0.0)
    e = a.mean(); sd = a.std(ddof=1)
    return (n, e, e / (sd / np.sqrt(n)) if sd > 0 else 0.0)


def main():
    groups, dates = bt.load_groups()
    groups = liquid_groups(groups)                          # FREQ-FILTRÉ uniquement (univers tradable)
    split = bt.oos_split(dates); tdays = [d for d in dates if d >= split]; mid = dates[len(dates) // 2]
    ecombos = list(itertools.product(GAPS, STARTS, ENDS, RETR, CAPIT, HOD, GREEN, VWAP, RECACT))
    print(f"{len(dates)} séances, OOS≥{split} | {len(ecombos)} configs d'ENTRÉE × {len(EXITS)} sorties "
          f"= {len(ecombos)*len(EXITS)} combos\n", flush=True)
    rows = []; t0 = time.time()
    for k, ((gmin, gmax), (es, esl), (ee, eel), rp, cr, (hl, hv), (gl, gv), (vl, vv), (ral, rav)) in enumerate(ecombos):
        if k and k % 500 == 0:
            pd.DataFrame(rows).to_csv(OUT, index=False)
            print(f"  {k}/{len(ecombos)} entrées ({(time.time()-t0)/60:.0f}min) — {len(rows)} combos", flush=True)
        Pe = dict(bt.LIVE)
        Pe.update(gap_min=gmin, gap_max=gmax, entry_start=es, entry_end=ee, retrace_pct=rp, capit_ratio=cr,
                  hod_in_rth=hv, require_green=gv, vwap_side=vv, recent_active_min=rav, recent_active_window=10)
        ents = bt.entries(groups, Pe)
        if len(ents) < N_MIN:
            continue
        ind = '+'.join(x for x in (hl, gl, vl, ral) if x) or '—'
        for exl, exu in EXITS:
            P = dict(Pe); P.update(exu)
            t = bt.trades_from(ents, P, slip=True)
            if len(t) < N_MIN:
                continue
            pnl = t.pnl.to_numpy(); _, exp, tt = substat(pnl)
            _, e_h1, _ = substat(t[t.date < mid].pnl.to_numpy())
            _, e_h2, _ = substat(t[t.date >= mid].pnl.to_numpy())
            _, e_te, _ = substat(t[t.date >= split].pnl.to_numpy())
            _, e_trim, _ = substat(np.sort(pnl)[:-3] if len(pnl) > 3 else pnl)
            pf = pnl[pnl > 0].sum() / (-pnl[pnl < 0].sum() or 1e-9)
            cpte, dd = portfolio(t, 0.02, P['stop_pct']); cpte_o, _ = portfolio(t, 0.02, P['stop_pct'], days=tdays)
            rows.append(dict(gap=f"{gmin}-{gmax}", heures=f"{esl}{eel}", repli=rp, capit=cr, indic=ind, exit=exl,
                             n=len(pnl), trj=round(len(pnl) / t.date.nunique(), 1), exp=round(exp, 2),
                             t=round(tt, 2), e_trim=round(e_trim, 2), pf=round(pf, 2), win=round((pnl > 0).mean()*100),
                             e_h1=round(e_h1, 2), e_h2=round(e_h2, 2), e_te=round(e_te, 2), maxDD=round(dd, 1),
                             cpte=round(cpte, 1), cpte_oos=round(cpte_o, 1),
                             robust=bool(e_h1 > 0 and e_h2 > 0 and e_te > 0 and e_trim > 0 and tt >= 2.3)))
    r = pd.DataFrame(rows); r.to_csv(OUT, index=False)
    print(f"\nFINI en {(time.time()-t0)/60:.0f}min. {len(r)} combos. {int(r.robust.sum()) if len(r) else 0} robustes.", flush=True)
    base = r[r.robust] if (len(r) and r.robust.any()) else r
    cols = ['gap', 'heures', 'repli', 'capit', 'indic', 'exit', 'n', 'trj', 'exp', 't', 'e_trim', 'win', 'maxDD', 'cpte', 'cpte_oos']
    if len(base):
        print("\n===== TOP 25 par CPTE (robustes) =====", flush=True)
        print(base.sort_values('cpte', ascending=False).head(25)[cols].to_string(index=False), flush=True)


if __name__ == '__main__':
    main()
