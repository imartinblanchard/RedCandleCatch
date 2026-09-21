#!/usr/bin/env python3
"""
Dip NORMALISÉ-VOLATILITÉ vs dip FIXE, sur les gappers PM (gap 10-20), OOS train/test.

Idée : au lieu d'un seuil fixe (-6%), déclencher quand la bougie descend de k × la
VOLATILITÉ du titre. sigma = écart-type glissant du mouvement intra-bougie (c-o)/o sur
les 20 dernières bougies (point-in-time). Un titre volatil a besoin d'un gros dip, un
calme d'un petit -> chacun trigger sur un repli significatif POUR LUI.

Reste FIXE : gap 10-20, prix 3-20, stop -10%, act +5%, trail 2%, 1 entrée/jour, backstop 15:55.
Lancer : source .venv/bin/activate && python research/test_dip_volnorm.py
"""
import os, json
import numpy as np, pandas as pd
import engine
R = os.path.dirname(__file__)

STOP, ACT, TRAIL = 0.10, 0.05, 0.02
PMIN, PMAX = 3.0, 20.0
ES, HARD, XE = 570, 955, 960     # 9:30 / 15:55 (entrée+sortie forcée) / 16:00
WIN = 20                         # fenêtre du sigma glissant
def slip_of(p): return max(0.0015, 0.015 / p)

FIXED = [0.04, 0.045, 0.05]
KS = []   # variantes volatilité abandonnées (testées, sans edge)


def exit_pnl(mins, h, l, c, i):
    e = float(c[i]); sl = slip_of(e); ef = e * (1 + sl)
    st, ac = e * (1 - STOP), e * (1 + ACT); activ = False; peak = e; ex = None
    for j in range(i + 1, len(c)):
        if mins[j] < ES or mins[j] >= XE:
            continue
        if mins[j] >= HARD:                       # backstop 15:55
            ex = c[j]; break
        if not activ:
            if l[j] <= st: ex = st; break
            peak = max(peak, h[j])
            if h[j] >= ac: activ = True
        else:
            ts = peak * (1 - TRAIL)
            if l[j] <= ts: ex = ts; break
            peak = max(peak, h[j])
    if ex is None:
        win = c[(mins >= ES) & (mins < XE)]
        ex = float(win[-1]) if len(win) else e
    return (ex * (1 - sl) - ef) / ef * 100


def find_entry(mins, o, c, move, sigma, thr_fixed=None, k=None):
    """1re bougie de la fenêtre : dip fixe (thr_fixed) OU normalisé (move <= -k*sigma)."""
    for i in range(len(c)):
        if mins[i] < ES or mins[i] >= HARD:
            continue
        if not (o[i] > 0 and PMIN <= c[i] <= PMAX):
            continue
        if thr_fixed is not None:
            if move[i] <= -thr_fixed:
                return i
        else:
            s = sigma[i]
            if s == s and s > 0 and move[i] <= -k * s:
                return i
    return -1


def main():
    df = engine.load_table(os.path.join(R, 'candles.parquet'))
    gap = {(x['ticker'], x['date']): x['gap'] for x in json.load(open(os.path.join(R, 'gappers.json')))}
    rows = []  # (date, variant, pnl)
    dates_all = set()
    for (tk, date), g in df.groupby(['ticker', 'date'], sort=False):
        gp = gap.get((tk, date))
        if gp is None or not (10 <= gp < 20):
            continue
        g = g.reset_index(drop=True)
        mins = (g['datetime'].str.slice(0, 2).astype(int) * 60 + g['datetime'].str.slice(3, 5).astype(int)).values
        o = g['o'].values; h = g['h'].values; l = g['l'].values; c = g['c'].values
        move = np.divide(c - o, o, out=np.zeros_like(c), where=o > 0)
        # sigma glissant du mouvement intra-bougie, point-in-time (décalé de 1)
        sigma = pd.Series(move).rolling(WIN, min_periods=8).std().shift(1).values
        dates_all.add(date)
        for pct in FIXED:
            i = find_entry(mins, o, c, move, sigma, thr_fixed=pct)
            if i >= 0:
                rows.append((date, f'fixe -{pct*100:.1f}%', exit_pnl(mins, h, l, c, i)))
        for k in KS:
            i = find_entry(mins, o, c, move, sigma, k=k)
            if i >= 0:
                rows.append((date, f'vol {k:.1f}sigma', exit_pnl(mins, h, l, c, i)))

    L = pd.DataFrame(rows, columns=['date', 'variant', 'pnl'])
    split = sorted(dates_all)[len(dates_all) // 2]
    test_days = len({d for d in dates_all if d >= split})
    print(f"OOS split au {split} | {test_days} jours de bourse en TEST\n")
    print("=== TEST (out-of-sample) — détail par seuil de dip ===")
    print(f"{'dip':6}{'n':>6}{'tr/j':>6}{'win%':>6}{'gain+':>7}{'perte-':>8}{'exp/tr':>8}{'pf':>6}{'t':>5}{'TOTAL%':>8}")
    for p in FIXED:
        v = f'fixe -{p*100:.1f}%'
        x = L[(L.variant == v) & (L.date >= split)]['pnl'].values
        if len(x) < 2:
            continue
        wins = x[x > 0]; losses = x[x < 0]
        pf = wins.sum() / (-losses.sum() or 1e-9)
        t = x.mean() / (x.std(ddof=1) / np.sqrt(len(x)))
        print(f"-{p*100:.1f}%  {len(x):>6}{len(x)/test_days:>6.1f}{100*(x>0).mean():>5.0f}%"
              f"{wins.mean():>+6.1f}%{losses.mean():>+7.1f}%{x.mean():>+7.2f}%{pf:>6.2f}{t:>5.1f}{x.sum():>+7.0f}%")
    print("\ntr/j = trades par jour (fréquence) | TOTAL% = somme des P&L (mise fixe, sans compounding)")


if __name__ == '__main__':
    main()
