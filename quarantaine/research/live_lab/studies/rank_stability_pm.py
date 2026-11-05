#!/usr/bin/env python3
"""Classe les candidates PM-causales par STABILITÉ (pas par CPTE max).
Re-simule chaque candidate robuste et calcule : win%, maxDD, écart-type/tr, pire trade,
écart |h1-h2| (régularité), e_trim (non-fragile), OOS, CPTE. Préférence Martin = stabilité."""
import os, sys
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(HERE))))
from research.live_lab import backtest as bt
from research.live_lab.leaderboard import portfolio

RES = os.path.join(HERE, '..', 'results', 'strategy_search_liquid_pm_results.csv')
UNIV_CSV = os.path.join(HERE, '..', 'results', 'liquid_universe_pm.csv')
UCOL = {'near02': ('near_frac', 0.2), 'near03': ('near_frac', 0.3),
        'latepm02': ('latepm_frac', 0.2), 'latepm03': ('latepm_frac', 0.3)}
STARTS = {'9:30': 570, '10:00': 600, '10:30': 630}
ENDS = {'midi': 720, '15:55': 955}


def build_P(row):
    P = dict(bt.LIVE)
    gmin, gmax = (float(x) for x in row['gap'].split('-'))
    esl, eel = row['heures'].split('>')
    P.update(gap_min=gmin, gap_max=gmax, entry_start=STARTS[esl], entry_end=ENDS[eel],
             retrace_pct=float(row['repli']), capit_ratio=float(row['capit']),
             hod_in_rth='hodRTH' in row['indic'], require_green='green' in row['indic'],
             vwap_side='below' if 'vw<' in row['indic'] else None, recent_active_min=0.0)
    s = row['sortie']
    if s == 'eod': P.update(exit_mode='eod')
    elif s == 'tp20': P.update(exit_mode='tp', tp_pct=0.20)
    elif s == 'trail10/2': P.update(exit_mode='trail', activate_pct=0.10, trail_pct=0.02)
    return P


def main():
    r = pd.read_csv(RES)
    bal = r[r.robust & (r.e_h1 >= 0.8) & (r.e_h2 >= 0.8) & (r.e_te >= 0.8) & (r.t >= 2.3)]
    bal = bal.drop_duplicates(subset=['univ', 'gap', 'heures', 'repli', 'capit', 'sortie', 'indic'])
    groups, dates = bt.load_groups()
    split = bt.oos_split(dates); tdays = [d for d in dates if split and d >= split]
    mid = dates[len(dates) // 2]
    TY = 252                                        # jours de bourse/an (annualisation linéaire, comparabilité)
    nd_full, nd_oos = len(dates), max(len(tdays), 1)
    u = pd.read_csv(UNIV_CSV)
    out = []
    for _, row in bal.iterrows():
        col, thr = UCOL[row['univ']]
        uset = set(zip(u[u[col] >= thr].ticker, u[u[col] >= thr].date))
        g_use = [g for g in groups if (g['tk'], g['date']) in uset]
        P = build_P(row)
        t = bt.simulate(g_use, P, slip=True)
        if not len(t): continue
        pnl = t.pnl.to_numpy(); n = len(pnl)
        win = (pnl > 0).mean() * 100
        std = pnl.std(ddof=1)
        worst = pnl.min()
        h1 = t[t.date < mid].pnl.mean(); h2 = t[t.date >= mid].pnl.mean()
        consist = abs(h1 - h2)                          # écart entre moitiés (bas = régulier)
        srt = np.sort(pnl)
        e_trim = srt[:-3].mean() if n > 3 else pnl.mean()          # retire les 3 MEILLEURS (fragilité)
        trimBW = srt[1:-1].mean() if n > 2 else pnl.mean()         # retire le PIRE + le MEILLEUR
        trim2 = srt[2:-2].mean() if n > 4 else pnl.mean()          # retire 2 pires + 2 meilleurs
        cpte, dd = portfolio(t, 0.02, P['stop_pct'])
        cpte_o, dd_o = portfolio(t, 0.02, P['stop_pct'], days=tdays)
        out.append(dict(univ=row['univ'], gap=row['gap'], heures=row['heures'], repli=row['repli'],
                        sortie=row['sortie'], indic=row['indic'], n=n, trj=round(n / t.date.nunique(), 1),
                        exp=round(pnl.mean(), 2), t=round(row['t'], 2), pf=round(row['pf'], 1),
                        win=round(win), std=round(std, 1), worst=round(worst, 1),
                        h1=round(h1, 2), h2=round(h2, 2), dHalf=round(consist, 2),
                        e_trim=round(e_trim, 2), trimBW=round(trimBW, 2), trim2=round(trim2, 2),
                        oos=round(row['e_te'], 2),
                        maxDD=round(dd, 1), cpte=round(cpte, 1), cpte_oos=round(cpte_o, 1),
                        cpte_ann=round(cpte * TY / nd_full), cpte_oos_ann=round(cpte_o * TY / nd_oos)))
    d = pd.DataFrame(out)
    cols = ['univ', 'gap', 'heures', 'repli', 'sortie', 'indic', 'n', 'trj', 'exp', 'win', 'pf',
            'worst', 'dHalf', 'e_trim', 'oos', 'maxDD', 'cpte', 'cpte_ann', 'cpte_oos', 'cpte_oos_ann']
    print("\n########## PAR CPTE (rendement) ##########")
    print(d.sort_values('cpte', ascending=False)[cols].to_string(index=False))
    print(f"\nLEGENDE: e_trim=sans les 3 MEILLEURS | dHalf=|h1-h2| (bas=regulier) | maxDD=pire drawdown")
    print(f"  cpte=% compte sur {nd_full} jours | cpte_oos=sur {nd_oos} jours OOS | *_ann=annualisé x252/jours")
    print(f"  ⚠️ annualisé = extrapolation LINÉAIRE pour comparer IS/OOS — PAS une promesse (petit n, backtest optimiste)")
    d.to_csv(os.path.join(HERE, '..', 'results', 'rank_stability_pm.csv'), index=False)


if __name__ == '__main__':
    main()
