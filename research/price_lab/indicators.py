#!/usr/bin/env python3
"""Indicateurs 100% PRIX (aucun volume) — utilisables en live (le prix d'une bougie clôturée
arrive fiable ; le volume temps réel est en retard/incomplet, cf audit 05/11). Tout est CAUSAL
(valeurs <= i). Entrées vectorisées numpy. Pas de VWAP, pas de rvol, pas d'OBV."""
import numpy as np


def _ewm(x, span):
    a = 2.0 / (span + 1.0); out = np.empty_like(x, float); out[0] = x[0]
    for i in range(1, len(x)):
        out[i] = a * x[i] + (1 - a) * out[i - 1]
    return out


def _rma(x, n):                       # moyenne de Wilder (RSI/ATR)
    a = 1.0 / n; out = np.empty_like(x, float); out[0] = x[0]
    for i in range(1, len(x)):
        out[i] = a * x[i] + (1 - a) * out[i - 1]
    return out


def ema(c, span):
    return _ewm(np.asarray(c, float), span)


def rsi(c, n=14):
    c = np.asarray(c, float); d = np.diff(c, prepend=c[0])
    up = _rma(np.clip(d, 0, None), n); dn = _rma(-np.clip(d, None, 0), n)
    rs = up / np.where(dn > 0, dn, 1e-9)
    return 100 - 100 / (1 + rs)


def macd(c, fast=12, slow=26, sig=9):
    c = np.asarray(c, float); line = _ewm(c, fast) - _ewm(c, slow)
    signal = _ewm(line, sig)
    return line, signal, line - signal           # macd, signal, hist


def bollinger(c, n=20, k=2.0):
    c = np.asarray(c, float); ma = _sma(c, n); sd = _rstd(c, n)
    up = ma + k * sd; lo = ma - k * sd
    bw = np.where(ma > 0, (up - lo) / ma, 0.0)    # largeur de bande relative
    return ma, up, lo, bw


def atr(h, l, c, n=14):
    h, l, c = map(lambda x: np.asarray(x, float), (h, l, c))
    pc = np.roll(c, 1); pc[0] = c[0]
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    return _rma(tr, n)


def stochastic(h, l, c, n=14, d=3):
    h, l, c = map(lambda x: np.asarray(x, float), (h, l, c))
    hh = _roll_max(h, n); ll = _roll_min(l, n)
    k = np.where(hh > ll, (c - ll) / (hh - ll) * 100, 50.0)
    return k, _sma(k, d)


def roc(c, n=10):
    c = np.asarray(c, float); out = np.zeros_like(c)
    out[n:] = (c[n:] / np.where(c[:-n] > 0, c[:-n], 1e-9) - 1) * 100
    return out


def williams_r(h, l, c, n=14):
    h, l, c = map(lambda x: np.asarray(x, float), (h, l, c))
    hh = _roll_max(h, n); ll = _roll_min(l, n)
    return np.where(hh > ll, (hh - c) / (hh - ll) * -100, -50.0)   # -100 (survendu) .. 0 (suracheté)


def cci(h, l, c, n=20):
    tp = (np.asarray(h, float) + np.asarray(l, float) + np.asarray(c, float)) / 3.0
    ma = _sma(tp, n); md = _roll_mad(tp, n)
    return np.where(md > 0, (tp - ma) / (0.015 * md), 0.0)


def supertrend(h, l, c, n=10, mult=3.0):
    """Supertrend (ATR) PRIX : renvoie la tendance (+1 haussier / -1 baissier) par barre."""
    h, l, c = map(lambda x: np.asarray(x, float), (h, l, c))
    a = atr(h, l, c, n); hl2 = (h + l) / 2.0
    up = hl2 + mult * a; dn = hl2 - mult * a
    trend = np.ones(len(c), int); fu = up.copy(); fl = dn.copy()
    for i in range(1, len(c)):
        fu[i] = min(up[i], fu[i - 1]) if c[i - 1] <= fu[i - 1] else up[i]
        fl[i] = max(dn[i], fl[i - 1]) if c[i - 1] >= fl[i - 1] else dn[i]
        trend[i] = 1 if c[i] > fu[i - 1] else (-1 if c[i] < fl[i - 1] else trend[i - 1])
    return trend


# ── helpers de fenêtre glissante (causaux) ──
def _sma(x, n):
    x = np.asarray(x, float); cs = np.cumsum(np.insert(x, 0, 0.0))
    out = (cs[n:] - cs[:-n]) / n
    head = np.array([x[:i + 1].mean() for i in range(min(n - 1, len(x)))])
    return np.concatenate([head, out])[:len(x)]


def _rstd(x, n):
    x = np.asarray(x, float)
    return np.array([x[max(0, i - n + 1):i + 1].std() for i in range(len(x))])


def _roll_max(x, n):
    x = np.asarray(x, float)
    return np.array([x[max(0, i - n + 1):i + 1].max() for i in range(len(x))])


def _roll_min(x, n):
    x = np.asarray(x, float)
    return np.array([x[max(0, i - n + 1):i + 1].min() for i in range(len(x))])


def _roll_mad(x, n):
    x = np.asarray(x, float)
    return np.array([np.abs(x[max(0, i - n + 1):i + 1] - x[max(0, i - n + 1):i + 1].mean()).mean()
                     for i in range(len(x))])


def compute(g):
    """Toutes les features PRIX d'un ticker-jour (arrays alignés sur les bougies)."""
    o = np.asarray(g['o'], float); h = np.asarray(g['h'], float)
    l = np.asarray(g['l'], float); c = np.asarray(g['c'], float); mins = np.asarray(g['mins'])
    _, _, mh = macd(c); bb_ma, bb_up, bb_lo, bb_bw = bollinger(c)
    stk, std_ = stochastic(h, l, c)
    hod = np.maximum.accumulate(h); pc = g['pc'] or c[0]
    gap = (hod - pc) / pc * 100
    sma20 = _sma(c, 20)                                   # moyenne de prix = "VWAP sans volume"
    return dict(mins=mins, o=o, h=h, l=l, c=c, pc=pc, green=(c >= o), hod=hod, gap=gap,
                ema9=ema(c, 9), ema20=ema(c, 20), ema50=ema(c, 50), sma20=sma20,
                rsi=rsi(c), macd_hist=mh, bb_up=bb_up, bb_lo=bb_lo, bb_bw=bb_bw,
                atr=atr(h, l, c), stoch_k=stk, stoch_d=std_, roc=roc(c),
                wr=williams_r(h, l, c), cci=cci(h, l, c), st=supertrend(h, l, c))


def orb_high(ind, open_min, window):
    m = (ind['mins'] >= open_min) & (ind['mins'] < open_min + window)
    return float(ind['h'][m].max()) if m.any() else np.inf
