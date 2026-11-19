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
import numpy as np


def _hm(t) -> int:
    return t.hour * 60 + t.minute


def _rma(x, n):                         # moyenne de Wilder (identique à research/price_lab/indicators._rma)
    a = 1.0 / n; out = np.empty_like(x, float); out[0] = x[0]
    for i in range(1, len(x)):
        out[i] = a * x[i] + (1 - a) * out[i - 1]
    return out


def _rsi(c, n=14):                      # RSI Wilder — réplique EXACTE de price_lab.indicators.rsi
    c = np.asarray(c, float); d = np.diff(c, prepend=c[0])
    up = _rma(np.clip(d, 0, None), n); dn = _rma(-np.clip(d, None, 0), n)
    rs = up / np.where(dn > 0, dn, 1e-9)
    return 100 - 100 / (1 + rs)


def _ewm(x, span):                      # EMA — réplique EXACTE de price_lab.indicators._ewm
    a = 2.0 / (span + 1.0); out = np.empty_like(x, float); out[0] = x[0]
    for i in range(1, len(x)):
        out[i] = a * x[i] + (1 - a) * out[i - 1]
    return out


def _sma(x, n):                         # réplique EXACTE de price_lab.indicators._sma (tête = moyenne expansive)
    x = np.asarray(x, float); cs = np.cumsum(np.insert(x, 0, 0.0))
    out = (cs[n:] - cs[:-n]) / n
    head = np.array([x[:i + 1].mean() for i in range(min(n - 1, len(x)))])
    return np.concatenate([head, out])[:len(x)]


def _rstd(x, n):                        # réplique EXACTE de price_lab.indicators._rstd (std population, ddof=0)
    x = np.asarray(x, float)
    return np.array([x[max(0, i - n + 1):i + 1].std() for i in range(len(x))])


def bb_breakout_signal(allbars: List[dict], now_t, pc: float, gap_min: float = 10.0, gap_max: float = 20.0,
                       squeeze_bw: float = 0.04, win: Tuple[int, int] = (570, 720),
                       price: Tuple[float, float] = (3.0, 20.0), n: int = 20, k: float = 2.0,
                       tp: float = 0.15) -> Optional[Tuple[float, float, str]]:
    """Réplique EXACTEMENT signals.bb_breakout + engine._entry (gates fenêtre/prix/gap) :
      - compression : largeur de bande Bollinger (bb_bw) de la bougie PRÉCÉDENTE <= squeeze_bw
      - clôture > bande haute (bb_up), bougie VERTE, gap dans [gap_min,gap_max], prix/fenêtre OK.
    Renvoie (entry, tp, desc) ou None. Univers PM-liquidité géré EN AMONT par le terminator."""
    up = [b for b in allbars if b['t'] <= now_t]
    if len(up) < n + 2 or not pc or pc <= 0:
        return None
    i = len(up) - 1; bi = up[i]
    if not (win[0] <= _hm(bi['t']) <= win[1]):
        return None
    c_i, o_i = bi['c'], bi['o']
    if not (price[0] <= c_i <= price[1]) or c_i < o_i:       # prix exécutable + bougie VERTE
        return None
    hod = max(b['h'] for b in up); gap = (hod - pc) / pc * 100.0
    if not (gap_min <= gap <= gap_max):
        return None
    c = np.array([b['c'] for b in up], float)
    ma = _sma(c, n); sd = _rstd(c, n); up_b = ma + k * sd; lo_b = ma - k * sd
    bw = np.where(ma > 0, (up_b - lo_b) / ma, 0.0)
    if not (bw[i - 1] <= squeeze_bw and c_i > up_b[i]):      # squeeze (bougie préc.) PUIS cassure haut
        return None
    return (float(c_i), float(tp), f"bb_breakout gap{gap:.0f}% squeeze {bw[i-1]:.3f} c>{up_b[i]:.2f}")


def higher_high_signal(allbars: List[dict], now_t, pc: float, gap_min: float = 10.0, gap_max: float = 20.0,
                       hh_win: int = 3, win: Tuple[int, int] = (570, 720),
                       price: Tuple[float, float] = (3.0, 20.0),
                       tp: float = 0.15) -> Optional[Tuple[float, float, str]]:
    """Réplique EXACTEMENT signals.higher_high_momentum + engine._entry (gates fenêtre/prix/gap) :
      - N clôtures consécutivement plus hautes (poussée) ET clôture > EMA20. PAS de gate bougie verte
        (l'archétype ne le check pas). gap dans [gap_min,gap_max], prix/fenêtre OK.
    Renvoie (entry, tp, desc) ou None. Univers PM-liquidité géré EN AMONT par le terminator."""
    up = [b for b in allbars if b['t'] <= now_t]
    N = hh_win
    if len(up) < N + 2 or not pc or pc <= 0:
        return None
    i = len(up) - 1; bi = up[i]
    if not (win[0] <= _hm(bi['t']) <= win[1]):
        return None
    c_i = bi['c']
    if not (price[0] <= c_i <= price[1]):                    # prix exécutable (pas de gate verte)
        return None
    hod = max(b['h'] for b in up); gap = (hod - pc) / pc * 100.0
    if not (gap_min <= gap <= gap_max):
        return None
    c = np.array([b['c'] for b in up], float)
    ema20 = _ewm(c, 20)
    rising = all(c[i - j] > c[i - j - 1] for j in range(N))
    if not (rising and c_i > ema20[i]):                      # N clôtures montantes + au-dessus EMA20
        return None
    return (float(c_i), float(tp), f"higher_high gap{gap:.0f}% {N}xHH c>ema20 {ema20[i]:.2f}")


