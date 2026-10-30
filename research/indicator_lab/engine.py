#!/usr/bin/env python3
"""Moteur de backtest pour les entrées PAR INDICATEURS. Réutilise live_lab pour TOUT ce qui
n'est pas l'entrée : chargement des données (bt.load_groups), sortie/P&L (bt._pnl), split OOS,
et le sizing portefeuille (leaderboard.portfolio). Seul le DÉCLENCHEUR change (signals.py).

simulate(groups, signal_name, P, slip) -> DataFrame de trades (1/ticker-jour, one-shot).
P contient : gardes de base (price_min/max, gap_min/max, entry_start/end), params du signal,
et params de sortie (exit_mode, stop_pct, activate_pct, trail_pct, tp_pct, eod).
"""
import os, sys
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(HERE))))
from research.live_lab import backtest as bt
from research.live_lab.leaderboard import portfolio
from . import indicators as I
from . import signals as S

_CACHE = {}
_PM = os.path.join(os.path.dirname(HERE), 'live_lab', 'results', 'liquid_universe_pm.csv')


def _ind(g):
    key = (g['tk'], g['date'])
    if key not in _CACHE:
        _CACHE[key] = I.compute(g)
    return _CACHE[key]


def liquid_groups(groups, col='latepm_frac', thr=0.20):
    """Restreint l'univers aux ticker-jours qui passent le FILTRE DE FRÉQUENCE pré-marché
    (causal, = le filtre déployé live). latepm_frac>=0.20 : actif >=20% des min 8:00-9:30.
    C'est l'univers des titres réellement tradables en live (tous gaps confondus)."""
    u = pd.read_csv(_PM)
    keep = set(zip(u[u[col] >= thr].ticker, u[u[col] >= thr].date))
    return [g for g in groups if (g['tk'], g['date']) in keep]


# gap par défaut = AUCUNE bande (tous les titres de 0 à +250%+ ; l'univers est borné par le
# filtre de fréquence, pas par le gap). price 3-20$ conservé (zone exécutable, comme le live).
# Gardes de QUALITÉ causaux (neutres par défaut) : trieurs validés par studies/selectivity.py.
DEFAULTS = dict(price_min=3.0, price_max=20.0, gap_min=-100.0, gap_max=9999.0,
                entry_start=570, entry_end=955,
                macd_hist_min=-1e9, rvol_gate=0.0, float_rot_max=1e9,   # gardes qualité (off)
                exit_mode='eod', stop_pct=0.10, activate_pct=0.10, trail_pct=0.02,
                tp_pct=0.20, eod=955)


def _entry(g, ind, fn, P):
    mins, c, gap = ind['mins'], ind['c'], ind['gap']
    win = np.where((mins >= P['entry_start']) & (mins <= P['entry_end']))[0]
    for i in win:
        if not (P['price_min'] <= c[i] <= P['price_max']):
            continue
        if not (P['gap_min'] <= gap[i] <= P['gap_max']):   # gap (sur HOD) présent à l'entrée
            continue
        # ── gardes de QUALITÉ causaux (trieurs validés) ──
        if ind['macd_hist'][i] < P.get('macd_hist_min', -1e9):
            continue
        if ind['rvol'][i] < P.get('rvol_gate', 0.0):
            continue
        fs = g.get('float_shares')
        if fs and P.get('float_rot_max', 1e9) < 1e9 and ind['cum_v'][i] / fs > P['float_rot_max']:
            continue
        if fn(ind, i, P):
            return i
    return None


