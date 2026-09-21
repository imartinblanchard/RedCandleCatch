#!/usr/bin/env python3
"""
PM-HIGH vs OPEN : quelle DÉFINITION du gap sélectionne les meilleurs trades ?

- open_gap  = (open 9:30 - clôture veille) / clôture veille   (ce que mesure gappers.json)
- pm_gap    = (plus-haut 04:00-09:29 - clôture veille) / ...   (ce que mesure le bot LIVE)

On calcule les DEUX pour chaque ticker-jour, on rejoue la stratégie live
(dip -5%, stop -10%, act +5%, trail 2%, prix 3-20, 1 entrée/jour), puis on compare
les stats selon la définition utilisée pour SÉLECTIONNER (mêmes trades, tri différent).

Lancer : source .venv/bin/activate && python research/test_gap_def.py
"""
import os, json
import numpy as np, pandas as pd
import engine
R = os.path.dirname(__file__)

DIP, STOP, ACT, TRAIL = 0.05, 0.10, 0.05, 0.02
PMIN, PMAX = 3.0, 20.0
ES, EE, XE = 570, 960, 990          # 9:30 / 16:00 / 16:30
def slip_of(p): return max(0.0015, 0.015 / p)


def trade_pnl(mins, o, h, l, c):
    """1re entrée dip -5% dans la fenêtre -> P&L two-phase (ou None si pas de trade)."""
    chg = np.divide(c - o, o, out=np.full_like(c, 1.0), where=o > 0)
    idx = np.where((mins >= ES) & (mins < EE) & (chg <= -DIP) & (c >= PMIN) & (c <= PMAX))[0]
    if not len(idx):
        return None
    i = idx[0]; e = float(c[i]); sl = slip_of(e); ef = e * (1 + sl)
    st, ac = e * (1 - STOP), e * (1 + ACT); activ = False; peak = e; ex = None
    for j in range(i + 1, len(c)):
        if not (ES <= mins[j] < XE):
            continue
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


def main():
    df = engine.load_table(os.path.join(R, 'candles.parquet'))
    rows = []
    for (tk, date), g in df.groupby(['ticker', 'date'], sort=False):
        g = g.reset_index(drop=True)
        mins = (g['datetime'].str.slice(0, 2).astype(int) * 60
                + g['datetime'].str.slice(3, 5).astype(int)).values
        o = g['o'].values; h = g['h'].values; l = g['l'].values; c = g['c'].values
        pc = float(g['prev_close'].iloc[0]) if 'prev_close' in g else np.nan
        if not pc or pc <= 0 or np.isnan(pc):
            continue
        pm = (mins >= 240) & (mins < 570)          # 04:00-09:29
        at930 = np.where(mins == 570)[0]           # bougie d'ouverture 9:30
        if not pm.any() or not len(at930):
            continue
        pm_gap = (h[pm].max() - pc) / pc * 100
        open_gap = (o[at930[0]] - pc) / pc * 100
        pnl = trade_pnl(mins, o, h, l, c)
        if pnl is None:
            continue
        rows.append((tk, date, open_gap, pm_gap, pnl))

    L = pd.DataFrame(rows, columns=['ticker', 'date', 'open_gap', 'pm_gap', 'pnl'])
    print(f"{len(L)} ticker-jours avec un trade\n")

    def stats(sub, label):
        if len(sub) == 0:
            print(f"  {label:28} n=0"); return
        x = sub.pnl.values
        pf = x[x > 0].sum() / (-x[x < 0].sum() or 1e-9)
        t = x.mean() / (x.std(ddof=1) / np.sqrt(len(x))) if len(x) > 1 else 0
        print(f"  {label:28} n={len(sub):>5}  exp={x.mean():+.2f}%/tr  win={100*(x>0).mean():>3.0f}%  "
              f"pf={pf:.2f}  total={x.sum():>+7.0f}%  t={t:>4.1f}")

    for lo, hi in [(10, 20), (20, 50), (50, 300), (10, 300)]:
        print(f"=== TRANCHE {lo}-{hi}% : sélection par OPEN-gap vs PM-high ===")
        stats(L[(L.open_gap >= lo) & (L.open_gap < hi)], f"OPEN-gap {lo}-{hi}")
        stats(L[(L.pm_gap >= lo) & (L.pm_gap < hi)],    f"PM-high {lo}-{hi} (LIVE)")
        print()

    print("=== POPULATIONS : combien la définition déplace-t-elle de trades ? (tranche 10-20) ===")
    O = set(L.index[(L.open_gap >= 10) & (L.open_gap < 20)])
    P = set(L.index[(L.pm_gap >= 10) & (L.pm_gap < 20)])
    inter = O & P
    print(f"  OPEN 10-20: {len(O)}  |  PM 10-20: {len(P)}  |  communs: {len(inter)}")
    stats(L.loc[list(O - P)], "seulement OPEN (pas PM)")
    stats(L.loc[list(P - O)], "seulement PM (pas OPEN)")
    stats(L.loc[list(inter)], "les deux")

    print("\n=== les 'runners fadés' : PM 10-20 MAIS open < 5% (thèse de la stratégie) ===")
    stats(L[(L.pm_gap >= 10) & (L.pm_gap < 20) & (L.open_gap < 5)], "PM 10-20 & open<5")


if __name__ == '__main__':
    main()
