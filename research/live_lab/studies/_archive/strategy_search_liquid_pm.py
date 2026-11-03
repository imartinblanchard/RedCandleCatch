#!/usr/bin/env python3
"""Recherche LARGE sur l'univers liquide *CAUSAL* (fréquence PRÉ-MARCHÉ) — 29/10.

Filtre de liquidité CAUSAL (connu à l'open, pas de look-ahead) : on ne garde que les ticker-jours
qui tradaient déjà en fréquence élevée en PM (build_liquid_universe_pm.py). Puis grande recherche
de stratégies dedans. Si l'edge tient ici, il est reproductible EN LIVE.

Univers testés (boucle externe) : near/latepm × seuils, choisis pour garder assez d'échantillon.
Dimensions : gap x heures x repli x capit x sortie x HOD x vert x VWAP. Garde-fous anti-faux-positifs
(OOS + 2 moitiés + non-fragile + n>=N_MIN). collected_live uniquement.
"""
import os, sys, itertools, time
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(HERE))))
from research.live_lab import backtest as bt
from research.live_lab.leaderboard import portfolio

N_MIN = 20
UNIV_CSV = os.path.join(HERE, '..', 'results', 'liquid_universe_pm.csv')
# (label, colonne de fraction PM, seuil)  — causal : mesuré AVANT l'open
UNIVERSES = [('near02', 'near_frac', 0.2), ('near03', 'near_frac', 0.3),
             ('latepm02', 'latepm_frac', 0.2), ('latepm03', 'latepm_frac', 0.3)]
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
OUT = os.path.join(HERE, '..', 'results', 'strategy_search_liquid_pm_results.csv')


def substat(a):
    a = np.asarray(a, float); n = len(a)
    if n < 2: return (n, (a.mean() if n else 0.0), 0.0)
    e = a.mean(); sd = a.std(ddof=1)
    return (n, e, e / (sd / np.sqrt(n)) if sd > 0 else 0.0)


def main():
    groups, dates = bt.load_groups()
    split = bt.oos_split(dates); tdays = [d for d in dates if split and d >= split]
    mid = dates[len(dates) // 2]
    u = pd.read_csv(UNIV_CSV)
    usets = {lbl: set(zip(u[u[col] >= thr].ticker, u[u[col] >= thr].date)) for lbl, col, thr in UNIVERSES}
    pcombos = list(itertools.product(GAPS, STARTS, ENDS, RETR, CAPIT, EXITS, HOD, GREEN, VWAP))
    total = len(pcombos) * len(UNIVERSES)
    print(f"{len(dates)} séances, OOS≥{split}, moitié@{mid} | {total} combos "
          f"({len(pcombos)}/univers × {len(UNIVERSES)})", flush=True)
    rows = []; t0 = time.time(); k = 0
    for ulbl, col, thr in UNIVERSES:
        uset = usets[ulbl]
        g_use = [g for g in groups if (g['tk'], g['date']) in uset]
        print(f"  univers {ulbl} ({col}>={thr}): {len(g_use)} groupes — démarrage", flush=True)
        for ((gmin, gmax), (es, esl), (ee, eel), rp, cr, (exl, exu),
             (hl, hv), (gl, gv), (vl, vv)) in pcombos:
            k += 1
            if k % 1000 == 0:
                pd.DataFrame(rows).to_csv(OUT, index=False)
                print(f"  {k}/{total} ({(time.time()-t0)/60:.0f}min) — {len(rows)} combos n>={N_MIN}", flush=True)
            if not g_use:
                continue
            P = dict(bt.LIVE); P.update(exu)
            P.update(gap_min=gmin, gap_max=gmax, entry_start=es, entry_end=ee, retrace_pct=rp, capit_ratio=cr,
                     hod_in_rth=hv, require_green=gv, vwap_side=vv, recent_active_min=0.0)
            t = bt.simulate(g_use, P, slip=True)
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
            ind = '+'.join(x for x in (hl, gl, vl) if x) or '—'
            rows.append(dict(univ=ulbl, gap=f"{gmin}-{gmax}", heures=f"{esl}{eel}", repli=rp, capit=cr,
                             sortie=exl, indic=ind, n=n, trj=round(n / t.date.nunique(), 1),
                             exp=round(exp, 2), t=round(tt, 2), pf=round(pf, 2),
                             e_h1=round(e_h1, 2), e_h2=round(e_h2, 2), e_te=round(e_te, 2), t_te=round(t_te, 2),
                             e_trim=round(e_trim, 2), cpte=round(cpte, 1), cpte_oos=round(cpte_o, 1),
                             robust=bool(e_h1 > 0 and e_h2 > 0 and e_te > 0 and e_trim > 0)))
    r = pd.DataFrame(rows); r.to_csv(OUT, index=False)
    print(f"\nFINI en {(time.time()-t0)/60:.0f}min. {len(r)} combos n>={N_MIN}. CSV -> {OUT}", flush=True)
    bal = r[r.robust & (r.e_h1 >= 0.8) & (r.e_h2 >= 0.8) & (r.e_te >= 0.8) & (r.t >= 2.3)]
    bal = bal.sort_values('cpte', ascending=False).drop_duplicates(subset=['univ', 'n', 'exp', 'pf', 'cpte'])
    cols = ['univ', 'gap', 'heures', 'repli', 'capit', 'sortie', 'indic', 'n', 'trj', 'exp', 't', 'pf',
            'e_h1', 'e_h2', 'e_te', 'cpte', 'cpte_oos']
    print(f"\n===== CANDIDATES EQUILIBREES ({len(bal)}) — top 30 par P&L compte =====", flush=True)
    print((bal.head(30)[cols].to_string(index=False) if len(bal) else "  (aucune)"), flush=True)
    print("\n===== MEILLEURE par univers (CPTE, robuste ou non) =====", flush=True)
    for ulbl, col, thr in UNIVERSES:
        sub = r[r.univ == ulbl].sort_values('cpte', ascending=False)
        print(f"\n--- {ulbl} ({col}>={thr}) — {len(sub)} combos n>={N_MIN} ---", flush=True)
        print((sub.head(5)[cols + ['robust']].to_string(index=False) if len(sub) else "  (rien n>=20)"), flush=True)


if __name__ == '__main__':
    main()