def rsi_bounce_signal(allbars: List[dict], now_t, pc: float, gap_min: float = 3.0, gap_max: float = 10.0,
                      rsi_lo: float = 20.0, win: Tuple[int, int] = (570, 720),
                      price: Tuple[float, float] = (3.0, 20.0), n: int = 14,
                      tp: float = 0.20) -> Optional[Tuple[float, float, str]]:
    """Réplique EXACTEMENT research/price_lab (signals.rsi_bounce + engine._entry) — 100% PRIX :
      - gap (plus-haut du jour depuis la 1re bougie, PM inclus, vs clôture veille) dans [gap_min,gap_max]
      - RSI(14) recroise rsi_lo à la hausse (rsi[i-1] < rsi_lo <= rsi[i])
      - bougie verte, prix dans [price], fenêtre horaire [win].
    Renvoie (entry, tp, desc) ou None. L'univers PM-liquidité est géré EN AMONT par le terminator."""
    up = [b for b in allbars if b['t'] <= now_t]
    if len(up) < n + 2 or not pc or pc <= 0:
        return None
    i = len(up) - 1; bi = up[i]
    if not (win[0] <= _hm(bi['t']) <= win[1]):
        return None
    c_i, o_i = bi['c'], bi['o']
    if not (price[0] <= c_i <= price[1]) or c_i < o_i:        # zone exécutable + bougie verte
        return None
    hod = max(b['h'] for b in up); gap = (hod - pc) / pc * 100.0
    if not (gap_min <= gap <= gap_max):
        return None
    rsi = _rsi([b['c'] for b in up], n)
    if not (rsi[i - 1] < rsi_lo <= rsi[i]):                   # recroisement du seuil bas à la hausse
        return None
    return (float(c_i), float(tp), f"rsi_bounce gap{gap:.0f}% RSI {rsi[i-1]:.0f}->{rsi[i]:.0f} (cross {rsi_lo:.0f})")


def rsi30_bblo_signal(allbars: List[dict], now_t, pc: float, gap_min: float = 14.0, gap_max: float = 9999.0,
                      rsi_thr: float = 30.0, win: Tuple[int, int] = (570, 720),
                      price: Tuple[float, float] = (3.0, 20.0), n: int = 14, bb_n: int = 20, bb_k: float = 2.0,
                      act_win: int = 30, act_min: int = 10,
                      tp: float = 0.20) -> Optional[Tuple[float, float, str]]:
    """Setup ④ (recherche point-in-time, bande 14-20) — réplique EXACTEMENT la brique
    `rsi^30 & c<bbLo` + gate liquidité `act_30>=10` du générateur :
      - gap (plus-haut du jour depuis la 1re bougie, PM inclus, vs clôture veille) >= gap_min.
        ⚠️ PAS de plafond de gap par défaut (gap_max=9999) : comme dans search_bands, la bande 14-20
        signifie « a ATTEINT >=14 % », l'entrée peut survenir même si le gap a depuis dépassé 20 %
        (rebond de survente). Mettre gap_max=20 pour borner (change l'edge mesuré).
      - RSI(14) recroise rsi_thr (=30) à la hausse (rsi[i-1] < 30 <= rsi[i])
      - clôture SOUS la bande de Bollinger basse (c < bb_lo), bb_n=20/k=2
      - >= act_min (=10) bougies actives (vol>0) sur les act_win (=30) dernières. PAS de gate verte.
    Renvoie (entry, tp, desc) ou None. Univers PM-liquidité géré EN AMONT par le terminator."""
    up = [b for b in allbars if b['t'] <= now_t]
    if len(up) < max(n, bb_n, act_win) + 2 or not pc or pc <= 0:
        return None
    i = len(up) - 1; bi = up[i]
    if not (win[0] <= _hm(bi['t']) <= win[1]):
        return None
    c_i = bi['c']
    if not (price[0] <= c_i <= price[1]):                     # prix exécutable (pas de gate verte)
        return None
    hod = max(b['h'] for b in up); gap = (hod - pc) / pc * 100.0
    if not (gap_min <= gap <= gap_max):
        return None
    c = np.array([b['c'] for b in up], float)
    rsi = _rsi(c, n)
    if not (rsi[i - 1] < rsi_thr <= rsi[i]):                  # RSI recroise 30 à la hausse
        return None
    ma = _sma(c, bb_n); sd = _rstd(c, bb_n); bb_lo = ma - bb_k * sd
    if not (c_i < bb_lo[i]):                                  # clôture sous Bollinger basse
        return None
    start = max(0, i - act_win + 1)
    active = sum(1 for b in up[start:i + 1] if (b['v'] or 0) > 0)
    if active < act_min:                                     # liquidité : >=10 bougies actives/30
        return None
    return (float(c_i), float(tp), f"rsi30_bblo gap{gap:.0f}% RSI{rsi[i-1]:.0f}->{rsi[i]:.0f} c<bbLo{bb_lo[i]:.2f}")


