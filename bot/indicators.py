#!/usr/bin/env python3
"""
Indicators — pure functions used by the LONG Terminator's entry setups.

Warrior (Ross Cameron) reads price action off the 1-min chart with two guides:
the 9 EMA and VWAP. These are deterministic helpers over a bar list; no I/O, so
they are unit-testable on historical data.

Bar shape: {'t': datetime, 'o','h','l','c','v'} (as returned by
IBKRBroker.intraday_1min or Alpaca historical bars).
"""
import math
from typing import List, Optional


def ema(values: List[float], period: int) -> List[float]:
    """Exponential moving average. Returns a list aligned with `values`
    (first `period-1` entries are the running SMA seed, then true EMA)."""
    if not values:
        return []
    k = 2 / (period + 1)
    out = [values[0]]
    for v in values[1:]:
        out.append(v * k + out[-1] * (1 - k))
    return out


def last_ema(values: List[float], period: int) -> Optional[float]:
    e = ema(values, period)
    return e[-1] if e else None


def vwap(bars: List[dict]) -> List[float]:
    """Cumulative VWAP anchored to the first bar provided (assumed same session).
    VWAP_i = sum(typical*vol)[0..i] / sum(vol)[0..i]."""
    out, cum_pv, cum_v = [], 0.0, 0.0
    for b in bars:
        typical = (b['h'] + b['l'] + b['c']) / 3
        cum_pv += typical * b['v']
        cum_v += b['v']
        out.append(cum_pv / cum_v if cum_v else b['c'])
    return out


def last_vwap(bars: List[dict]) -> Optional[float]:
    v = vwap(bars)
    return v[-1] if v else None


def vwap_bands(bars: List[dict], k: float) -> List[float]:
    """Upper VWAP band = VWAP + k·σ, σ = volume-weighted std of typical price,
    anchored to the first bar (same anchor as VWAP). Returns the upper band series.
    Small-cap momentum traders take profit when price stretches to the +2σ band."""
    out, cv, cpv, cpv2 = [], 0.0, 0.0, 0.0
    for b in bars:
        tp = (b['h'] + b['l'] + b['c']) / 3
        cv += b['v']; cpv += tp * b['v']; cpv2 += tp * tp * b['v']
        if cv <= 0:
            out.append(b['c']); continue
        vw = cpv / cv
        var = max(0.0, cpv2 / cv - vw * vw)
        out.append(vw + k * math.sqrt(var))
    return out


def vwap_upper(bars: List[dict], k: float = 2) -> Optional[float]:
    b = vwap_bands(bars, k)
    return b[-1] if b else None


def session_high(bars: List[dict]) -> Optional[float]:
    return max((b['h'] for b in bars), default=None)


def session_low(bars: List[dict]) -> Optional[float]:
    return min((b['l'] for b in bars), default=None)
