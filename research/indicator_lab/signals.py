#!/usr/bin/env python3
"""Archétypes d'entrée = COMBINAISONS d'indicateurs. Chacun répond "la barre i est-elle
une entrée ?" en n'utilisant QUE des valeurs <= i (causal). Complètement différents du
repli-depuis-HOD de live_lab. Params lus dans P (dict). Registre REGISTRY en bas.

Signature : fn(ind, i, P) -> bool. `ind` = indicators.compute(g). L'engine applique en
amont les gardes de base (prix, bande de gap, fenêtre horaire) et le one-shot.
"""
import numpy as np
from . import indicators as I


def _cross_up(a, b, i):
    return i >= 1 and a[i - 1] < b[i - 1] and a[i] >= b[i]


def vwap_reclaim(ind, i, P):
    """Reprise : le prix repasse AU-DESSUS du VWAP sur volume (momentum qui redémarre)."""
    return (_cross_up(ind['c'], ind['vwap'], i)
            and ind['rvol'][i] >= P.get('rvol_min', 2.0)
            and ind['green'][i])


def ema9_pullback(ind, i, P):
    """Tendance haussière (9>20>VWAP), repli sur la 9 EMA, puis bougie verte de rebond."""
    return (ind['ema9'][i] > ind['ema20'][i] > ind['vwap'][i]
            and ind['l'][i] <= ind['ema9'][i] * (1 + P.get('touch', 0.003))
            and ind['c'][i] > ind['ema9'][i]
            and ind['green'][i]
            and ind['rvol'][i] >= P.get('rvol_min', 1.0))


def orb_breakout(ind, i, P):
    """Cassure FRAÎCHE du plus-haut du range d'ouverture (ORB) sur volume, au-dessus du VWAP."""
    om = P.get('open_min', 570); w = P.get('orb_win', 15)
    lvl = I.orb_high(ind, om, w)
    if not np.isfinite(lvl) or ind['mins'][i] < om + w:
        return False
    fresh = ind['c'][i - 1] <= lvl if i >= 1 else True
    return (ind['c'][i] > lvl and fresh
            and ind['rvol'][i] >= P.get('rvol_min', 2.0)
            and ind['c'][i] >= ind['vwap'][i])


def rsi_bounce(ind, i, P):
    """RSI ressort du survendu (croise à la hausse un seuil bas) en restant au-dessus du VWAP."""
    lo = P.get('rsi_lo', 30)
    return (_cross_up(ind['rsi'], np.full_like(ind['rsi'], lo), i)
            and ind['c'][i] >= ind['vwap'][i]
            and ind['green'][i])


def macd_cross(ind, i, P):
    """Croisement MACD haussier (hist passe >0) filtré par RSI non-suracheté, au-dessus du VWAP."""
    return (i >= 1 and ind['macd_hist'][i - 1] < 0 <= ind['macd_hist'][i]
            and P.get('rsi_lo', 40) <= ind['rsi'][i] <= P.get('rsi_hi', 70)
            and ind['c'][i] >= ind['vwap'][i]
            and ind['rvol'][i] >= P.get('rvol_min', 1.0))


def bb_breakout(ind, i, P):
    """Compression de Bollinger (largeur de bande basse) puis clôture au-dessus de la bande haute."""
    squeezed = i >= 1 and ind['bb_bw'][i - 1] <= P.get('squeeze_bw', 0.04)
    return (squeezed and ind['c'][i] > ind['bb_up'][i]
            and ind['rvol'][i] >= P.get('rvol_min', 1.5)
            and ind['c'][i] >= ind['vwap'][i])


def keltner_breakout(ind, i, P):
    """Cassure du canal de Keltner (EMA20 + mult·ATR) sur volume — expansion de volatilité haussière."""
    upper = ind['ema20'][i] + P.get('kelt_mult', 2.0) * ind['atr'][i]
    fresh = i >= 1 and ind['c'][i - 1] <= ind['ema20'][i - 1] + P.get('kelt_mult', 2.0) * ind['atr'][i - 1]
    return (ind['c'][i] > upper and fresh
            and ind['rvol'][i] >= P.get('rvol_min', 1.5)
            and ind['green'][i])


def atr_breakout(ind, i, P):
    """Cassure de volatilité : clôture > clôture précédente + k·ATR, au-dessus du VWAP, sur volume."""
    if i < 1:
        return False
    return (ind['c'][i] >= ind['c'][i - 1] + P.get('atr_k', 1.0) * ind['atr'][i]
            and ind['c'][i] >= ind['vwap'][i]
            and ind['rvol'][i] >= P.get('rvol_min', 1.5))


def obv_divergence(ind, i, P):
    """Divergence haussière : le PRIX fait un nouveau plus-bas sur la fenêtre mais l'OBV NON
    (le volume ne confirme pas la baisse → essoufflement vendeur), confirmé par une bougie verte > VWAP."""
    N = P.get('div_win', 20)
    if i < N:
        return False
    lo = i - N + 1
    price_low = ind['l'][i] <= ind['l'][lo:i + 1].min() * (1 + 0.001)   # prix = plus-bas de la fenêtre
    obv_holds = ind['obv'][i] > ind['obv'][lo:i + 1].min() + 1e-9       # OBV PAS à son plus-bas
    return (price_low and obv_holds and ind['green'][i]
            and ind['c'][i] >= ind['vwap'][i])


def bullish_engulfing(ind, i, P):
    """Avalement haussier : bougie verte dont le corps englobe la rouge précédente, au-dessus du VWAP."""
    if i < 1:
        return False
    prev_red = ind['c'][i - 1] < ind['o'][i - 1]
    engulf = ind['o'][i] <= ind['c'][i - 1] and ind['c'][i] >= ind['o'][i - 1]
    return (prev_red and engulf and ind['green'][i]
            and ind['c'][i] >= ind['vwap'][i]
            and ind['rvol'][i] >= P.get('rvol_min', 1.0))


REGISTRY = {
    'vwap_reclaim': vwap_reclaim,
    'ema9_pullback': ema9_pullback,
    'orb_breakout': orb_breakout,
    'rsi_bounce': rsi_bounce,
    'macd_cross': macd_cross,
    'bb_breakout': bb_breakout,
    'keltner_breakout': keltner_breakout,
    'atr_breakout': atr_breakout,
    'obv_divergence': obv_divergence,
    'bullish_engulfing': bullish_engulfing,
}
