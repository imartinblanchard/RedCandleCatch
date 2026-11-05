#!/usr/bin/env python3
"""Archétypes d'entrée 100% PRIX (aucune condition volume). fn(ind, i, P) -> bool, causal.
Les 8 archétypes repris de l'ancien lab sont STRIPPÉS de leurs confirmations vwap/rvol.
+ 6 nouveaux price-only, dont des remplaçants SANS volume de vwap_reclaim (sma_reclaim) et
obv_divergence (rsi_divergence). L'engine applique en amont prix/gap/fenêtre + one-shot."""
import numpy as np
from . import indicators as I


def _cross_up(a, b, i):
    return i >= 1 and a[i - 1] < b[i - 1] and a[i] >= b[i]


# ───────── les 8 archétypes repris, STRIPPÉS du volume ─────────
def ema9_pullback(ind, i, P):
    """Tendance (9>20), repli qui TOUCHE la 9-EMA, puis bougie verte de rebond."""
    return (ind['ema9'][i] > ind['ema20'][i]
            and ind['l'][i] <= ind['ema9'][i] * (1 + P.get('touch', 0.003))
            and ind['c'][i] > ind['ema9'][i] and ind['green'][i])


def orb_breakout(ind, i, P):
    """Cassure FRAÎCHE du plus-haut du range d'ouverture (ORB)."""
    om = P.get('open_min', 570); w = P.get('orb_win', 15)
    lvl = I.orb_high(ind, om, w)
    if not np.isfinite(lvl) or ind['mins'][i] < om + w:
        return False
    fresh = ind['c'][i - 1] <= lvl if i >= 1 else True
    return ind['c'][i] > lvl and fresh and ind['green'][i]


def rsi_bounce(ind, i, P):
    """RSI ressort du survendu (croise un seuil bas à la hausse) + bougie verte."""
    lo = P.get('rsi_lo', 30)
    return _cross_up(ind['rsi'], np.full_like(ind['rsi'], lo), i) and ind['green'][i]


def macd_cross(ind, i, P):
    """Croisement MACD haussier (hist passe >0) filtré RSI non-suracheté."""
    return (i >= 1 and ind['macd_hist'][i - 1] < 0 <= ind['macd_hist'][i]
            and P.get('rsi_lo', 40) <= ind['rsi'][i] <= P.get('rsi_hi', 70))


def bb_breakout(ind, i, P):
    """Compression de Bollinger puis clôture au-dessus de la bande haute."""
    squeezed = i >= 1 and ind['bb_bw'][i - 1] <= P.get('squeeze_bw', 0.04)
    return squeezed and ind['c'][i] > ind['bb_up'][i] and ind['green'][i]


def keltner_breakout(ind, i, P):
    """Cassure FRAÎCHE du canal de Keltner (EMA20 + mult·ATR)."""
    m = P.get('kelt_mult', 2.0)
    upper = ind['ema20'][i] + m * ind['atr'][i]
    fresh = i >= 1 and ind['c'][i - 1] <= ind['ema20'][i - 1] + m * ind['atr'][i - 1]
    return ind['c'][i] > upper and fresh and ind['green'][i]


def atr_breakout(ind, i, P):
    """Cassure de volatilité : clôture > clôture précédente + k·ATR."""
    return (i >= 1 and ind['c'][i] >= ind['c'][i - 1] + P.get('atr_k', 1.0) * ind['atr'][i]
            and ind['green'][i])


def bullish_engulfing(ind, i, P):
    """Avalement haussier : bougie verte dont le corps englobe la rouge précédente."""
    if i < 1:
        return False
    prev_red = ind['c'][i - 1] < ind['o'][i - 1]
    engulf = ind['o'][i] <= ind['c'][i - 1] and ind['c'][i] >= ind['o'][i - 1]
    return prev_red and engulf and ind['green'][i]


# ───────── 6 NOUVEAUX archétypes price-only ─────────
def sma_reclaim(ind, i, P):
    """REMPLAÇANT de vwap_reclaim SANS volume : la clôture recroise la moyenne de prix (SMA20) + verte."""
    return _cross_up(ind['c'], ind['sma20'], i) and ind['green'][i]


def rsi_divergence(ind, i, P):
    """REMPLAÇANT d'obv_divergence SANS volume : le PRIX fait un nouveau plus-bas sur la fenêtre
    mais le RSI NON (essoufflement vendeur), confirmé par une bougie verte."""
    N = P.get('div_win', 20)
    if i < N:
        return False
    lo = i - N + 1
    price_low = ind['l'][i] <= ind['l'][lo:i + 1].min() * (1 + 0.001)
    rsi_holds = ind['rsi'][i] > ind['rsi'][lo:i + 1].min() + 1.0
    return price_low and rsi_holds and ind['green'][i]


def donchian_breakout(ind, i, P):
    """Cassure FRAÎCHE du plus-haut des N dernières bougies (canal de Donchian, prix pur)."""
    N = P.get('don_win', 20)
    if i < N:
        return False
    prior = ind['h'][i - N:i].max()
    return ind['c'][i] > prior and ind['green'][i]


def supertrend_flip(ind, i, P):
    """Bascule du Supertrend (ATR) en tendance HAUSSIÈRE à cette barre."""
    return i >= 1 and ind['st'][i - 1] < 0 and ind['st'][i] > 0


def williams_bounce(ind, i, P):
    """Williams %R ressort du survendu (croise -80 à la hausse) + bougie verte."""
    thr = P.get('wr_lo', -80.0)
    return _cross_up(ind['wr'], np.full_like(ind['wr'], thr), i) and ind['green'][i]


def higher_high_momentum(ind, i, P):
    """Momentum : N clôtures consécutivement plus hautes (poussée de prix) au-dessus de l'EMA20."""
    N = P.get('hh_win', 3)
    if i < N:
        return False
    rising = all(ind['c'][i - k] > ind['c'][i - k - 1] for k in range(N))
    return rising and ind['c'][i] > ind['ema20'][i]


REGISTRY = {
    # 8 strippés
    'ema9_pullback': ema9_pullback, 'orb_breakout': orb_breakout, 'rsi_bounce': rsi_bounce,
    'macd_cross': macd_cross, 'bb_breakout': bb_breakout, 'keltner_breakout': keltner_breakout,
    'atr_breakout': atr_breakout, 'bullish_engulfing': bullish_engulfing,
    # 6 nouveaux price-only
    'sma_reclaim': sma_reclaim, 'rsi_divergence': rsi_divergence, 'donchian_breakout': donchian_breakout,
    'supertrend_flip': supertrend_flip, 'williams_bounce': williams_bounce,
    'higher_high_momentum': higher_high_momentum,
}
