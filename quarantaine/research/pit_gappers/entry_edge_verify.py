#!/usr/bin/env python3
"""Vérif anti-artefact de l'edge « repli nu » (sans filtres anti-couteau).

L'ablation (21/10) montre : repli 8% + gap 5-10 + hold-EOD, SANS capit/dvol/run-up/gap-open
= +1,24%/tr (t=10,8), OOS +1,45% (t=9,0), n=4156. Trop beau -> on vérifie que ce n'est
pas un artefact (ce repo a déjà été piégé par un look-ahead, cf lookahead-postopen-invalide).

Tests : (1) stabilité mois par mois, (2) fragilité aux méga-gagnants (trim top 1%),
(3) survie à un coût réaliste, (4) concentration par prix & heure, (5) distribution.
Moteur live exact, slippage ON. Config = bt.LIVE sans les 4 filtres anti-couteau.
"""
import os, sys
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
from research.live_lab import backtest as bt
from research.pit_gappers.exit_trail_vs_eod import load_pit_groups

SPLIT = '2026-05-01'
BARE = dict(bt.LIVE, capit_ratio=-1, pullback_dvol_min=0, runup_min=0, gap_open_min=None)


def st(a):
    a = np.asarray(a, float); n = len(a)
    if n < 2: return (n, float('nan'), float('nan'))
    e = a.mean(); t = e / (a.std(ddof=1) / np.sqrt(n)) if a.std(ddof=1) > 0 else 0
    return (n, e, t)


def main():
    print("Chargement…")
    groups, dates = load_pit_groups()
    t = bt.simulate(groups, BARE, slip=True)
    t = t.sort_values('date').reset_index(drop=True)
    t['month'] = t.date.str.slice(0, 7)
    p = t.pnl.to_numpy()
    print(f"Config « repli nu » : n={len(t)}, FULL exp={p.mean():+.2f}% t={st(p)[2]:+.2f}\n")

    print("=== (1) STABILITÉ MOIS PAR MOIS ===")
    for m, g in t.groupby('month'):
        n, e, tt = st(g.pnl.to_numpy())
        print(f"  {m} : n={n:>4} exp={e:>+5.2f}% t={tt:>+5.2f}")

    print("\n=== (2) FRAGILITÉ AUX EXTRÊMES ===")
    print(f"  mean={p.mean():+.2f}%  médiane={np.median(p):+.2f}%  win={(p>0).mean()*100:.0f}%")
    hi = np.sort(p)[::-1]
    for k in [1, 5, 10]:
        cut = int(len(p) * k / 100)
        trimmed = np.sort(p)[: len(p) - cut]          # retire les k% MEILLEURS
        n, e, tt = st(trimmed)
        print(f"  sans les {k}% meilleurs trades ({cut}) : exp={e:>+5.2f}% t={tt:>+5.2f}")

    print("\n=== (3) SURVIE AUX COÛTS (haircut par trade, slippage déjà inclus) ===")
    for cost in [0.2, 0.5, 1.0]:
        n, e, tt = st(p - cost)
        oo = t[t.date >= SPLIT].pnl.to_numpy() - cost
        _, eo, to = st(oo)
        print(f"  −{cost:.1f}%/trade : FULL exp={e:>+5.2f}% t={tt:>+5.2f} | OOS exp={eo:>+5.2f}% t={to:>+5.2f}")

    print("\n=== (4) CONCENTRATION PAR PRIX ===")
    t['pxb'] = pd.cut(t.entry, [0, 5, 10, 20, 999], labels=['3-5', '5-10', '10-20', '20+'])
    for b, g in t.groupby('pxb', observed=True):
        n, e, tt = st(g.pnl.to_numpy())
        print(f"  {b:<6} : n={n:>4} exp={e:>+5.2f}% t={tt:>+5.2f}")

    print("\n=== (4b) CONCENTRATION PAR HEURE D'ENTRÉE ===")
    for h, g in t.groupby('hour'):
        n, e, tt = st(g.pnl.to_numpy())
        print(f"  {int(h):02d}h : n={n:>4} exp={e:>+5.2f}% t={tt:>+5.2f}")

    print("\n=== (5) TRAIN vs TEST (rappel) ===")
    for lbl, seg in [('TRAIN <split', t[t.date < SPLIT]), ('TEST OOS ≥split', t[t.date >= SPLIT])]:
        n, e, tt = st(seg.pnl.to_numpy())
        print(f"  {lbl:<16} n={n:>4} exp={e:>+5.2f}% t={tt:>+5.2f}")


if __name__ == '__main__':
    main()
