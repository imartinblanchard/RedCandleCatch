#!/usr/bin/env python3
"""Parmi les stratégies RENTABLES, lesquelles prennent des tickers DIFFÉRENTS les unes des autres.

Mesure = recouvrement des ensembles de trades (paires ticker-jour), via Jaccard :
  overlap(A,B) = |trades_A ∩ trades_B| / |trades_A ∪ trades_B|
0% = elles ne touchent jamais le même titre le même jour (diversification maximale),
100% = elles tradent exactement le même panier. Complémentaire de best_trio (corr des P&L).

Pool = stratégies diverses et INDIVIDUELLEMENT rentables (reprend best_trio : hodRTH, trail,
activité) + la config live liq-eod (hold-EOD). Sortie : matrice d'overlap + sélection gloutonne
d'un roster le plus DISJOINT possible (chaque ajout = la strat rentable qui recoupe le moins les
déjà retenues). ⚠️ live only, petit n (~21 j) -> hypothèses. collected_live uniquement.
"""
import os, sys, itertools
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(HERE))))
from research.live_lab import backtest as bt
from research.live_lab.leaderboard import portfolio

TRAIL = dict(exit_mode='trail', activate_pct=0.10, trail_pct=0.02)
RA = 0.9
POOL = {   # mêmes archétypes variés que best_trio (gaps/heures/replis/capit/vert divers)
    'a 5-10/9:30/r8/cap2':     dict(gap_min=5, gap_max=10, entry_start=570, retrace_pct=0.08, capit_ratio=2.0, **TRAIL, hod_in_rth=True, recent_active_min=RA, recent_active_window=10),
    'b 5-10/9:30/r8/capOFF':   dict(gap_min=5, gap_max=10, entry_start=570, retrace_pct=0.08, capit_ratio=-1, **TRAIL, hod_in_rth=True, recent_active_min=RA, recent_active_window=10),
    'c 3-10/9:30/r8/cap1.6':   dict(gap_min=3, gap_max=10, entry_start=570, retrace_pct=0.08, capit_ratio=1.6, **TRAIL, hod_in_rth=True, recent_active_min=RA, recent_active_window=10),
    'd 10-20/9:30/r10/capOFF': dict(gap_min=10, gap_max=20, entry_start=570, retrace_pct=0.10, capit_ratio=-1, **TRAIL, hod_in_rth=True, recent_active_min=RA, recent_active_window=10),
    'e 10-20/10:00/r10':       dict(gap_min=10, gap_max=20, entry_start=600, retrace_pct=0.10, capit_ratio=-1, **TRAIL, hod_in_rth=True, recent_active_min=RA, recent_active_window=10),
    'f 20-50/9:30/r8/capOFF':  dict(gap_min=20, gap_max=50, entry_start=570, retrace_pct=0.08, capit_ratio=-1, **TRAIL, hod_in_rth=True, recent_active_min=RA, recent_active_window=10),
    'g 20-50/10:00/r10':       dict(gap_min=20, gap_max=50, entry_start=600, retrace_pct=0.10, capit_ratio=-1, **TRAIL, hod_in_rth=True, recent_active_min=RA, recent_active_window=10),
    'h 5-50/10:30/r12/capOFF': dict(gap_min=5, gap_max=50, entry_start=630, retrace_pct=0.12, capit_ratio=-1, **TRAIL, hod_in_rth=True, recent_active_min=RA, recent_active_window=10),
    'i 5-50/10:00/r10/green':  dict(gap_min=5, gap_max=50, entry_start=600, retrace_pct=0.10, capit_ratio=-1, require_green=True, **TRAIL, hod_in_rth=True, recent_active_min=RA, recent_active_window=10),
    'j 5-50/10:30/r8/green':   dict(gap_min=5, gap_max=50, entry_start=630, retrace_pct=0.08, capit_ratio=-1, require_green=True, **TRAIL, hod_in_rth=True, recent_active_min=RA, recent_active_window=10),
    'k 5-50/10:00/r12/capOFF': dict(gap_min=5, gap_max=50, entry_start=600, retrace_pct=0.12, capit_ratio=-1, **TRAIL, hod_in_rth=True, recent_active_min=RA, recent_active_window=10),
    'l 5-20/10:00/r12/capOFF': dict(gap_min=5, gap_max=20, entry_start=600, retrace_pct=0.12, capit_ratio=-1, **TRAIL, hod_in_rth=True, recent_active_min=RA, recent_active_window=10),
    'n 5-10/10:00/r10/cap1.3': dict(gap_min=5, gap_max=10, entry_start=600, retrace_pct=0.10, capit_ratio=1.3, **TRAIL, hod_in_rth=True, recent_active_min=RA, recent_active_window=10),
    'liq-eod 5-50/10:00/r12':  dict(gap_min=5, gap_max=50, entry_start=600, retrace_pct=0.12, capit_ratio=-1, hod_in_rth=True, exit_mode='eod'),
}
MIN_N = 10


