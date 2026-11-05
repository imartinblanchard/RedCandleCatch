#!/usr/bin/env python3
"""Recherche LARGE de stratégies sur NOS DONNÉES LIVE (générateur d'hypothèses).

⚠️ ~20 séances : des milliers de combos -> faux positifs garantis par hasard. On NE prouve
rien ici ; on REPÈRE des candidates avec des garde-fous anti-bruit sérieux :
  - OOS train/test (split 70/30)
  - robustesse TEMPORELLE : exp > 0 sur la 1re ET la 2e moitié de la période
  - n >= N_MIN, et NON-FRAGILE (exp > 0 après retrait des 3 meilleurs trades)
  - P&L COMPTE (sizing contraint capital) FULL + OOS (règle Martin)
Sortie : classement + CSV. collected_live uniquement.

Dimensions balayées (≈1150 combos) : bande de gap × fenêtre d'heures × repli × capit × sortie.
Les "indicateurs" (vwap, bougie verte, above-open, hod-rth) : passe marginale séparée ensuite.
"""
import os, sys, itertools
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(HERE))))  # racine projet (studies/ = +1 niveau)
from research.live_lab import backtest as bt
from research.live_lab.leaderboard import portfolio

N_MIN = 20
GAPS   = [(5, 10), (10, 20), (5, 20), (5, 50), (3, 10)]
STARTS = [(570, '9:30'), (600, '10:00'), (630, '10:30')]      # entry_start
ENDS   = [(720, '->midi'), (955, '->15:55')]                   # entry_end (exclure ou non l'aprem)
RETR   = [0.05, 0.08, 0.10, 0.12]
CAPIT  = [-1, 1.3, 1.6, 2.0]
EXITS  = [('eod', dict(exit_mode='eod')),
          ('trail10/2', dict(exit_mode='trail', activate_pct=0.10, trail_pct=0.02)),
          ('tp20', dict(exit_mode='tp', tp_pct=0.20))]


def substat(a):
    a = np.asarray(a, float); n = len(a)
    if n < 2: return (n, (a.mean() if n else 0.0), 0.0)
    e = a.mean(); sd = a.std(ddof=1)
    return (n, e, e / (sd / np.sqrt(n)) if sd > 0 else 0.0)


def main():
    groups, dates = bt.load_groups()
    split = bt.oos_split(dates)
    tdays = [d for d in dates if split and d >= split]
    mid = dates[len(dates) // 2]                                  # frontière 1re/2e moitié (temporel)
    print(f"{len(dates)} séances ({dates[0]}→{dates[-1]}), OOS≥{split} ({len(tdays)}j), moitié @ {mid}")
    combos = list(itertools.product(GAPS, STARTS, ENDS, RETR, CAPIT, EXITS))
    print(f"{len(combos)} combinaisons à tester…\n")

    rows = []
    for (gmin, gmax), (es, eslab), (ee, eelab), rp, cr, (exlab, exupd) in combos:
        P = dict(bt.LIVE); P.update(exupd)
        P.update(gap_min=gmin, gap_max=gmax, entry_start=es, entry_end=ee, retrace_pct=rp, capit_ratio=cr)
        t = bt.simulate(groups, P, slip=True)
        n = len(t)
        if n < N_MIN:
            continue
        pnl = t.pnl.to_numpy()
        _, exp, tt = substat(pnl)
        _, e_h1, _ = substat(t[t.date < mid].pnl.to_numpy())
        _, e_h2, _ = substat(t[t.date >= mid].pnl.to_numpy())
        n_te, e_te, t_te = substat(t[t.date >= split].pnl.to_numpy()) if split else (0, 0, 0)
        # non-fragile : retirer les 3 meilleurs trades
        trimmed = np.sort(pnl)[:-3] if n > 3 else pnl
        _, e_trim, _ = substat(trimmed)
        pf = pnl[pnl > 0].sum() / (-pnl[pnl < 0].sum() or 1e-9)
        cpte, _ = portfolio(t, 0.02, P['stop_pct'])
        cpte_o, _ = portfolio(t, 0.02, P['stop_pct'], days=tdays) if split else (0, 0)
        robust = (e_h1 > 0 and e_h2 > 0 and e_te > 0 and e_trim > 0)
        rows.append(dict(gap=f"{gmin}-{gmax}", heures=f"{eslab}{eelab}", repli=rp, capit=cr, sortie=exlab,
                         n=n, trj=round(n / t.date.nunique(), 1), exp=round(exp, 2), t=round(tt, 2),
                         pf=round(pf, 2), e_h1=round(e_h1, 2), e_h2=round(e_h2, 2),
                         e_te=round(e_te, 2), t_te=round(t_te, 2), e_trim=round(e_trim, 2),
                         cpte=round(cpte, 1), cpte_oos=round(cpte_o, 1), robust=robust))
    r = pd.DataFrame(rows)
    out = os.path.join(HERE, '..', 'results', 'strategy_search_results.csv')
    r.sort_values('cpte', ascending=False).to_csv(out, index=False)
    print(f"{len(r)} combos avec n>={N_MIN}. CSV complet -> {out}\n")

    rob = r[r.robust].copy()
    print(f"===== CANDIDATES ROBUSTES ({len(rob)}) : exp>0 sur 1re ET 2e moitié + OOS + sans-top3 =====")
    print("(classé par P&L compte ; = hypothèses à surveiller, PAS prouvées)\n")
    cols = ['gap', 'heures', 'repli', 'capit', 'sortie', 'n', 'trj', 'exp', 't', 'pf', 'e_h1', 'e_h2', 'e_te', 'cpte', 'cpte_oos']
    print(rob.sort_values('cpte', ascending=False).head(25)[cols].to_string(index=False))


if __name__ == '__main__':
    main()
