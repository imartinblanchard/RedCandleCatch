#!/usr/bin/env python3
"""Portefeuille MULTI-STRATÉGIES + filtre d'activité. Live only.

Idée Martin : le filtre d'activité (recent_active) améliore la QUALITÉ/trade mais coupe le
VOLUME. Donc : combiner PLUSIEURS stratégies filtrées-activité (peu corrélées) pour remonter
à ~5 trades/jour -> garder la qualité ET le volume. On teste le portefeuille combiné AVEC vs
SANS filtre d'activité, vs le meilleur single. Union des trades (1/ticker/jour), sizing compte.
collected_live uniquement.
"""
import os, sys
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(HERE))))
from research.live_lab import backtest as bt
from research.live_lab.leaderboard import portfolio, EXPCAP, POSCAP, MAXPOS

TRAIL = dict(exit_mode='trail', activate_pct=0.10, trail_pct=0.02)
# stratégies choisies pour se COMPLÉTER (gaps/heures/replis différents)
STRATS = {
    'A 5-10/9:30/r8/capit2/hodRTH':   dict(gap_min=5, gap_max=10, entry_start=570, retrace_pct=0.08, capit_ratio=2.0, hod_in_rth=True, **TRAIL),
    'B 5-50/10:30/r12/noCapit/hodRTH': dict(gap_min=5, gap_max=50, entry_start=630, retrace_pct=0.12, capit_ratio=-1, hod_in_rth=True, **TRAIL),
    'C 5-50/10:00/r10/noCapit/green':  dict(gap_min=5, gap_max=50, entry_start=600, retrace_pct=0.10, capit_ratio=-1, require_green=True, hod_in_rth=True, **TRAIL),
    'D 10-20/9:30/r10/noCapit':        dict(gap_min=10, gap_max=20, entry_start=570, retrace_pct=0.10, capit_ratio=-1, hod_in_rth=True, **TRAIL),
}
RA = 0.7   # niveau d'activité récente (fraction des 10 dern. min avec trade)


def trades_of(groups, upd, ra):
    P = dict(bt.LIVE); P.update(upd); P['recent_active_min'] = ra; P['recent_active_window'] = 10
    t = bt.simulate(groups, P, slip=True)
    return t[['ticker', 'date', 'entry_min', 'pnl']].copy() if len(t) else pd.DataFrame(columns=['ticker', 'date', 'entry_min', 'pnl'])


def combine(dfs):
    """Union des trades, 1 seul par (ticker, date) [garde la 1re entrée du jour]."""
    allt = pd.concat(dfs, ignore_index=True)
    if not len(allt):
        return allt
    return allt.sort_values('entry_min').drop_duplicates(['ticker', 'date'], keep='first')


def report(t, label, split, tdays):
    if not len(t):
        print(f"  {label:<34} 0 trade"); return
    s = bt.stat(t.pnl.to_numpy()); trj = len(t) / t.date.nunique()
    so = bt.stat(t[t.date >= split].pnl.to_numpy()) if split else s
    p2, _ = portfolio(t, 0.02, 0.10); p2o, _ = portfolio(t, 0.02, 0.10, days=tdays)
    print(f"  {label:<34} n={s['n']:>3} {trj:>4.1f}/j exp={s['exp']:>+5.2f}% t={s['t']:>+5.2f} "
          f"win={s['win']:>3.0f}% | OOS {so['exp']:>+5.2f}% | CPTE {p2:>+6.1f}% / OOS {p2o:>+5.1f}%")


def main():
    groups, dates = bt.load_groups()
    split = bt.oos_split(dates); tdays = [d for d in dates if split and d >= split]
    print(f"{len(dates)} séances, OOS≥{split}. recent_active={RA}. sizing 2%, trail, hold->cloture.\n")

    for ra, tag in [(0.0, 'SANS filtre activité'), (RA, f'AVEC filtre activité (>={RA})')]:
        print(f"########## {tag} ##########")
        dfs = {name: trades_of(groups, upd, ra) for name, upd in STRATS.items()}
        print("-- stratégies individuelles --")
        for name, t in dfs.items():
            report(t, name, split, tdays)
        comb = combine(list(dfs.values()))
        print("-- PORTEFEUILLE COMBINÉ (union, 1/ticker/jour) --")
        report(comb, 'COMBINÉ A+B+C+D', split, tdays)
        if len(comb):
            # chevauchement : combien de doublons retirés
            tot = sum(len(t) for t in dfs.values())
            print(f"     (trades bruts {tot} -> {len(comb)} après dédup ticker/jour ; chevauchement {tot-len(comb)})")
        print()


if __name__ == '__main__':
    main()
