#!/usr/bin/env python3
"""Valide la config candidate (filtre $vol sur la BOUGIE DE DIP + activation) sur les 8 MOIS
d'historique (164 jours). ⚠️ Données à BIAIS DU SURVIVANT -> borne SUPÉRIEURE. Sert à
vérifier la DIRECTION et la MAGNITUDE sur grand échantillon (vs 6 jours collectés)."""
import os, json
import numpy as np
import pandas as pd
import backtest_intraday as B

HERE = os.path.dirname(os.path.abspath(__file__)); DATA = os.path.join(HERE, 'data')
STOP, TRAIL = 0.10, 0.02
PMIN, PMAX = 3.0, 20.0


def sim(g, dip, ACT):
    mins = (g['datetime'].str.slice(0, 2).astype(int) * 60 + g['datetime'].str.slice(3, 5).astype(int)).values
    o, h, l, c, v = g['o'].values, g['h'].values, g['l'].values, g['c'].values, g['v'].values
    move = np.divide(c - o, o, out=np.zeros_like(c), where=o > 0)
    cand = np.where((mins >= B.ES) & (mins < B.EE) & (move <= -dip) & (c >= PMIN) & (c <= PMAX))[0]
    if not len(cand):
        return None
    i = cand[0]; e = float(c[i]); dvol = float(v[i] * c[i])
    st, ac = e * (1 - STOP), e * (1 + ACT); activ = False; peak = e; ex = None
    for j in range(i + 1, len(c)):
        if not (B.ES <= mins[j] < B.XE):
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
        w = c[(mins >= B.ES) & (mins < B.XE)]; ex = float(w[-1]) if len(w) else e
    return (ex - e) / e * 100, dvol


def main():
    df = pd.read_parquet(os.path.join(DATA, 'bars_1min.parquet'))
    meta = json.load(open(os.path.join(DATA, 'meta.json')))
    groups = list(df.groupby(['ticker', 'date'], sort=False))
    ndays = df['date'].nunique()

    # génère tous les trades (pnl, dvol, sess) pour une activation donnée
    def gen(ACT):
        rows = []
        for (tk, date), g in groups:
            m = meta.get(f'{tk}|{date}')
            if not m:
                continue
            sess = 'post-open' if m.get('post_open') else 'PM'
            dip = 0.015 if sess == 'post-open' else 0.05
            r = sim(g, dip, ACT)
            if r:
                rows.append((r[0], r[1], sess))
        return pd.DataFrame(rows, columns=['pnl', 'dvol', 'sess'])

    def line(tag, x):
        x = np.array(x)
        if len(x) < 2:
            print(f'{tag:26} n<2'); return
        w = x[x > 0]; l = x[x < 0]; rr = w.mean() / abs(l.mean()) if len(l) else float('nan')
        pf = w.sum() / (-l.sum() or 1e-9)
        print(f'{tag:26}{len(x):>6}{len(x)/ndays:>6.1f}{100*(x>0).mean():>5.0f}%{rr:>6.2f}'
              f'{x.mean():>+7.2f}%{pf:>6.2f}{x.sum():>+8.0f}%')

    print(f'VALIDATION 8 MOIS ({ndays} jours, biais survivant = borne SUP.) — dip PM -5%/post-open -1,5%')
    print(f'{"config":26}{"n":>6}{"tr/j":>6}{"win%":>6}{"R/R":>6}{"exp/tr":>8}{"pf":>6}{"TOTAL%":>9}')
    print('-' * 73)
    for ACT in [0.05, 0.10]:
        D = gen(ACT)
        for thr, lb in [(0, 'aucun'), (100000, '>=100K'), (200000, '>=200K')]:
            sub = D[D.dvol >= thr]
            line(f'act+{int(ACT*100)}% | dip-vol {lb}', sub['pnl'].values)
        print()


if __name__ == '__main__':
    main()
