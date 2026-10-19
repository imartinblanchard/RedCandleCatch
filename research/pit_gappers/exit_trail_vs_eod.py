#!/usr/bin/env python3
"""trail 10/2 vs hold-to-EOD sur le GROS dataset point-in-time (pit_gappers), OOS.

Motivation (19/10) : sur les 15 séances live, la variante « sortie trail 10/2 »
bat notre hold-to-EOD (OOS +3,1 %/tr vs +0,8). 15 jours = bruit. On re-teste la
MÊME question sur pit_gappers (~165 jours, jan→août 2026) avec le MOTEUR LIVE EXACT
(research/live_lab/backtest.simulate + config LIVE) : seule la SORTIE change,
l'entrée (repli 8 % + capitulation + run-up + gap-open, gap 5-10) est identique.

Entrées identiques entre les deux sorties => comparaison APPARIÉE (même trade,
pnl_eod vs pnl_trail) = test le plus puissant.
"""
import os, sys, glob, json
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)
from research.live_lab import backtest as bt   # moteur live exact

DATA = os.path.join(HERE, 'data')
BARS = os.path.join(DATA, 'bars')
SPLIT = '2026-05-01'                             # convention OOS du rebuild pit


def load_pit_groups():
    """Construit les groupes au format backtest.load_groups() depuis les bars pit + candidates.json."""
    pc_map = {f"{x['ticker']}|{x['date']}": x['prev_close']
              for x in json.load(open(os.path.join(DATA, 'candidates.json')))}
    groups = []
    for path in sorted(glob.glob(os.path.join(BARS, '*.parquet'))):
        df = pd.read_parquet(path).drop_duplicates(['ticker', 'date', 'datetime'])
        for (tk, date), g in df.groupby(['ticker', 'date'], sort=False):
            pc = pc_map.get(f"{tk}|{date}")
            if not pc or pc <= 0:
                continue
            g = g.sort_values('datetime')
            mins = (g['datetime'].str.slice(0, 2).astype(int) * 60 +
                    g['datetime'].str.slice(3, 5).astype(int)).to_numpy()
            o, h, l, c, v = (g[k].to_numpy(float) for k in ('o', 'h', 'l', 'c', 'v'))
            groups.append(dict(tk=tk, date=date, pc=float(pc), mins=mins, o=o, h=h, l=l, c=c, v=v,
                               float_shares=None, inst_pct=None, band=None, first_seen=None))
    dates = sorted({g['date'] for g in groups})
    return groups, dates


def seg(t, lo=None, hi=None):
    if lo is not None:
        t = t[t.date >= lo]
    if hi is not None:
        t = t[t.date < hi]
    return t


def paired(te, tt, label):
    """Delta apparié pnl_trail - pnl_eod sur les trades communs (même ticker-jour-entrée)."""
    m = te.merge(tt, on=['ticker', 'date', 'entry_min'], suffixes=('_eod', '_trail'))
    d = (m.pnl_trail - m.pnl_eod).to_numpy()
    n = len(d)
    if n < 2:
        print(f"  {label:<14} n={n} (trop peu)")
        return
    mean = d.mean(); sd = d.std(ddof=1)
    tstat = mean / (sd / np.sqrt(n)) if sd > 0 else 0.0
    wins = (d > 0).mean() * 100
    print(f"  {label:<14} n={n:>4}  Δ(trail−eod)={mean:>+6.3f}%  t={tstat:>+5.2f}  "
          f"trail>eod sur {wins:>3.0f}% des trades")


def main():
    print("Chargement des groupes pit_gappers…")
    groups, dates = load_pit_groups()
    print(f"{len(groups)} ticker-jours, {len(dates)} séances ({dates[0]} → {dates[-1]}), split OOS ≥ {SPLIT}\n")

    P_eod = dict(bt.LIVE)                                   # hold-to-EOD + stop (config LIVE)
    P_trail = dict(bt.LIVE, exit_mode='trail', activate_pct=0.10, trail_pct=0.02)

    t_eod = bt.simulate(groups, P_eod, slip=True)
    t_trail = bt.simulate(groups, P_trail, slip=True)

    print(f"Entrées détectées : {len(t_eod)} (identiques pour les deux sorties)\n")
    print("══ EXPECTANCY PAR SORTIE (moteur live exact, slippage ON) ══")
    for name, lo, hi in [('FULL', None, None), ('TRAIN (<split)', None, SPLIT), ('TEST OOS (≥split)', SPLIT, None)]:
        se = bt.stat(seg(t_eod, lo, hi).pnl.to_numpy())
        st = bt.stat(seg(t_trail, lo, hi).pnl.to_numpy())
        print(f"\n[{name}]")
        print(f"  hold-to-EOD : {bt.fmt(se)}")
        print(f"  trail 10/2  : {bt.fmt(st)}")

    print("\n══ COMPARAISON APPARIÉE (Δ par trade = trail − eod) ══")
    paired(t_eod, t_trail, 'FULL')
    paired(seg(t_eod, None, SPLIT), seg(t_trail, None, SPLIT), 'TRAIN')
    paired(seg(t_eod, SPLIT, None), seg(t_trail, SPLIT, None), 'TEST OOS')


if __name__ == '__main__':
    main()
