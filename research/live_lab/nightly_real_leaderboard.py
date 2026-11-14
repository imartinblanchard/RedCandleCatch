#!/usr/bin/env python3
"""Leaderboard NIGHTLY sur l'univers RÉEL (aligné live) : charge data/collected_live/
bars_eligible-*.parquet (ce que le bot voit vraiment, cf bot/fetch_eligible_bars.py), applique
exclusions + filtre PM-liq déployé, teste chaque stratégie, classe par CPTE + robustesse.
Évolue à chaque soir à mesure que les données réelles s'accumulent -> on sait quelles stratégies
gagnent À LONG TERME sur le VRAI univers (pas sur le sous-ensemble universe.json des stats).

Réutilise le moteur price_lab (engine.simulate/evaluate) — aucune logique dupliquée.
NE TOUCHE PAS aux stats existantes : fichiers séparés.
Sortie : research/live_lab/results/leaderboard_real-latest.csv  (écrasé, = état courant)
         research/live_lab/results/leaderboard_real-history.csv  (append daté, = évolution)

Usage : python -m research.live_lab.nightly_real_leaderboard [--thr 0.35]
"""
import os, sys, glob, json, argparse
from datetime import datetime
from zoneinfo import ZoneInfo
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
from research.live_lab import backtest as bt
from research.price_lab import engine as E, signals as S

ET = ZoneInfo('America/New_York')
DATA = bt.DATA
PM_LO, PM_HI = 480, 570
RES = os.path.join(HERE, 'results')

# Stratégies testées (déployées + archétypes price-only). Chacune : (nom_signal, params).
CONFIGS = {
    'rsi_bounce 3-10 tp20/s8':  ('rsi_bounce', dict(gap_min=3, gap_max=10, entry_start=570, entry_end=720, rsi_lo=20, exit_mode='tp', tp_pct=0.20, stop_pct=0.08)),
    'rsi_bounce 3-10 tp15/s8':  ('rsi_bounce', dict(gap_min=3, gap_max=10, entry_start=570, entry_end=720, rsi_lo=20, exit_mode='tp', tp_pct=0.15, stop_pct=0.08)),
    'rsi_bounce 3-10 eod/s8':   ('rsi_bounce', dict(gap_min=3, gap_max=10, entry_start=570, entry_end=720, rsi_lo=20, exit_mode='eod', stop_pct=0.08)),
    'ema9_pullback 3-10 tp20':  ('ema9_pullback', dict(gap_min=3, gap_max=10, entry_start=570, entry_end=720, exit_mode='tp', tp_pct=0.20, stop_pct=0.08)),
    'macd_cross 3-10 tp20':     ('macd_cross', dict(gap_min=3, gap_max=10, entry_start=570, entry_end=720, exit_mode='tp', tp_pct=0.20, stop_pct=0.08)),
    'orb_breakout 3-10 tp20':   ('orb_breakout', dict(gap_min=3, gap_max=10, entry_start=570, entry_end=720, exit_mode='tp', tp_pct=0.20, stop_pct=0.08)),
    'rsi_divergence 3-10 tp20': ('rsi_divergence', dict(gap_min=3, gap_max=10, entry_start=570, entry_end=720, exit_mode='tp', tp_pct=0.20, stop_pct=0.08)),
}


def load_eligible_groups():
    """Comme bt.load_groups mais sur bars_eligible-*.parquet + meta_eligible-*.json (univers réel)."""
    barfiles = sorted(glob.glob(os.path.join(DATA, 'bars_eligible-*.parquet')))
    if not barfiles:
        print("❌ aucun bars_eligible-*.parquet — lance d'abord: python -m bot.fetch_eligible_bars")
        sys.exit(1)
    meta_by_td = {}
    for mf in glob.glob(os.path.join(DATA, 'meta_eligible-*.json')):
        day = os.path.basename(mf)[len('meta_eligible-'):-5]
        try:
            for tk, m in json.load(open(mf)).items():
                meta_by_td[(tk, day)] = m
        except Exception:
            continue
    df = pd.concat([pd.read_parquet(f) for f in barfiles], ignore_index=True).drop_duplicates(['ticker', 'date', 'datetime'])
    groups = []
    for (tk, date), g in df.groupby(['ticker', 'date'], sort=False):
        m = meta_by_td.get((tk, date), {})
        pc = m.get('prev_close')
        if not pc or pc <= 0:
            continue
        g = g.sort_values('datetime')
        mins = (g['datetime'].str.slice(0, 2).astype(int) * 60 + g['datetime'].str.slice(3, 5).astype(int)).to_numpy()
        o, h, l, c, v = (g[k].to_numpy(float) for k in ('o', 'h', 'l', 'c', 'v'))
        groups.append(dict(tk=tk, date=date, pc=float(pc), mins=mins, o=o, h=h, l=l, c=c, v=v,
                           float_shares=m.get('float_shares'), inst_pct=m.get('inst_pct'),
                           band=m.get('band'), first_seen=m.get('added')))
    dates = sorted({g['date'] for g in groups})
    return groups, dates


def pm_liquid(groups, thr):
    """Filtre PM-liq calculé DIRECTEMENT depuis les bars (== bot live), + exclusions split/acquisition."""
    ex = E.excluded_set()
    out = []
    for g in groups:
        if (g['tk'], g['date']) in ex:
            continue
        pm = sum(1 for mn, vv in zip(g['mins'], g['v']) if PM_LO <= mn < PM_HI and vv > 0)
        if pm / (PM_HI - PM_LO) >= thr:
            out.append(g)
    return out


def main(thr):
    groups, dates = load_eligible_groups()
    liq = pm_liquid(groups, thr)
    split = bt.oos_split(dates)
    print(f"univers RÉEL : {len(groups)} ticker-jours ({len(dates)} séances) | PM-liq>={thr:.0%}: {len(liq)} | OOS {split}")
    rows = []
    for label, (sig, P) in CONFIGS.items():
        df = E.simulate(liq, sig, P)
        r = E.evaluate(df, dates, split, stop_pct=P.get('stop_pct', 0.08))
        if not r:
            continue
        r['robust'] = bool(r['e_h1'] > 0 and r['e_h2'] > 0 and r['t'] >= 2 and r['cpte'] > 0)
        rows.append(dict(strategie=label, **{k: r[k] for k in
                     ['n', 'trj', 'exp', 't', 'win', 'entry_med', 'cpte', 'cpte_oos', 'e_h1', 'e_h2', 'maxDD', 'robust']}))
    res = pd.DataFrame(rows).sort_values('cpte', ascending=False)
    os.makedirs(RES, exist_ok=True)
    res.to_csv(os.path.join(RES, 'leaderboard_real-latest.csv'), index=False)
    # historique daté (évolution soir après soir)
    today = datetime.now(ET).date().isoformat()
    snap = res.assign(asof=today)
    hp = os.path.join(RES, 'leaderboard_real-history.csv')
    snap.to_csv(hp, mode='a', header=not os.path.exists(hp), index=False)
    print(f"-> leaderboard_real-latest.csv ({len(res)} strat) + history ({today})\n")
    print(res.to_string(index=False))


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--thr', type=float, default=0.35, help='seuil PM-liq (défaut = déployé 0.35)')
    a = ap.parse_args()
    main(a.thr)
