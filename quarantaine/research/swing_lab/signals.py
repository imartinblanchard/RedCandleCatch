#!/usr/bin/env python3
"""Stratégies SWING daily pour un seul titre. Chacune renvoie une POSITION cible (1=long/0=flat)
par jour, CAUSALE (info jusqu'à la clôture du jour i ; le moteur exécute le lendemain).
Indicateurs daily : SMA/EMA, RSI, Donchian (cassure N jours), ROC (momentum). REGISTRY en bas."""
import numpy as np, pandas as pd


def _sma(c, n): return pd.Series(c).rolling(n, min_periods=1).mean().to_numpy()
def _ema(c, n): return pd.Series(c).ewm(span=n, adjust=False).mean().to_numpy()
def _roc(c, n):
    out = np.zeros_like(c); out[n:] = c[n:] / c[:-n] - 1; return out


def _rsi(c, n=14):
    d = np.diff(c, prepend=c[0]); up = np.where(d > 0, d, 0.0); dn = np.where(d < 0, -d, 0.0)
    ru = pd.Series(up).ewm(alpha=1 / n, adjust=False).mean().to_numpy()
    rd = pd.Series(dn).ewm(alpha=1 / n, adjust=False).mean().to_numpy()
    return 100 - 100 / (1 + ru / np.where(rd == 0, 1e-9, rd))


def _from_entry_exit(entry, exit_):
    """Machine à états : entre sur `entry`, reste long jusqu'à `exit_`. Causal."""
    pos = np.zeros(len(entry)); live = False
    for i in range(len(entry)):
        if not live and entry[i]:
            live = True
        elif live and exit_[i]:
            live = False
        pos[i] = 1.0 if live else 0.0
    return pos


def sma_cross(df, P):
    """Suiveur de tendance : long quand SMA rapide > SMA lente."""
    c = df['c'].to_numpy(float)
    return (_sma(c, P.get('fast', 50)) > _sma(c, P.get('slow', 200))).astype(float)


def donchian_breakout(df, P):
    """Cassure de canal (type tortue) : long si clôture > plus-haut des N jours PRÉCÉDENTS,
    sortie si clôture < plus-bas des M jours précédents."""
    c = df['c'].to_numpy(float)
    nin, nout = P.get('n_in', 50), P.get('n_out', 20)
    hi = pd.Series(c).rolling(nin, min_periods=1).max().shift(1).to_numpy()
    lo = pd.Series(c).rolling(nout, min_periods=1).min().shift(1).to_numpy()
    return _from_entry_exit(c > hi, c < lo)


def trend_pullback(df, P):
    """Achat du repli en tendance : régime haussier (clôture > SMA200) ET RSI faible (repli),
    sortie quand le RSI repasse au-dessus d'un seuil. 'Buy the dip' en tendance."""
    c = df['c'].to_numpy(float)
    regime = c > _sma(c, P.get('trend', 200))
    rsi = _rsi(c, P.get('rsi_n', 14))
    entry = regime & (rsi < P.get('rsi_lo', 35))
    exit_ = rsi > P.get('rsi_hi', 55)
    return _from_entry_exit(entry, exit_)


def rsi_meanrev(df, P):
    """Retour à la moyenne : long sur RSI survendu, sortie sur RSI haut. Optionnel : filtre tendance."""
    c = df['c'].to_numpy(float)
    rsi = _rsi(c, P.get('rsi_n', 14))
    entry = rsi < P.get('rsi_lo', 30)
    if P.get('trend'):
        entry = entry & (c > _sma(c, P['trend']))
    return _from_entry_exit(entry, rsi > P.get('rsi_hi', 50))


def momentum(df, P):
    """Momentum : long tant que le rendement sur N jours (~3 mois) est positif."""
    c = df['c'].to_numpy(float)
    return (_roc(c, P.get('n', 63)) > P.get('thr', 0.0)).astype(float)


def ema_cross(df, P):
    """Croisement d'EMA (plus réactif que SMA)."""
    c = df['c'].to_numpy(float)
    return (_ema(c, P.get('fast', 20)) > _ema(c, P.get('slow', 50))).astype(float)


def _atr(h, l, c, n=14):
    pc = np.concatenate([[c[0]], c[:-1]])
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    return pd.Series(tr).ewm(alpha=1 / n, adjust=False).mean().to_numpy()


def macd_trend(df, P):
    """MACD : long quand l'histogramme (MACD − signal) est positif."""
    c = df['c'].to_numpy(float)
    line = _ema(c, P.get('fast', 12)) - _ema(c, P.get('slow', 26))
    sig = _ema(line, P.get('sig', 9))
    return ((line - sig) > 0).astype(float)