def simulate(groups, signal_name, P=None, slip=True):
    fn = S.REGISTRY[signal_name]
    Q = dict(DEFAULTS); Q.update(P or {})
    rows = []
    for g in groups:
        ind = _ind(g)
        i = _entry(g, ind, fn, Q)
        if i is None:
            continue
        pnl = bt._pnl(g, i, Q, slip)
        c = float(ind['c'][i]); vw = float(ind['vwap'][i]); fs = g.get('float_shares')
        rows.append(dict(ticker=g['tk'], date=g['date'], entry_min=int(ind['mins'][i]),
                         entry_time=bt.hhmm(int(ind['mins'][i])), entry=round(c, 4),
                         signal=signal_name, pnl=round(pnl, 3),
                         # ── features CAUSALES à l'entrée (pour la recherche de sélectivité) ──
                         gap=round(float(ind['gap'][i]), 1), rsi=round(float(ind['rsi'][i]), 1),
                         rvol=round(float(ind['rvol'][i]), 2),
                         dist_vwap=round((c / vw - 1) * 100, 2) if vw > 0 else 0.0,   # % au-dessus du VWAP
                         break_bb=round((c / float(ind['bb_up'][i]) - 1) * 100, 2) if ind['bb_up'][i] > 0 else 0.0,
                         atr_pct=round(float(ind['atr'][i]) / c * 100, 2) if c > 0 else 0.0,
                         macd_hist=round(float(ind['macd_hist'][i]), 3),
                         stoch_k=round(float(ind['stoch_k'][i]), 1), roc=round(float(ind['roc'][i]), 2),
                         float_rot=round(float(ind['cum_v'][i]) / fs, 3) if fs else None,
                         hour=int(ind['mins'][i]) // 60))
    df = pd.DataFrame(rows)
    return df


def evaluate(df, dates, split, stop_pct=0.10):
    """Stats robustesse + CPTE full/OOS (+ annualisé pommes-avec-pommes)."""
    if not len(df):
        return None
    pnl = df.pnl.to_numpy(); n = len(pnl)
    tdays = [d for d in dates if split and d >= split]
    mid = dates[len(dates) // 2]
    h1 = df[df.date < mid].pnl; h2 = df[df.date >= mid].pnl
    te = df[df.date >= split].pnl if split else pnl
    sd = pnl.std(ddof=1) if n > 1 else 0
    cp, dd = portfolio(df, 0.02, stop_pct)
    cpo, _ = portfolio(df, 0.02, stop_pct, days=tdays)
    srt = np.sort(pnl)
    return dict(n=n, trj=round(n / df.date.nunique(), 1), exp=round(pnl.mean(), 2),
                t=round(pnl.mean() / (sd / np.sqrt(n)), 2) if sd > 0 else 0,
                win=round((pnl > 0).mean() * 100), pf=round(pnl[pnl > 0].sum() / (-pnl[pnl < 0].sum() or 1e-9), 1),
                e_h1=round(h1.mean(), 2) if len(h1) else 0, e_h2=round(h2.mean(), 2) if len(h2) else 0,
                e_te=round(te.mean(), 2) if len(te) else 0, n_te=len(te),
                e_trim=round(srt[:-3].mean(), 2) if n > 3 else round(pnl.mean(), 2),
                maxDD=round(dd, 1), cpte=round(cp, 1), cpte_oos=round(cpo, 1),
                cpte_ann=round(cp * 252 / len(dates)), cpte_oos_ann=round(cpo * 252 / max(len(tdays), 1)))


if __name__ == '__main__':      # smoke-test : tous archétypes, univers freq-filtré, tous gaps
    groups, dates = bt.load_groups()
    groups = liquid_groups(groups)
    split = bt.oos_split(dates)
    print(f"Univers freq-filtré (latepm>=0.20) : {len(groups)} ticker-jours, tous gaps.\n")
    for name in S.REGISTRY:
        df = simulate(groups, name)
        r = evaluate(df, dates, split)
        if r:
            print(f"{name:<15} n={r['n']:>3} {r['trj']}/j exp={r['exp']:+.2f}% t={r['t']} "
                  f"win={r['win']}% pf={r['pf']} OOS={r['e_te']:+.2f} CPTE={r['cpte']:+.1f}%")
        else:
            print(f"{name:<15} 0 trade")
