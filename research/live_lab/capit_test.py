#!/usr/bin/env python3
"""Filtre de capitulation sur grille fine — avec sizing EXPLICITE + P&L compte.

Sur NOS DONNÉES LIVE (collected_live) uniquement. Tout identique à la v3 sauf capit_ratio.
Pour chaque seuil : n, trades/jour, TAILLE DE POSITION choisie par le sizing (posfrac),
rendement/trade, t, win, pf, OOS, et % de gain sur le COMPTE à risque 2% et 1% (FULL+OOS).

Le sizing (leaderboard.portfolio) dépend du nb de trades/jour ET du risque :
    posfrac = min(risque/stop, budget(100%/j)/trades_jour, plafond 20%)
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
from research.live_lab import backtest as bt
from research.live_lab.leaderboard import portfolio, EXPCAP, POSCAP

CAPITS = [('OFF', -1), ('1.0', 1.0), ('1.2', 1.2), ('1.3(v3)', 1.3), ('1.4', 1.4),
          ('1.5', 1.5), ('1.6', 1.6), ('1.8', 1.8), ('2.0', 2.0), ('2.5', 2.5)]


def posfrac(trday, risk, stop):
    return min(risk / stop, EXPCAP / trday, POSCAP) if trday else 0


def main():
    groups, dates = bt.load_groups()
    split = bt.oos_split(dates)
    tdays = [d for d in dates if split and d >= split]
    print(f"{len(dates)} séances live ({dates[0]}→{dates[-1]}), OOS ≥ {split} ({len(tdays)} j test)")
    print("tout = v3 sauf capit ; hold-EOD, slip ON. Sizing = min(risque/stop, 100%/tr_jour, 20%).\n")
    print(f"{'capit':<9}{'n':>4}{'tr/j':>6}{'pos%@2%':>8}{'exp/tr':>8}{'t':>6}{'win':>5}{'pf':>6}"
          f" | {'OOSexp':>7}{'t':>5} | {'CPTE2%':>8}{'OOS':>7} | {'CPTE1%':>8}{'OOS':>7}")
    print('-' * 104)
    for lab, cr in CAPITS:
        P = dict(bt.LIVE); P['capit_ratio'] = cr
        t = bt.simulate(groups, P, slip=True)
        if not len(t):
            print(f"{lab:<9} 0 trade"); continue
        s = bt.stat(t.pnl.to_numpy()); trday = len(t) / t.date.nunique()
        so = bt.stat(t[t.date >= split].pnl.to_numpy()) if split else s
        pf2, _ = portfolio(t, 0.02, P['stop_pct']); pf2o, _ = portfolio(t, 0.02, P['stop_pct'], days=tdays)
        pf1, _ = portfolio(t, 0.01, P['stop_pct']); pf1o, _ = portfolio(t, 0.01, P['stop_pct'], days=tdays)
        pfr = posfrac(trday, 0.02, P['stop_pct']) * 100
        print(f"{lab:<9}{s['n']:>4}{trday:>6.1f}{pfr:>7.0f}%{s['exp']:>+7.2f}%{s['t']:>+6.2f}{s['win']:>4.0f}%{s['pf']:>6.2f}"
              f" | {so['exp']:>+6.2f}%{so['t']:>+5.2f} | {pf2:>+7.1f}%{pf2o:>+6.1f}% | {pf1:>+7.1f}%{pf1o:>+6.1f}%")
    print("\npos%@2% = taille de position (fraction du compte) choisie par le sizing à risque 2%.")
    print("CPTE2%/CPTE1% = % de gain sur le COMPTE (composé) à risque 2% / 1%, FULL puis OOS.")


if __name__ == '__main__':
    main()
