#!/usr/bin/env python3
"""SÉLECTIVITÉ CAUSALE : réduire le nb de trades SANS tuer la qualité (exp/tr), via des conditions
connues À L'ENTRÉE (pas de look-ahead). Simule une fois (features causales enregistrées), puis :
  (1) analyse par QUINTILE de chaque feature -> est-ce que exp/tr MONTE avec la feature ?
  (2) pour les meilleures features, courbe "garder >= seuil" : nb/j -> exp/tr -> t -> CPTE -> OOS.
On cherche une condition où, en durcissant, exp/tr augmente ET le CPTE remonte (positions regrossissent).
⚠️ live only, in-sample 23 j, hypothèses. collected_live uniquement."""
import os, sys
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(HERE)))))
from research.live_lab import backtest as bt
from research.live_lab.leaderboard import portfolio
from research.indicator_lab import engine as E

TRAIL = dict(exit_mode='trail', activate_pct=0.10, trail_pct=0.02)
STRATS = {
    'bb_breakout':  dict(entry_start=570, entry_end=630, rvol_min=1.0, **TRAIL),
    'vwap_reclaim': dict(entry_start=570, entry_end=630, rvol_min=1.0, **TRAIL),
}
FEATURES = ['rvol', 'dist_vwap', 'break_bb', 'atr_pct', 'macd_hist', 'stoch_k', 'roc',
            'gap', 'float_rot', 'rsi', 'entry_min']


def main():
    groups, dates = bt.load_groups()
    liq = E.liquid_groups(groups)
    split = bt.oos_split(dates); tdays = [d for d in dates if split and d >= split]
    nd = len(dates)
    for name, P in STRATS.items():
        t = E.simulate(liq, name, P)
        t = t.dropna(subset=['pnl'])
        base_exp = t.pnl.mean(); base_n = len(t); base_trj = base_n / t.date.nunique()
        cp0, _ = portfolio(t, 0.02, 0.10)
        print("=" * 78)
        print(f"{name.upper()} — base : n={base_n} ({base_trj:.1f}/j) exp={base_exp:+.2f}% CPTE={cp0:+.1f}%")

        # (1) QUINTILES : exp/tr par tranche de chaque feature (monotonie = trieur de qualité)
        print("\n(1) exp/tr par QUINTILE de feature (Q1=bas … Q5=haut). ↑ de Q1→Q5 = trie la qualité :")
        print(f"    {'feature':<11} {'Q1':>7} {'Q2':>7} {'Q3':>7} {'Q4':>7} {'Q5':>7}   spread(Q5-Q1)")
        scorers = []
        for f in FEATURES:
            s = t[f].dropna()
            if s.nunique() < 5:
                continue
            try:
                q = pd.qcut(t[f], 5, labels=False, duplicates='drop')
            except ValueError:
                continue
            means = t.groupby(q).pnl.mean()
            vals = [means.get(k, np.nan) for k in range(5)]
            spread = (vals[-1] - vals[0]) if not (np.isnan(vals[-1]) or np.isnan(vals[0])) else np.nan
            cells = ' '.join(f"{v:+7.2f}" if not np.isnan(v) else f"{'—':>7}" for v in vals)
            print(f"    {f:<11} {cells}   {spread:+.2f}")
            if not np.isnan(spread):
                scorers.append((spread, f))

        # (2) COURBE de sélectivité sur les 2 meilleures features (par spread Q5-Q1)
        scorers.sort(reverse=True)
        print(f"\n(2) Courbe 'garder les trades avec feature >= seuil' (meilleures features : "
              f"{', '.join(f for _, f in scorers[:2])}) :")
        for _, f in scorers[:2]:
            print(f"\n  ── {f} ──   (garde feature >= percentile p)")
            print(f"    {'p':>4} {'seuil':>8} {'n':>5} {'/j':>5} {'exp':>7} {'t':>6} {'win':>5} {'OOS':>7} {'CPTE':>7} {'maxDD':>7}")
            for p in [0, 50, 70, 80, 90, 95]:
                thr = np.nanpercentile(t[f], p)
                sub = t[t[f] >= thr]
                if len(sub) < 10:
                    continue
                pnl = sub.pnl.to_numpy(); n = len(pnl); sd = pnl.std(ddof=1) if n > 1 else 0
                tt = pnl.mean() / (sd / np.sqrt(n)) if sd > 0 else 0
                oos = sub[sub.date >= split].pnl
                cp, dd = portfolio(sub, 0.02, 0.10)
                print(f"    {p:>4} {thr:>8.2f} {n:>5} {n/sub.date.nunique():>5.1f} "
                      f"{pnl.mean():>+7.2f} {tt:>6.2f} {(pnl>0).mean()*100:>4.0f}% "
                      f"{oos.mean() if len(oos) else 0:>+7.2f} {cp:>+7.1f} {dd:>+7.1f}")
        print()


if __name__ == '__main__':
    main()