def tkset(t):
    return set(zip(t.ticker, t.date))


def jacc(a, b):
    u = len(a | b)
    return len(a & b) / u if u else 0.0


def main():
    groups, dates = bt.load_groups()
    split = bt.oos_split(dates); tdays = [d for d in dates if split and d >= split]
    print(f"{len(dates)} séances, OOS≥{split}. Pool={len(POOL)}.\n", flush=True)

    sims = {}
    for name, upd in POOL.items():
        P = dict(bt.LIVE); P.update(upd)
        t = bt.simulate(groups, P, slip=True)
        if len(t) >= MIN_N and t.pnl.mean() > 0:
            cp, dd = portfolio(t, 0.02, P['stop_pct'])
            sims[name] = dict(set=tkset(t), n=len(t), trj=len(t) / t.date.nunique(),
                              exp=t.pnl.mean(), cpte=cp)
    print(f"{len(sims)} stratégies RENTABLES retenues (n>={MIN_N}, exp>0), triées par exp/tr :")
    for name, s in sorted(sims.items(), key=lambda x: -x[1]['exp']):
        print(f"  {name:<26} n={s['n']:>3} {s['trj']:.1f}/j exp={s['exp']:+.2f}% cpte={s['cpte']:+.1f}%", flush=True)

    names = list(sims)
    # matrice d'overlap (Jaccard des ensembles ticker-jour)
    M = pd.DataFrame(index=names, columns=names, dtype=float)
    for a, b in itertools.product(names, names):
        M.loc[a, b] = 100.0 if a == b else round(jacc(sims[a]['set'], sims[b]['set']) * 100, 0)
    print("\n########## RECOUVREMENT DE TICKERS (% Jaccard, 0=disjoint) ##########")
    sh = [n.split()[0] for n in names]
    MM = M.copy(); MM.index = sh; MM.columns = sh
    print(MM.astype(int).to_string(), flush=True)

    # paires les plus DISJOINTES (toutes deux rentables, overlap minimal)
    pairs = sorted(((M.loc[a, b], a, b) for a, b in itertools.combinations(names, 2)), key=lambda x: x[0])
    print("\n########## 12 PAIRES LES PLUS DIFFÉRENTES (overlap bas = titres distincts) ##########")
    for ov, a, b in pairs[:12]:
        print(f"  {int(ov):>3}%  {a.split()[0]:>7} + {b.split()[0]:<7}  "
              f"(exp {sims[a]['exp']:+.2f}/{sims[b]['exp']:+.2f}, {sims[a]['n']}+{sims[b]['n']} tr)", flush=True)

    # sélection gloutonne d'un roster MAXIMALEMENT disjoint (seed = meilleure exp)
    seed = max(names, key=lambda n: sims[n]['exp'])
    roster = [seed]
    while len(roster) < 5:
        best, bov = None, 1e9
        for c in names:
            if c in roster: continue
            mx = max(M.loc[c, r] for r in roster)       # pire recoupement avec le roster
            if mx < bov: bov, best = mx, c
        if best is None: break
        roster.append(best)
    print(f"\n########## ROSTER DIVERSIFIÉ (glouton, overlap min) ##########")
    for n in roster:
        print(f"  {n:<26} n={sims[n]['n']:>3} {sims[n]['trj']:.1f}/j exp={sims[n]['exp']:+.2f}% cpte={sims[n]['cpte']:+.1f}%", flush=True)
    # portefeuille combiné du roster (union, 1/ticker/jour)
    # (re-simuler pour récupérer les P&L : on reconstruit à partir des ensembles n'est pas suffisant,
    #  donc on affiche juste les overlaps internes)
    inter = [M.loc[a, b] for a, b in itertools.combinations(roster, 2)]
    print(f"  -> overlap interne moyen {np.mean(inter):.0f}% (max {max(inter):.0f}%)", flush=True)
    M.to_csv(os.path.join(HERE, '..', 'results', 'strategy_ticker_overlap.csv'))
    print("\nCSV: results/strategy_ticker_overlap.csv", flush=True)


if __name__ == '__main__':
    main()