def rsi20_30_signal(allbars: List[dict], now_t, pc: float, gap_min: float = 5.0, gap_max: float = 9999.0,
                    win: Tuple[int, int] = (570, 720), price: Tuple[float, float] = (3.0, 20.0),
                    n: int = 14, tp: float = 0.20) -> Optional[Tuple[float, float, str]]:
    """Setup n°1 (recherche point-in-time, bande 5-7) — réplique EXACTEMENT la brique `rsi^20 & rsi^30` :
      - RSI(14) SAUTE de <20 à >=30 en UNE bougie (rsi[i-1] < 20 ET rsi[i] >= 30) = rebond violent
        de survente profonde. (PAS de gate verte, PAS de gate liq : la liq pm0.35 est gérée EN AMONT
        par le terminator via PM_LIQ_MIN_FRAC.)
      - gap (plus-haut du jour vs clôture veille) >= gap_min. ⚠️ PAS de plafond (gap_max=9999) = fidèle
        au backtest (« a atteint >=5% ») -> chevauche les autres bandes. Mettre gap_max=7 pour borner.
      - prix dans [price], fenêtre horaire [win].
    Renvoie (entry, tp, desc) ou None."""
    up = [b for b in allbars if b['t'] <= now_t]
    if len(up) < n + 2 or not pc or pc <= 0:
        return None
    i = len(up) - 1; bi = up[i]
    if not (win[0] <= _hm(bi['t']) <= win[1]):
        return None
    c_i = bi['c']
    if not (price[0] <= c_i <= price[1]):                     # prix exécutable (pas de gate verte)
        return None
    hod = max(b['h'] for b in up); gap = (hod - pc) / pc * 100.0
    if not (gap_min <= gap <= gap_max):
        return None
    rsi = _rsi([b['c'] for b in up], n)
    if not (rsi[i - 1] < 20.0 and rsi[i] >= 30.0):           # saut <20 -> >=30 (cross 20 ET 30 à la fois)
        return None
    return (float(c_i), float(tp), f"rsi20_30 gap{gap:.0f}% RSI{rsi[i-1]:.0f}->{rsi[i]:.0f} (saut 20&30)")


def oversold_roc_signal(allbars: List[dict], now_t, pc: float, gap_min: float = 30.0, gap_max: float = 9999.0,
                        win: Tuple[int, int] = (570, 720), price: Tuple[float, float] = (3.0, 20.0),
                        stoch_n: int = 14, roc_n: int = 10, tp: float = 0.15) -> Optional[Tuple[float, float, str]]:
    """Setup n°3 (recherche point-in-time, bande 30-50) — réplique EXACTEMENT `stoch<20 & roc>0`
    (identique à `will<-80 & roc>0` : %R = %K-100, donc %K<20 ⟺ %R<-80) :
      - stochastique %K(14) < 20 (survente)
      - ROC(10) > 0  <=>  close[i] > close[i-10]  (momentum haussier)
      - gap (plus-haut du jour vs clôture veille) >= 30. ⚠️ PAS de plafond (gap_max=9999) = fidèle au
        backtest (« a atteint >=30% »). PAS de gate verte, PAS de gate liq.
      - prix dans [price], fenêtre [win], warmup >= 16 bougies (RSI/stoch réchauffés).
    Renvoie (entry, tp, desc) ou None. Univers PM-liquidité géré EN AMONT par le terminator."""
    up = [b for b in allbars if b['t'] <= now_t]
    if len(up) < max(stoch_n, roc_n) + 2 or not pc or pc <= 0:
        return None
    i = len(up) - 1; bi = up[i]
    if not (win[0] <= _hm(bi['t']) <= win[1]):
        return None
    c_i = bi['c']
    if not (price[0] <= c_i <= price[1]):                     # prix exécutable (pas de gate verte)
        return None
    hod = max(b['h'] for b in up); gap = (hod - pc) / pc * 100.0
    if not (gap_min <= gap <= gap_max):
        return None
    wb = up[-stoch_n:]                                        # stochastique %K(14) = position dans le range
    hh = max(b['h'] for b in wb); ll = min(b['l'] for b in wb)
    k = (c_i - ll) / (hh - ll) * 100.0 if hh > ll else 50.0
    if not (k < 20.0):                                        # survente
        return None
    if not (c_i > up[i - roc_n]['c']):                        # ROC(10) > 0
        return None
    return (float(c_i), float(tp), f"oversold_roc gap{gap:.0f}% stoch{k:.0f}<20 ROC>0")


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