def bollinger_meanrev(df, P):
    """Retour à la moyenne : achat sous la bande basse, sortie au retour sur la moyenne."""
    c = df['c'].to_numpy(float); s = pd.Series(c)
    mid = s.rolling(P.get('n', 20), min_periods=1).mean().to_numpy()
    sd = s.rolling(P.get('n', 20), min_periods=1).std(ddof=0).fillna(0).to_numpy()
    k = P.get('k', 2.0)
    return _from_entry_exit(c < mid - k * sd, c >= mid)


def bollinger_breakout(df, P):
    """Cassure de volatilité : long au-dessus de la bande haute, sortie sous la moyenne."""
    c = df['c'].to_numpy(float); s = pd.Series(c)
    mid = s.rolling(P.get('n', 20), min_periods=1).mean().to_numpy()
    sd = s.rolling(P.get('n', 20), min_periods=1).std(ddof=0).fillna(0).to_numpy()
    k = P.get('k', 2.0)
    return _from_entry_exit(c > mid + k * sd, c < mid)


def keltner_breakout(df, P):
    """Cassure du canal de Keltner (EMA + mult·ATR), sortie sous l'EMA."""
    c = df['c'].to_numpy(float); h = df['h'].to_numpy(float); l = df['l'].to_numpy(float)
    e = _ema(c, P.get('n', 20)); a = _atr(h, l, c, P.get('atr_n', 14)); m = P.get('mult', 2.0)
    return _from_entry_exit(c > e + m * a, c < e)


def high_52w(df, P):
    """Cassure du plus-haut des N jours (~52 sem.=252), sortie sous une SMA."""
    c = df['c'].to_numpy(float)
    win = P.get('win', 252)
    hh = pd.Series(c).rolling(win, min_periods=1).max().shift(1).to_numpy()
    sma_exit = _sma(c, P.get('exit_sma', 50))
    return _from_entry_exit(c >= hh, c < sma_exit)


def stochastic(df, P):
    """Stochastique : long quand %K sort du survendu, sortie en surachat (optionnel filtre tendance)."""
    c = df['c'].to_numpy(float); h = df['h'].to_numpy(float); l = df['l'].to_numpy(float)
    n = P.get('n', 14)
    hh = pd.Series(h).rolling(n, min_periods=1).max().to_numpy()
    ll = pd.Series(l).rolling(n, min_periods=1).min().to_numpy()
    k = np.where(hh > ll, (c - ll) / np.where(hh > ll, hh - ll, 1) * 100, 50.0)
    entry = k < P.get('lo', 20)
    if P.get('trend'):
        entry = entry & (c > _sma(c, P['trend']))
    return _from_entry_exit(entry, k > P.get('hi', 80))


def supertrend(df, P):
    """Supertrend (ATR) : long tant que la tendance est haussière. Classique du swing."""
    c = df['c'].to_numpy(float); h = df['h'].to_numpy(float); l = df['l'].to_numpy(float)
    a = _atr(h, l, c, P.get('atr_n', 10)); m = P.get('mult', 3.0)
    hl2 = (h + l) / 2.0; up = hl2 + m * a; dn = hl2 - m * a
    fu = up.copy(); fd = dn.copy(); trend = np.ones(len(c))
    for i in range(1, len(c)):
        fu[i] = min(up[i], fu[i - 1]) if c[i - 1] <= fu[i - 1] else up[i]
        fd[i] = max(dn[i], fd[i - 1]) if c[i - 1] >= fd[i - 1] else dn[i]
        trend[i] = 1 if c[i] > fu[i - 1] else (-1 if c[i] < fd[i - 1] else trend[i - 1])
    return (trend > 0).astype(float)


def rsi2_meanrev(df, P):
    """SWING mean-reversion court-terme (style Connors) : acheter un repli survendu RSI(2) bas EN
    TENDANCE haussière (prix > SMA200), revendre vite au rebond (prix > SMA5 ou RSI(2) haut).
    Tenue typique = 1-5 jours = vrai swing. Le classique à edge documenté sur indices/ETF."""
    c = df['c'].to_numpy(float)
    r = _rsi(c, P.get('rsi_n', 2))
    entry = (r < P.get('lo', 10))
    if P.get('trend'):
        entry = entry & (c > _sma(c, P['trend']))
    exit_ = (c > _sma(c, P.get('exit_sma', 5))) | (r > P.get('hi', 70))
    return _from_entry_exit(entry, exit_)


REGISTRY = {
    'rsi2_meanrev': rsi2_meanrev,
    'sma_cross': sma_cross,
    'ema_cross': ema_cross,
    'donchian_breakout': donchian_breakout,
    'trend_pullback': trend_pullback,
    'rsi_meanrev': rsi_meanrev,
    'momentum': momentum,
    'macd_trend': macd_trend,
    'bollinger_meanrev': bollinger_meanrev,
    'bollinger_breakout': bollinger_breakout,
    'keltner_breakout': keltner_breakout,
    'high_52w': high_52w,
    'stochastic': stochastic,
    'supertrend': supertrend,
}
