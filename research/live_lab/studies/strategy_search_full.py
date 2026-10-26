#!/usr/bin/env python3
"""Recherche LARGE v3 (COMPLETE) : tous les filtres, y compris activité récente. Live only.

Dimensions : gap x heures x repli x capit x sortie x HOD x bougie-verte x VWAP x ACTIVITE-RECENTE
≈ 23 000 combos. ⚠️ ~19 séances + des dizaines de milliers de combos = faux positifs ENORMES :
garde-fous (OOS + 2 moities positives + non-fragile + n>=N_MIN). Ecrit le CSV toutes les 1000
combos (lisible en cours). collected_live uniquement. Supersede strategy_search_indicators.py.
"""
import os, sys, itertools, time
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(HERE))))
from research.live_lab import backtest as bt
from research.live_lab.leaderboard import portfolio

N_MIN = 20
GAPS   = [(5, 10), (10, 20), (5, 20), (5, 50), (3, 10)]
STARTS = [(570, '9:30'), (600, '10:00'), (630, '10:30')]
ENDS   = [(720, '>midi'), (955, '>15:55')]
RETR   = [0.05, 0.08, 0.10, 0.12]
CAPIT  = [-1, 1.3, 1.6, 2.0]
EXITS  = [('eod', dict(exit_mode='eod')),
          ('trail10/2', dict(exit_mode='trail', activate_pct=0.10, trail_pct=0.02)),
          ('tp20', dict(exit_mode='tp', tp_pct=0.20))]
HOD    = [('', False), ('hodRTH', True)]
GREEN  = [('', False), ('green', True)]
VWAP   = [('', None), ('vw<', 'below')]
RECACT = [('', 0.0), ('rAct80', 0.8)]          # NOUVEAU : activité récente (fraction 10 dern. min avec trade)
OUT = os.path.join(HERE, '..', 'results', 'strategy_search_full_results.csv')


def substat(a):
    a = np.asarray(a, float); n = len(a)
    if n < 2: return (n, (a.mean() if n else 0.0), 0.0)
    e = a.mean(); sd = a.std(ddof=1)
    return (n, e, e / (sd / np.sqrt(n)) if sd > 0 else 0.0)


def main():
    groups, dates = bt.load_groups()
    split = bt.oos_split(dates); tdays = [d for d in dates if split and d >= split]
    mid = dates[len(dates) // 2]
    combos = list(itertools.product(GAPS, STARTS, ENDS, RETR, CAPIT, EXITS, HOD, GREEN, VWAP, RECACT))
    print(f"{len(dates)} séances, OOS≥{split}, moitié@{mid} | {len(combos)} combos", flush=True)
    rows = []; t0 = time.time()
    for k, ((gmin, gmax), (es, esl), (ee, eel), rp, cr, (exl, exu), (hl, hv), (gl, gv), (vl, vv), (ral, rav)) in enumerate(combos):
        if k and k % 1000 == 0:
            pd.DataFrame(rows).to_csv(OUT, index=False)
            print(f"  {k}/{len(combos)} ({(time.time()-t0)/60:.0f}min) — {len(rows)} combos n>={N_MIN}", flush=True)
        P = dict(bt.LIVE); P.update(exu)
        P.update(gap_min=gmin, gap_max=gmax, entry_start=es, entry_end=ee, retrace_pct=rp, capit_ratio=cr,
                 hod_in_rth=hv, require_green=gv, vwap_side=vv, recent_active_min=rav, recent_active_window=10)
        t = bt.simulate(groups, P, slip=True)
        n = len(t)
        if n < N_MIN:
            continue
        pnl = t.pnl.to_numpy()
        _, exp, tt = substat(pnl)
        _, e_h1, _ = substat(t[t.date < mid].pnl.to_numpy())
        _, e_h2, _ = substat(t[t.date >= mid].pnl.to_numpy())
        _, e_te, t_te = substat(t[t.date >= split].pnl.to_numpy())
        _, e_trim, _ = substat(np.sort(pnl)[:-3] if n > 3 else pnl)
        pf = pnl[pnl > 0].sum() / (-pnl[pnl < 0].sum() or 1e-9)
        cpte, _ = portfolio(t, 0.02, P['stop_pct'])
        cpte_o, _ = portfolio(t, 0.02, P['stop_pct'], days=tdays)
        ind = '+'.join(x for x in (hl, gl, vl, ral) if x) or '—'
        rows.append(dict(gap=f"{gmin}-{gmax}", heures=f"{esl}{eel}", repli=rp, capit=cr, sortie=exl, indic=ind,
                         n=n, trj=round(n / t.date.nunique(), 1), exp=round(exp, 2), t=round(tt, 2), pf=round(pf, 2),
                         e_h1=round(e_h1, 2), e_h2=round(e_h2, 2), e_te=round(e_te, 2), t_te=round(t_te, 2),
                         e_trim=round(e_trim, 2), cpte=round(cpte, 1), cpte_oos=round(cpte_o, 1),
                         robust=bool(e_h1 > 0 and e_h2 > 0 and e_te > 0 and e_trim > 0)))
    r = pd.DataFrame(rows); r.to_csv(OUT, index=False)
    print(f"\nFINI en {(time.time()-t0)/60:.0f}min. {len(r)} combos n>={N_MIN}. CSV -> {OUT}", flush=True)
    bal = r[r.robust & (r.e_h1 >= 0.8) & (r.e_h2 >= 0.8) & (r.e_te >= 0.8) & (r.t >= 2.3)]
    bal = bal.sort_values('cpte', ascending=False).drop_duplicates(subset=['n', 'exp', 'pf', 'cpte', 'cpte_oos'])
    print(f"\n===== CANDIDATES EQUILIBREES ({len(bal)}) — top 25 par P&L compte =====", flush=True)
    cols = ['gap', 'heures', 'repli', 'capit', 'sortie', 'indic', 'n', 'trj', 'exp', 't', 'pf', 'e_h1', 'e_h2', 'e_te', 'cpte', 'cpte_oos']
    print(bal.head(25)[cols].to_string(index=False), flush=True)
    rac = bal[bal.indic.str.contains('rAct')]
    print(f"\n-> dont AVEC activité récente : {len(rac)} candidates (si ~0, le filtre n'aide pas en combinaison)", flush=True)


if __name__ == '__main__':
    main()
