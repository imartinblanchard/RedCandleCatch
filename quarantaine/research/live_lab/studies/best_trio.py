#!/usr/bin/env python3
"""Meilleur TRIO de stratégies peu corrélées (~5 tr/j), filtre d'activité ON. Live only.

Pool de stratégies diverses (toutes : recent_active>=0.7, hodRTH, trail, hold-cloture).
Simule chacune -> trades + série P&L quotidienne. Énumère tous les trios -> pour chaque :
portefeuille combiné (union 1/ticker/jour, sizing 2%), CPTE full+OOS, trades/jour, et
corrélation moyenne des P&L quotidiens (faible = diversifié). Classe par OOS.
⚠️ brute-force de trios sur 21 j = surapprentissage -> hypothèses. collected_live uniquement.
"""
import os, sys, itertools
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(HERE))))
from research.live_lab import backtest as bt
from research.live_lab.leaderboard import portfolio

TRAIL = dict(exit_mode='trail', activate_pct=0.10, trail_pct=0.02)
RA = 0.9
# pool curé : gaps/heures/replis/capit/vert variés, tous hodRTH + activité + trail
POOL = {
    'a 5-10/9:30/r8/cap2':     dict(gap_min=5, gap_max=10, entry_start=570, retrace_pct=0.08, capit_ratio=2.0),
    'b 5-10/9:30/r8/capOFF':   dict(gap_min=5, gap_max=10, entry_start=570, retrace_pct=0.08, capit_ratio=-1),
    'c 3-10/9:30/r8/cap1.6':   dict(gap_min=3, gap_max=10, entry_start=570, retrace_pct=0.08, capit_ratio=1.6),
    'd 10-20/9:30/r10/capOFF': dict(gap_min=10, gap_max=20, entry_start=570, retrace_pct=0.10, capit_ratio=-1),
    'e 10-20/10:00/r10/capOFF':dict(gap_min=10, gap_max=20, entry_start=600, retrace_pct=0.10, capit_ratio=-1),
    'f 20-50/9:30/r8/capOFF':  dict(gap_min=20, gap_max=50, entry_start=570, retrace_pct=0.08, capit_ratio=-1),
    'g 20-50/10:00/r10/capOFF':dict(gap_min=20, gap_max=50, entry_start=600, retrace_pct=0.10, capit_ratio=-1),
    'h 5-50/10:30/r12/capOFF': dict(gap_min=5, gap_max=50, entry_start=630, retrace_pct=0.12, capit_ratio=-1),
    'i 5-50/10:00/r10/green':  dict(gap_min=5, gap_max=50, entry_start=600, retrace_pct=0.10, capit_ratio=-1, require_green=True),
    'j 5-50/10:30/r8/green':   dict(gap_min=5, gap_max=50, entry_start=630, retrace_pct=0.08, capit_ratio=-1, require_green=True),
    'k 5-50/10:00/r12/capOFF': dict(gap_min=5, gap_max=50, entry_start=600, retrace_pct=0.12, capit_ratio=-1),
    'l 5-20/10:00/r12/capOFF': dict(gap_min=5, gap_max=20, entry_start=600, retrace_pct=0.12, capit_ratio=-1),
    'm 5-20/10:30/r10/capOFF': dict(gap_min=5, gap_max=20, entry_start=630, retrace_pct=0.10, capit_ratio=-1),
    'n 5-10/10:00/r10/cap1.3': dict(gap_min=5, gap_max=10, entry_start=600, retrace_pct=0.10, capit_ratio=1.3),
    'o 10-20/9:30/r8/green':   dict(gap_min=10, gap_max=20, entry_start=570, retrace_pct=0.08, capit_ratio=-1, require_green=True),
    'p 5-50/9:30/r10/capOFF':  dict(gap_min=5, gap_max=50, entry_start=570, retrace_pct=0.10, capit_ratio=-1),
}
MIN_N = 10


def main():
    groups, dates = bt.load_groups()
    split = bt.oos_split(dates); tdays = [d for d in dates if split and d >= split]
    alldates = pd.Index(dates)
    print(f"{len(dates)} séances, OOS≥{split}. recent_active={RA}, hodRTH, trail. Pool={len(POOL)}.\n", flush=True)

    sims = {}
    for name, upd in POOL.items():
        P = dict(bt.LIVE); P.update(upd, **TRAIL, hod_in_rth=True, recent_active_min=RA, recent_active_window=10)
        t = bt.simulate(groups, P, slip=True)
        if len(t) >= MIN_N and t.pnl.mean() > 0:
            daily = t.groupby('date').pnl.sum().reindex(alldates, fill_value=0.0)
            sims[name] = dict(tr=t[['ticker', 'date', 'entry_min', 'pnl']], daily=daily,
                              n=len(t), exp=t.pnl.mean(), trj=len(t) / t.date.nunique())
    print(f"{len(sims)} stratégies retenues (n>={MIN_N}, exp>0) :")
    for name, s in sorted(sims.items(), key=lambda x: -x[1]['exp']):
        print(f"  {name:<26} n={s['n']:>3} {s['trj']:.1f}/j exp={s['exp']:+.2f}%", flush=True)

    names = list(sims)
    rows = []
    for a, b, c in itertools.combinations(names, 3):
        comb = pd.concat([sims[a]['tr'], sims[b]['tr'], sims[c]['tr']], ignore_index=True)
        comb = comb.sort_values('entry_min').drop_duplicates(['ticker', 'date'], keep='first')
        n = len(comb); trj = n / comb.date.nunique()
        if not (2.0 <= trj <= 8.0):          # cible ~5 trades/jour (bande 3-8)
            continue
        pnl = comb.pnl.to_numpy()
        exp = pnl.mean(); sd = pnl.std(ddof=1) if n > 1 else 0
        t = exp / (sd / np.sqrt(n)) if sd > 0 else 0
        oos = comb[comb.date >= split].pnl
        oexp = oos.mean() if len(oos) else 0
        cp, dd = portfolio(comb, 0.02, 0.10); cpo, _ = portfolio(comb, 0.02, 0.10, days=tdays)
        # corrélation moyenne des P&L quotidiens (diversification)
        cors = [sims[x]['daily'].corr(sims[y]['daily']) for x, y in itertools.combinations((a, b, c), 2)]
        corr = float(np.nanmean(cors))
        rows.append(dict(trio=f"{a.split()[0]}+{b.split()[0]}+{c.split()[0]}", n=n, trj=round(trj, 1),
                         exp=round(exp, 2), t=round(t, 2), oos=round(oexp, 2),
                         cpte=round(cp, 1), cpte_oos=round(cpo, 1), maxDD=round(dd, 1), corr=round(corr, 2)))
    r = pd.DataFrame(rows)
    if not len(r):
        print('Aucun trio >=2 tr/j : le filtre strict laisse trop peu de trades.'); return
    r = r.sort_values('cpte_oos', ascending=False)
    r.to_csv(os.path.join(HERE, '..', 'results', 'best_trio_results.csv'), index=False)
    print(f"\n{len(r)} trios dans la bande 3-8 tr/j. TOP 15 par OOS compte :\n", flush=True)
    print(r.head(15).to_string(index=False), flush=True)
    print("\nMeilleur trio PEU CORRÉLÉ (corr<=0.2, parmi top OOS) :", flush=True)
    lowc = r[r['corr'] <= 0.2].head(5)
    print(lowc.to_string(index=False) if len(lowc) else "  (aucun avec corr<=0.2)", flush=True)


if __name__ == '__main__':
    main()
