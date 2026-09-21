#!/usr/bin/env python3
"""
Pre-market momentum strategy (LONG) — the rules validated in STRATEGY.md.

⚠️ IN-SAMPLE ONLY: tuned on the May–Jul 2026 checklist. The paper Terminator
(bot.terminator_long) runs this forward to gather out-of-sample evidence.

Entry (pre-market): price above VWAP, pull back tagging VWAP, green bounce close,
entry-bar volume ≥ SURGE× the recent average, cumulative PM volume ≥ MIN_PM_VOL,
and a "tradability" gate (the stock must actually be moving, not a flat/dead tape).
Exit: −STOP_PCT stop, or take profit at the VWAP +BAND_K·σ upper band.
"""
from typing import List, Optional, Dict

from bot.indicators import vwap, vwap_upper

# --- validated parameters (see STRATEGY.md) ---
STOP_PCT   = 0.05    # initial stop -5%
BAND_K     = 2       # take profit at VWAP + 2σ (best in-sample)
SURGE      = 3.0     # entry-bar volume >= 3x recent average
MIN_PM_VOL = 150_000 # cumulative pre-market volume liquidity gate
VWAP_TOL   = 0.003   # pull back "tags" VWAP if low <= VWAP*(1+tol)
MIN_ABOVE  = 3       # bars above VWAP before the pullback (uptrend)
# tradability gate — skip flat/dead tapes (e.g. BTCT pinned at 1.18 on ~0 volume)
MIN_RANGE_PCT = 0.01    # avg bar range (high-low)/close over last 5 bars must be >= 1%
MIN_BAR_VOL   = 10_000  # entry-bar volume floor (absolute liquidity backstop)
# reward gate — skip low-upside setups: the VWAP+2σ band (the TP) must be far enough
MIN_TARGET_PCT = 0.05   # band at entry must be >= 5% above entry (else not worth it)


def check_entry(bars: List[dict]) -> Optional[Dict]:
    """Evaluate the LAST bar as an entry trigger. `bars` = today's pre-market
    session bars (anchored at 04:00 ET). Returns {'entry','stop','reason'} or None."""
    if len(bars) < MIN_ABOVE + 2:
        return None
    i = len(bars) - 1
    last = bars[-1]
    vw = vwap(bars)
    if sum(b['v'] for b in bars) < MIN_PM_VOL:            # liquidity gate
        return None
    prev5 = [b['v'] for b in bars[max(0, i - 5):i]]        # volume surge on entry bar
    avg5 = sum(prev5) / len(prev5) if prev5 else 0
    if avg5 and last['v'] < SURGE * avg5:
        return None
    if last['v'] < MIN_BAR_VOL:                            # tradability: real liquidity now
        return None
    last5 = bars[max(0, i - 4):i + 1]                      # tradability: it must move
    avg_range = sum((b['h'] - b['l']) / b['c'] for b in last5) / len(last5)
    if avg_range < MIN_RANGE_PCT:
        return None
    above = all(bars[j]['c'] > vwap(bars[:j + 1])[-1] for j in range(i - MIN_ABOVE, i))
    tag = last['l'] <= vw[-1] * (1 + VWAP_TOL)
    bounce = last['c'] >= last['o'] and last['c'] > vw[-1]
    if above and tag and bounce:
        entry = last['c']
        band = vwap_upper(bars, BAND_K)                   # reward gate: enough upside?
        if band and (band - entry) / entry < MIN_TARGET_PCT:
            return None
        return {'entry': entry, 'stop': round(entry * (1 - STOP_PCT), 4),
                'reason': 'VWAP_PULLBACK+SURGE'}
    return None


def check_exit(bars: List[dict], entry: float) -> Optional[Dict]:
    """Decide whether to exit now, given current pre-market bars and the entry.
    Returns {'reason','price'} or None."""
    last = bars[-1]
    stop = entry * (1 - STOP_PCT)
    band = vwap_upper(bars, BAND_K)
    if last['l'] <= stop or last['c'] <= stop:
        return {'reason': 'STOP', 'price': round(stop, 4)}
    if band and (last['h'] >= band or last['c'] >= band):
        return {'reason': 'TP_BAND', 'price': round(band, 4)}
    return None
