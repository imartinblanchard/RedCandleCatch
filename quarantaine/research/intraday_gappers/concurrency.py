#!/usr/bin/env python3
"""Post-open : combien de trades se CHEVAUCHENT ? pourrait-on tous les prendre ?
Mesure la concurrence (positions simultanées) et le taux de trades RATÉS selon une
capacité max de positions, à dip -1% vs -1,5%."""
import os, json
import numpy as np, pandas as pd
import backtest_intraday as B

HERE = os.path.dirname(os.path.abspath(__file__)); DATA = os.path.join(HERE, 'data')


def gen(groups, meta, DIP):
    """[(entry_dt, exit_dt)] pour les post-open runners."""
    B.DIP = DIP; out = []
    for (tk, date), g in groups:
        m = meta.get(f"{tk}|{date}")
        if not (m and m['post_open']):
            continue
        mins = (g['datetime'].str.slice(0, 2).astype(int) * 60 + g['datetime'].str.slice(3, 5).astype(int)).values
        o = g['o'].values; h = g['h'].values; l = g['l'].values; c = g['c'].values; dt = g['datetime'].values
        chg = np.divide(c - o, o, out=np.full_like(c, 1.0), where=o > 0)
        idx = np.where((mins >= B.ES) & (mins < B.EE) & (chg <= -DIP) & (c >= B.PMIN) & (c <= B.PMAX))[0]
        if not len(idx):
            continue
        i = idx[0]; e = float(c[i]); st = e*(1-B.STOP); ac = e*(1+B.ACT); activ=False; peak=e; jx=len(c)-1
        for j in range(i+1, len(c)):
            if not (B.ES <= mins[j] < B.XE): continue
            if not activ:
                if l[j] <= st: jx=j; break
                peak=max(peak,h[j])
                if h[j]>=ac: activ=True
            else:
                if l[j] <= peak*(1-B.TRAIL): jx=j; break
                peak=max(peak,h[j])
        out.append((pd.Timestamp(f"{date} {dt[i]}"), pd.Timestamp(f"{date} {dt[jx]}")))
    return out


def analyze(trades, label):
    ndays = len({e.date() for e, _ in trades})
    # concurrence : événements +1 à l'entrée, -1 à la sortie
    ev = []
    for e, x in trades:
        ev.append((e, 1)); ev.append((x, -1))
    ev.sort(key=lambda z: (z[0], z[1]))
    cur = 0; peak = 0
    for _, d in ev:
        cur += d; peak = max(peak, cur)
    # taux de prise selon capacité (simulation cap)
    print(f"\n{label} : {len(trades)} trades sur {ndays} jours ({len(trades)/ndays:.1f}/j)")
    print(f"  PIC de positions simultanées : {peak}")
    for cap in [1, 3, 5, 10, 20]:
        taken = 0; openx = []  # heures de sortie des positions ouvertes
        for e, x in sorted(trades):
            openx = [t for t in openx if t > e]     # libère les positions déjà sorties
            if len(openx) < cap:
                taken += 1; openx.append(x)
        print(f"  capacité {cap:>2} positions -> {taken}/{len(trades)} pris ({100*taken/len(trades):.0f}%)")


def main():
    df = pd.read_parquet(os.path.join(DATA, 'bars_1min.parquet'))
    meta = json.load(open(os.path.join(DATA, 'meta.json')))
    groups = list(df.groupby(['ticker', 'date'], sort=False))
    for DIP, lab in [(0.01, 'DIP -1%'), (0.015, 'DIP -1,5%')]:
        analyze(gen(groups, meta, DIP), lab)


if __name__ == '__main__':
    main()
