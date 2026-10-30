#!/usr/bin/env python3
"""Détecteurs d'entrée PURS (sans broker, sans I/O) pour le terminator live.

But : la MÊME logique sert (a) au terminator en direct et (b) au script de vérification
qui rejoue l'historique — pour garantir que la détection LIVE == le backtest. Chaque
détecteur prend la liste des bougies clôturées `allbars` (dicts {'t':datetime,'o','h','l','c','v'},
triées, 04:00+) et l'instant `now_t`, et renvoie (entry, activate, desc) ou None.

vwap_reclaim : réplique EXACTEMENT research/indicator_lab (signals.vwap_reclaim + engine._entry) :
  - VWAP cumulatif ancré à la 1re bougie (PM inclus), bandes identiques au backtest
  - reprise = la clôture repasse AU-DESSUS du VWAP (c[i-1]<vwap[i-1] et c[i]>=vwap[i])
  - rvol[i] = v[i] / (somme(v[0..i]) / i)   ← MÊME quirk que le backtest (cum_v inclut i, /i)
  - bougie verte, prix dans [price], fenêtre horaire [win], rvol >= rvol_min
L'univers (freq-filtré PM) est géré EN AMONT par le terminator (gate PM-liq), pas ici.
"""
from typing import List, Optional, Tuple


def _hm(t) -> int:
    return t.hour * 60 + t.minute


def vwap_reclaim_signal(allbars: List[dict], now_t, rvol_min: float = 60.0,
                        win: Tuple[int, int] = (570, 630), price: Tuple[float, float] = (3.0, 20.0),
                        activate: float = 0.10) -> Optional[Tuple[float, float, str]]:
    up = [b for b in allbars if b['t'] <= now_t]
    if len(up) < 2:
        return None
    i = len(up) - 1
    bi = up[i]
    if not (win[0] <= _hm(bi['t']) <= win[1]):          # fenêtre horaire (1re heure)
        return None
    c_i, o_i = bi['c'], bi['o']
    if not (price[0] <= c_i <= price[1]):               # zone exécutable
        return None
    if c_i < o_i:                                       # bougie verte
        return None
    # VWAP cumulatif ancré à la 1re bougie (typ = (h+l+c)/3, pondéré volume)
    cum_pv = cum_v = 0.0
    vwap_prev = vwap_cur = c_i
    for k, b in enumerate(up):
        typ = (b['h'] + b['l'] + b['c']) / 3.0
        cum_pv += typ * (b['v'] or 0.0)
        cum_v += (b['v'] or 0.0)
        v = cum_pv / cum_v if cum_v > 0 else b['c']
        if k == i - 1:
            vwap_prev = v
        elif k == i:
            vwap_cur = v
    if not (up[i - 1]['c'] < vwap_prev and c_i >= vwap_cur):   # reprise = cross-up du VWAP
        return None
    # rvol : v[i] / (somme(v[0..i]) / i)  — réplique indicators.compute (avg_v_before = cum_v[i]/i)
    sv = sum((b['v'] or 0.0) for b in up[:i + 1])
    avg_before = sv / i if i > 0 else 0.0
    rvol = (bi['v'] or 0.0) / avg_before if avg_before > 0 else 0.0
    if rvol < rvol_min:
        return None
    return (float(c_i), activate, f"vwap_reclaim rvol>={rvol_min:.0f} (rvol={rvol:.0f})")
