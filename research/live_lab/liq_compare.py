#!/usr/bin/env python3
"""ÉTAPE 2 — teste si la LIQUIDITÉ GLISSANTE À L'ENTRÉE (act_30/dvol_30, par bougie) bat la
méthode actuelle (fréquence PM 8:00-9:30 fixe, une valeur/jour). Même stratégie (rsi_bounce 3-10),
univers LARGE (bars-*.parquet). Classe par CPTE + robustesse. But : décider AVANT de toucher au bot.

Méthodes comparées :
  A. ACTUEL    : filtre PM-matin pm_frac >= 0.35, pas de gate à l'entrée
  B. NOUVEAU   : aucun filtre PM, gate liquidité À L'ENTRÉE (act_30 >= seuil)
  C. NOUVEAU   : idem avec dvol_30 >= seuil ($)
  D. COMBINÉ   : PM-matin 0.35 ET gate à l'entrée

Usage : python -m research.live_lab.liq_compare
"""
import os, sys
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
from research.live_lab import backtest as bt
from research.price_lab import engine as E

PM_LO, PM_HI = 480, 570
P0 = dict(gap_min=3, gap_max=10, entry_start=570, entry_end=720, rsi_lo=20,
          exit_mode='tp', tp_pct=0.20, stop_pct=0.08)


def pm_frac_groups(groups, thr):
    out = []
    for g in groups:
        pm = sum(1 for mn, vv in zip(g['mins'], g['v']) if PM_LO <= mn < PM_HI and vv > 0) / (PM_HI - PM_LO)
        if pm >= thr:
            out.append(g)
    return out


def run(groups, dates, split, label, P):
    df = E.simulate(groups, 'rsi_bounce', P)
    r = E.evaluate(df, dates, split, stop_pct=P.get('stop_pct', 0.08))
    if not r:
        return dict(methode=label, n=0)
    return dict(methode=label, n=r['n'], trj=r['trj'], exp=r['exp'], t=r['t'], win=r['win'],
                cpte=r['cpte'], oos=r['cpte_oos'], h1=r['e_h1'], h2=r['e_h2'], maxDD=r['maxDD'])


def main():
    groups, dates = bt.load_groups()
    ex = E.excluded_set()
    groups = [g for g in groups if (g['tk'], g['date']) not in ex]
    split = bt.oos_split(dates)
    pm035 = pm_frac_groups(groups, 0.35)
    rows = []
    # A. ACTUEL : PM-matin 0.35
    rows.append(run(pm035, dates, split, 'A. PM-matin 0.35 (ACTUEL)', P0))
    # B. NOUVEAU : act_30 à l'entrée (sans PM), plusieurs seuils
    for a in (5, 10, 15, 20):
        rows.append(run(groups, dates, split, f'B. act_30>={a} à l_entrée', {**P0, 'liq_col': 'act_30', 'liq_min': a}))
    # C. NOUVEAU : dvol_30 à l'entrée (sans PM)
    for d in (50_000, 100_000, 200_000, 500_000):
        rows.append(run(groups, dates, split, f'C. dvol_30>=${d//1000}K à l_entrée', {**P0, 'liq_col': 'dvol_30', 'liq_min': d}))
    # D. COMBINÉ : PM 0.35 + act_30 à l'entrée
    for a in (10, 15):
        rows.append(run(pm035, dates, split, f'D. PM0.35 + act_30>={a}', {**P0, 'liq_col': 'act_30', 'liq_min': a}))
    res = pd.DataFrame(rows)
    res.to_csv(os.path.join(HERE, 'results', 'liq_compare.csv'), index=False)
    print(f"univers large : {len(groups)} ticker-jours, {len(dates)} séances, OOS {split}\n")
    print(res.to_string(index=False))


if __name__ == '__main__':
    main()
