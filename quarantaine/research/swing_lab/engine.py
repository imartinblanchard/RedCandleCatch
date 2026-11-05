#!/usr/bin/env python3
"""Moteur de backtest SWING daily, un seul titre (NVDA). Long/flat, causal.

Principe (vectorisé, sans look-ahead) : une stratégie renvoie une série de POSITION cible (1=long,
0=flat) calculée avec l'info DISPONIBLE à la clôture du jour i ; le moteur exécute cette position le
LENDEMAIN (pos.shift(1)) et calcule le rendement close-à-close. Benchmark OBLIGATOIRE = BUY & HOLD.

Métriques : rendement total, CAGR, maxDD, exposition (% jours investi), nb de trades, win%, Sharpe.
⚠️ un seul titre + 3 ans = TRÈS peu d'indépendance statistique -> hypothèses, pas des vérités.
Données isolées (data/research/nvda/), hors de l'univers live des gappers."""
import os
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(os.path.dirname(os.path.dirname(HERE)), 'data', 'research', 'swing')
TY = 252


def load_daily(ticker: str = 'nvda') -> pd.DataFrame:
    f = os.path.join(DATA, f'{ticker}_daily.parquet')
    if not os.path.exists(f):
        raise SystemExit(f"❌ {f} absent — lance d'abord : python -m research.swing_lab.fetch --universe")
    return pd.read_parquet(f).sort_values('date').reset_index(drop=True)


def _metrics(pos: np.ndarray, close: np.ndarray):
    """pos = position cible à la CLÔTURE du jour i. Exécutée le lendemain (shift 1)."""
    ret = np.zeros_like(close); ret[1:] = close[1:] / close[:-1] - 1       # rendement journalier
    exe = np.zeros_like(pos); exe[1:] = pos[:-1]                           # on tient la position le LENDEMAIN
    sret = exe * ret
    eq = np.cumprod(1 + sret); bh = np.cumprod(1 + ret)
    n = len(close)
    def dd(curve):
        peak = np.maximum.accumulate(curve); return ((curve - peak) / peak).min() * 100
    def cagr(curve):
        return (curve[-1] ** (TY / n) - 1) * 100 if curve[-1] > 0 else -100.0
    # trades = segments d'exécution continue
    trades, i = [], 0
    while i < n:
        if exe[i] >= 1:
            j = i
            while j < n and exe[j] >= 1:
                j += 1
            seg = close[i:j]
            if len(seg) >= 2:
                trades.append(seg[-1] / seg[0] - 1)
            i = j
        else:
            i += 1
    tr = np.array(trades) if trades else np.array([])
    sharpe = (sret.mean() / sret.std() * np.sqrt(TY)) if sret.std() > 0 else 0.0
    return dict(ret=(eq[-1] - 1) * 100, cagr=cagr(eq), maxDD=dd(eq), expo=exe.mean() * 100,
                ntr=len(tr), win=(tr > 0).mean() * 100 if len(tr) else 0.0,
                avgtr=tr.mean() * 100 if len(tr) else 0.0, sharpe=sharpe,
                bh_ret=(bh[-1] - 1) * 100, bh_cagr=cagr(bh), bh_maxDD=dd(bh))


def evaluate(df: pd.DataFrame, pos: np.ndarray):
    return _metrics(np.asarray(pos, float), df['c'].to_numpy(float))
