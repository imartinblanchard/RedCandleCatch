#!/usr/bin/env python3
"""
FORWARD-TEST : la stratégie tient-elle sur la data qu'on a RÉELLEMENT collectée en
temps réel (data/collected/, SANS biais du survivant) ?

Rejoue EXACTEMENT le bot live :
  - univers = les éligibles réels du jour (eligibles.csv, déjà filtrés gap/prix/liquidité)
  - dip adaptatif : -5% si gapper PM (is_premarket), -1,5% si runner post-open
  - entrée = 1re bougie 1-min (c-o)/o <= -dip, APRÈS l'heure d'éligibilité, prix 3-20$, en RTH
  - sortie 2-phases : STOP -10% -> à +5% -> TRAIL 2% (sur signal price), sortie forcée 15:55
  - slippage réaliste ; P&L BRUT (hors commission)
"""
import os
import numpy as np
import pandas as pd

R = os.path.dirname(os.path.abspath(__file__))
COLLECTED = os.path.join(os.path.dirname(R), 'data', 'collected')
BARS_DIR = os.path.join(COLLECTED, 'bars')

DIP_PM, DIP_PO = 0.05, 0.015
STOP, ACT, TRAIL = 0.10, 0.05, 0.02
PMIN, PMAX = 3.0, 20.0
RTH, HARD, XE = 570, 955, 960     # 09:30 / 15:55 / 16:00
def slip_of(p): return max(0.0015, 0.015 / p)


def to_min(s):  # 'HH:MM' -> minutes
    return int(s[:2]) * 60 + int(s[3:5])


def sim(g, dip, added_min):
    """Un ticker-jour -> pnl% brut, ou None si pas d'entrée."""
    mins = g['datetime'].map(to_min).values
    o, h, l, c = g['o'].values, g['h'].values, g['l'].values, g['c'].values
    start = max(RTH, added_min)                       # pas avant d'être éligible
    move = np.divide(c - o, o, out=np.zeros_like(c), where=o > 0)
    cand = np.where((mins >= start) & (mins < HARD) & (move <= -dip)
                    & (c >= PMIN) & (c <= PMAX))[0]
    if not len(cand):
        return None
    i = cand[0]; e = float(c[i]); sl = slip_of(e); ef = e * (1 + sl)
    st, ac = e * (1 - STOP), e * (1 + ACT); activ = False; peak = e; ex = None
    for j in range(i + 1, len(c)):
        if mins[j] < RTH or mins[j] >= XE:
            continue
        if mins[j] >= HARD:                            # sortie forcée 15:55
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
        w = c[(mins >= RTH) & (mins < XE)]
        ex = float(w[-1]) if len(w) else e
    return (ex * (1 - sl) - ef) / ef * 100


def stats(x):
    x = np.array(x)
    if len(x) < 2:
        return None
    wins, losses = x[x > 0], x[x < 0]
    pf = wins.sum() / (-losses.sum() or 1e-9)
    t = x.mean() / (x.std(ddof=1) / np.sqrt(len(x)))
    return dict(n=len(x), win=100 * (x > 0).mean(), gain=wins.mean() if len(wins) else 0,
                loss=losses.mean() if len(losses) else 0, exp=x.mean(), pf=pf, t=t, tot=x.sum())


def main():
    elig = pd.read_csv(os.path.join(COLLECTED, 'eligibles.csv'))
    elig['added'] = elig['added'].fillna('09:30')
    key = {(r.date, r.ticker): (bool(r.is_premarket), to_min(str(r.added)))
           for r in elig.itertuples()}
    pm, po = [], []
    ndays = set()
    for f in sorted(os.listdir(BARS_DIR)):
        if not f.endswith('.parquet'):
            continue
        date = f[:-8]
        df = pd.read_parquet(os.path.join(BARS_DIR, f))
        for tk, g in df.groupby('ticker', sort=False):
            k = key.get((date, tk))
            if k is None:
                continue
            is_pm, added_min = k
            p = sim(g.reset_index(drop=True), DIP_PM if is_pm else DIP_PO, added_min)
            if p is not None:
                ndays.add(date)
                (pm if is_pm else po).append(p)

    hdr = f"{'':10}{'n':>5}{'tr/j':>6}{'win%':>6}{'gain+':>7}{'perte-':>8}{'exp/tr':>8}{'pf':>6}{'t':>6}{'TOTAL%':>8}"
    print(f"FORWARD-TEST sur data collectée (SANS biais survivant) | {len(ndays)} jours\n")
    print(hdr)
    for lab, arr in [('PM -5%', pm), ('post-open -1,5%', po), ('COMBINÉ', pm + po)]:
        s = stats(arr)
        if not s:
            print(f"{lab:10}  (n<2 : {len(arr)} trade)"); continue
        print(f"{lab:10}{s['n']:>5}{s['n']/max(len(ndays),1):>6.1f}{s['win']:>5.0f}%"
              f"{s['gain']:>+6.1f}%{s['loss']:>+7.1f}%{s['exp']:>+7.2f}%{s['pf']:>6.2f}{s['t']:>6.1f}{s['tot']:>+7.0f}%")
    print("\nP&L BRUT (hors commission). Échantillon PETIT -> indicatif, pas concluant.")


if __name__ == '__main__':
    main()
