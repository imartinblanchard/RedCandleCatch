#!/usr/bin/env python3
"""Indicateurs vectorisés sur barres 1-min OHLCV — tous CAUSAUX (valeur à l'index i
n'utilise que les barres <= i). Alimentent les archétypes d'entrée de signals.py.

`compute(g)` prend un groupe ticker-jour de bt.load_groups (arrays o,h,l,c,v,mins,pc)
et renvoie un dict d'arrays alignés aux barres. Aucun I/O, testable unitairement.
⚠️ données = OHLCV minute SEULEMENT (pas de bid/ask, L2, tick) — rien ici ne les suppose.
"""
import numpy as np
import pandas as pd


def _ewm(x, span):
    return pd.Series(x).ewm(span=span, adjust=False).mean().to_numpy()


def _rma(x, n):                      # moyenne de Wilder (RSI/ATR)
    return pd.Series(x).ewm(alpha=1 / n, adjust=False).mean().to_numpy()


def rsi(c, n=14):
    d = np.diff(c, prepend=c[0])
    up = np.where(d > 0, d, 0.0); dn = np.where(d < 0, -d, 0.0)
    rs = _rma(up, n) / np.where(_rma(dn, n) == 0, 1e-9, _rma(dn, n))
    return 100 - 100 / (1 + rs)


def macd(c, fast=12, slow=26, sig=9):
    line = _ewm(c, fast) - _ewm(c, slow)
    signal = _ewm(line, sig)
    return line, signal, line - signal


def bollinger(c, n=20, k=2.0):
    s = pd.Series(c)
    mid = s.rolling(n, min_periods=1).mean().to_numpy()
    sd = s.rolling(n, min_periods=1).std(ddof=0).fillna(0).to_numpy()
    return mid, mid + k * sd, mid - k * sd, sd  # mid, up, lo, sigma


def atr(h, l, c, n=14):
    pc = np.concatenate([[c[0]], c[:-1]])
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    return _rma(tr, n)


def stochastic(h, l, c, n=14, d=3):
    hh = pd.Series(h).rolling(n, min_periods=1).max().to_numpy()
    ll = pd.Series(l).rolling(n, min_periods=1).min().to_numpy()
    rng = np.where(hh > ll, hh - ll, 1.0)
    k = np.where(hh > ll, (c - ll) / rng * 100, 50.0)
    return k, pd.Series(k).rolling(d, min_periods=1).mean().to_numpy()


def roc(c, n=10):
    out = np.zeros_like(c)
    out[n:] = (c[n:] - c[:-n]) / np.where(c[:-n] == 0, 1e-9, c[:-n]) * 100
    return out


def obv(c, v):
    sign = np.sign(np.diff(c, prepend=c[0]))
    return np.cumsum(sign * v)


def vwap_bands(h, l, c, v, k=2.0):
    tp = (h + l + c) / 3.0
    cv = np.cumsum(v); cpv = np.cumsum(tp * v); cpv2 = np.cumsum(tp * tp * v)
    cvp = np.where(cv > 0, cv, 1.0)
    vw = cpv / cvp
    var = np.maximum(0.0, cpv2 / cvp - vw * vw)
    sd = np.sqrt(var)
    return vw, vw + k * sd, vw - k * sd


def compute(g):
    """Renvoie un dict d'arrays causaux alignés aux barres du groupe."""
    o, h, l, c, v, mins = g['o'], g['h'], g['l'], g['c'], g['v'], g['mins']
    cum_v = np.cumsum(v)
    i = np.arange(len(c))
    avg_v_before = cum_v / np.maximum(i, 1)                         # vol moyen/min avant i (≈ shift)
    avg_v_before[0] = 0.0
    macd_l, macd_s, macd_h = macd(c)
    bb_mid, bb_up, bb_lo, bb_sd = bollinger(c)
    stk, std_ = stochastic(h, l, c)
    vw, vw_up, vw_lo = vwap_bands(h, l, c, v)
    hod = np.maximum.accumulate(h)                                 # plus-haut du jour (causal)
    gap = (hod - g['pc']) / g['pc'] * 100
    return dict(
        mins=mins, o=o, h=h, l=l, c=c, v=v, pc=g['pc'],
        ema9=_ewm(c, 9), ema20=_ewm(c, 20), ema50=_ewm(c, 50),
        rsi=rsi(c), macd=macd_l, macd_sig=macd_s, macd_hist=macd_h,
        bb_mid=bb_mid, bb_up=bb_up, bb_lo=bb_lo, bb_sd=bb_sd,
        bb_bw=(bb_up - bb_lo) / np.where(bb_mid > 0, bb_mid, 1.0),   # largeur relative (squeeze = basse)
        atr=atr(h, l, c), stoch_k=stk, stoch_d=std_, roc=roc(c), obv=obv(c, v),
        vwap=vw, vwap_up=vw_up, vwap_lo=vw_lo,
        rvol=np.where(avg_v_before > 0, v / np.where(avg_v_before > 0, avg_v_before, 1.0), 0.0),
        green=(c >= o), hod=hod, gap=gap, cum_v=cum_v,
    )


def orb_high(ind, open_min, window):
    """Plus-haut du range d'ouverture [open_min, open_min+window) — niveau fixe causal."""
    m = ind['mins']
    mask = (m >= open_min) & (m < open_min + window)
    return float(ind['h'][mask].max()) if mask.any() else np.inf
