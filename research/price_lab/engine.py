#!/usr/bin/env python3
"""Moteur de backtest price-only. Réutilise le NOYAU gardé (research/live_lab/backtest.py pour les
données + _pnl/_exit_price + oos_split ; leaderboard.portfolio pour le sizing). AUCUN gate volume
(ni rvol, ni dvol, ni float_rot) : seules les gardes PRIX/GAP/FENÊTRE + l'archétype de prix décident.
L'univers reste le PM-liquidité (comptage de minutes actives = binaire, robuste au délai volume)."""
import os, sys
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
from research.live_lab import backtest as bt
from research.live_lab.leaderboard import portfolio
from . import indicators as I
from . import signals as S

_CACHE = {}
_PM = os.path.join(os.path.dirname(HERE), 'live_lab', 'results', 'liquid_universe_pm.csv')
_EXCL = os.path.join(os.path.dirname(os.path.dirname(HERE)), 'data', 'collected_live', 'excluded.csv')


def excluded_set():
    """Ticker-jours EXCLUS (gap = reverse split ou acquisition) — cf build_exclusions.py."""
    if not os.path.exists(_EXCL):
        return set()
    e = pd.read_csv(_EXCL)
    return set(zip(e.ticker, e.date)) if len(e) else set()
DEFAULTS = dict(price_min=3.0, price_max=20.0, gap_min=-100.0, gap_max=9999.0,
                entry_start=570, entry_end=720,                 # 9:30 -> midi par défaut
                exit_mode='tp', stop_pct=0.08, tp_pct=0.20, activate_pct=0.10, trail_pct=0.05, eod=955)


def _ind(g):
    key = (g['tk'], g['date'])
    if key not in _CACHE:
        _CACHE[key] = I.compute(g)
    return _CACHE[key]


def liquid_groups(groups, thr=0.20, exclude=True):
    """Univers PM-liquidité (latepm_frac >= thr : actif >= thr% des minutes 8:00-9:30). Robuste au délai.
    exclude=True : retire aussi les ticker-jours à gap ARTEFACT (reverse split / acquisition)."""
    u = pd.read_csv(_PM)
    keep = set(zip(u[u.latepm_frac >= thr].ticker, u[u.latepm_frac >= thr].date))
    ex = excluded_set() if exclude else set()
    return [g for g in groups if (g['tk'], g['date']) in keep and (g['tk'], g['date']) not in ex]


_FEAT = os.path.join(HERE, 'results', 'features.csv')
_FEAT_CACHE = {}


def feature_table():
    """(ticker,date) -> dict de features hors-prix (cf build_features.py). {} si pas encore généré."""
    if not _FEAT_CACHE and os.path.exists(_FEAT):
        f = pd.read_csv(_FEAT)
        for r in f.itertuples(index=False):
            _FEAT_CACHE[(r.ticker, r.date)] = r._asdict()
    return _FEAT_CACHE


def feature_filter(groups, **conds):
    """Filtre les groups sur les features hors-prix. Conventions de clés :
      <col>=v        -> égalité (ex. has_news=1, halted=1)
      <col>_min=v    -> >= v (ex. float_rot_min=1.0, dvol_session_min=200000, gap_max_min=30)
      <col>_max=v    -> <= v
    Un ticker-jour SANS feature (ou valeur NaN testée) est EXCLU (conservateur). Nécessite features.csv."""
    ft = feature_table()
    if not ft:
        raise FileNotFoundError(f"{_FEAT} absent — lance d'abord: python -m research.price_lab.build_features")

    def ok(key):
        row = ft.get(key)
        if row is None:
            return False
        for c, v in conds.items():
            if c.endswith('_min'):
                x = row.get(c[:-4])
                if x is None or pd.isna(x) or x < v: return False
            elif c.endswith('_max'):
                x = row.get(c[:-4])
                if x is None or pd.isna(x) or x > v: return False
            else:
                x = row.get(c)
                if x is None or pd.isna(x) or x != v: return False
        return True

    return [g for g in groups if ok((g['tk'], g['date']))]


def shape_groups(groups, mode='all'):
    if mode == 'all':
        return groups
    if mode == '4L':
        return [g for g in groups if len(str(g['tk'])) == 4 and str(g['tk']).isalpha()]
    raise ValueError(mode)


def _entry(g, ind, fn, P):
    """Premier i (one-shot) dans la fenêtre qui passe prix/gap + l'archétype. ZÉRO gate volume."""
    mins, c, gap = ind['mins'], ind['c'], ind['gap']
    for i in np.where((mins >= P['entry_start']) & (mins <= P['entry_end']))[0]:
        if not (P['price_min'] <= c[i] <= P['price_max']):
            continue
        if not (P['gap_min'] <= gap[i] <= P['gap_max']):
            continue
        if fn(ind, i, P):
            return int(i)
    return None


def entries(groups, name, P=None):
    fn = S.REGISTRY[name]; Q = dict(DEFAULTS); Q.update(P or {})
    out = []
    for g in groups:
        ind = _ind(g); i = _entry(g, ind, fn, Q)
        if i is not None:
            out.append((g, ind, i))
    return out


def trades_from(ents, exitP, slip=True):
    Q = dict(DEFAULTS); Q.update(exitP)
    rows = [dict(ticker=g['tk'], date=g['date'], entry_min=int(ind['mins'][i]),
                 entry=round(float(ind['c'][i]), 4), gap=round(float(ind['gap'][i]), 1),
                 pnl=round(bt._pnl(g, i, Q, slip), 3))
            for g, ind, i in ents]
    return pd.DataFrame(rows)


def simulate(groups, name, P=None, slip=True):
    Q = dict(DEFAULTS); Q.update(P or {})
    return trades_from(entries(groups, name, Q), Q, slip)


def evaluate(df, dates, split, stop_pct=0.08):
    if not len(df):
        return None
    pnl = df.pnl.to_numpy(); n = len(pnl)
    tdays = [d for d in dates if split and d >= split]; mid = dates[len(dates) // 2]
    h1 = df[df.date < mid].pnl; h2 = df[df.date >= mid].pnl
    te = df[df.date >= split].pnl if split else df.pnl
    sd = pnl.std(ddof=1) if n > 1 else 0
    cp, dd = portfolio(df, 0.02, stop_pct); cpo, _ = portfolio(df, 0.02, stop_pct, days=tdays)
    em = df.entry_min
    return dict(n=n, trj=round(n / df.date.nunique(), 1), exp=round(pnl.mean(), 2),
                t=round(pnl.mean() / (sd / np.sqrt(n)), 2) if sd > 0 else 0,
                win=round((pnl > 0).mean() * 100),
                e_h1=round(h1.mean(), 2) if len(h1) else 0, e_h2=round(h2.mean(), 2) if len(h2) else 0,
                e_te=round(te.mean(), 2) if len(te) else 0,
                e_trim=round(np.sort(pnl)[:-3].mean(), 2) if n > 3 else round(pnl.mean(), 2),
                entry_med=bt.hhmm(int(em.median())), open_pct=round((em <= 575).mean() * 100),
                maxDD=round(dd, 1), cpte=round(cp, 1), cpte_oos=round(cpo, 1))
