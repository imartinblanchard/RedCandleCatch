#!/usr/bin/env python3
"""Sweep des 2 filtres de liquidité sur la config LIVE 'liq-eod', données live (sans biais) :
  - pullback_dvol_min : dollar-volume du repli (actuel 300K)
  - PM-liquidité       : latepm_frac >= seuil (actuel 0.20 = actif >=20% des min 8:00-9:30)
Pour chaque combo : n, trades/j, exp/tr, win%, CPTE full+OOS (sizing 2%), maxDD. On cherche si des
seuils plus STRICTS améliorent (meilleure qualité) sans trop réduire n. ⚠️ live only, petit n."""
import os, sys, itertools
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(HERE))))
from research.live_lab import backtest as bt
from research.live_lab.leaderboard import portfolio

PM_CSV = os.path.join(HERE, '..', 'results', 'liquid_universe_pm.csv')
PM_THR = [0.0, 0.10, 0.20, 0.30, 0.40, 0.50]          # 0 = filtre PM OFF ; 0.20 = actuel
DVOL = [0, 100_000, 200_000, 300_000, 500_000, 1_000_000]   # 300K = actuel
LIQEOD = dict(gap_min=5, gap_max=50, entry_start=600, retrace_pct=0.12, capit_ratio=-1,
              hod_in_rth=True, exit_mode='eod')


def main():
    groups, dates = bt.load_groups()
    split = bt.oos_split(dates); tdays = [d for d in dates if split and d >= split]
    u = pd.read_csv(PM_CSV)
    print(f"{len(dates)} séances live, OOS≥{split}. Config liq-eod. Actuel = PM>=0.20 / dvol>=300K.\n", flush=True)

    rows = []
    for pm in PM_THR:
        keep = None if pm <= 0 else set(zip(u[u.latepm_frac >= pm].ticker, u[u.latepm_frac >= pm].date))
        g_use = groups if keep is None else [g for g in groups if (g['tk'], g['date']) in keep]
        for dv in DVOL:
            P = dict(bt.LIVE); P.update(LIQEOD, pullback_dvol_min=dv)
            t = bt.simulate(g_use, P, slip=True)
            if not len(t):
                rows.append(dict(pm=pm, dvol=dv, n=0, trj=0, exp=0, win=0, cpte=0, cpte_oos=0, maxDD=0)); continue
            pnl = t.pnl.to_numpy(); cp, dd = portfolio(t, 0.02, 0.10); cpo, _ = portfolio(t, 0.02, 0.10, days=tdays)
            rows.append(dict(pm=pm, dvol=dv, n=len(pnl), trj=round(len(pnl)/t.date.nunique(), 1),
                             exp=round(pnl.mean(), 2), win=round((pnl > 0).mean()*100), t=round(pnl.mean()/(pnl.std(ddof=1)/np.sqrt(len(pnl))),1) if len(pnl)>1 and pnl.std()>0 else 0,
                             cpte=round(cp, 1), cpte_oos=round(cpo, 1), maxDD=round(dd, 1)))
    r = pd.DataFrame(rows)
    r.to_csv(os.path.join(HERE, '..', 'results', 'sweep_dvol_pmliq.csv'), index=False)

    def grid(metric, title):
        print(f"\n=== {title} (lignes = PM-liq seuil, colonnes = dvol-repli) ===")
        p = r.pivot(index='pm', columns='dvol', values=metric)
        p.columns = [f"{c/1000:.0f}K" if c else "OFF" for c in p.columns]
        print(p.round(2).to_string())
    grid('exp', 'EXP/TR %')
    grid('n', 'NOMBRE DE TRADES')
    grid('cpte', 'CPTE % (compte, risque 2%)')
    grid('win', 'WIN %')
    print("\n⚠️ Actuel = PM 0.20 / dvol 300K. Chercher : exp/CPTE qui MONTENT en durcissant SANS que n s'effondre.")
    print("CSV: research/live_lab/results/sweep_dvol_pmliq.csv")


if __name__ == '__main__':
    main()
