#!/usr/bin/env python3
"""Re-optimisation de la SORTIE pour la config gap 10-20% + dip -5%.

La sortie actuelle (stop -10%, activation +5%, trail 4%) a été calibrée sur des
gappers >=50% (bien plus volatils). Est-elle adaptée à des gappers 10-20% ?

Balayage : stop × activation × trailing. L'entrée est détectée UNE fois par
ticker-jour, puis toutes les variantes de sortie sont simulées dessus.
⚠️ 64 combinaisons => risque de sur-ajustement élevé : on juge sur le TEST."""
import os, json, itertools
import numpy as np, pandas as pd
import engine
R = os.path.dirname(__file__)

DIP = 0.05
STOPS  = [0.05, 0.07, 0.10, 0.15]
ACTS   = [0.02, 0.03, 0.05, 0.08]
TRAILS = [0.02, 0.03, 0.04, 0.06]
CUT = '2026-06-01'
def slip_of(p): return max(0.0015, 0.015 / p)

df = engine.load_table(os.path.join(R, 'candles.parquet'))
gap = {(x['ticker'], x['date']): x['gap'] for x in json.load(open(os.path.join(R, 'gappers.json')))}
combos = list(itertools.product(STOPS, ACTS, TRAILS))

rows = []
for (tk, date), g in df.groupby(['ticker', 'date'], sort=False):
    gp = gap.get((tk, date))
    if gp is None or not (10 <= gp < 20):
        continue
    g = g.reset_index(drop=True)
    mins = (g['datetime'].str.slice(0, 2).astype(int) * 60
            + g['datetime'].str.slice(3, 5).astype(int)).values
    o = g['o'].values; h = g['h'].values; l = g['l'].values; c = g['c'].values
    rth = (mins >= 570) & (mins < 990)
    if not rth.any():
        continue
    last_close = float(c[rth][-1])
    chg = np.divide(c - o, o, out=np.zeros_like(c), where=o > 0)
    idx = np.where((mins >= 570) & (mins < 960) & (chg <= -DIP) & (c >= 3))[0]
    if len(idx) == 0:
        continue
    i = idx[0]
    eraw = float(c[i]); sl = slip_of(eraw)
    js = [j for j in range(i + 1, len(g)) if rth[j]]

    for (S, A, T) in combos:
        st = eraw * (1 - S); ac = eraw * (1 + A)
        activ = False; peak = eraw; ex = None
        for j in js:
            if not activ:
                if l[j] <= st: ex = st; break
                peak = max(peak, h[j])
                if h[j] >= ac: activ = True
            else:
                ts = peak * (1 - T)
                if l[j] <= ts: ex = ts; break
                peak = max(peak, h[j])
        if ex is None:
            ex = last_close
        rows.append((date, S, A, T, (ex * (1 - sl) - eraw) / eraw * 100))

L = pd.DataFrame(rows, columns=['date', 'stop', 'act', 'trail', 'pnl'])

res = []
for (S, A, T), s in L.groupby(['stop', 'act', 'trail']):
    tr = s[s.date < CUT].pnl; te = s[s.date >= CUT].pnl
    pf = s.pnl[s.pnl > 0].sum() / (-s.pnl[s.pnl < 0].sum() or 1e-9)
    t = s.pnl.mean() / (s.pnl.std(ddof=1) / np.sqrt(len(s)))
    res.append(dict(stop=S, act=A, trail=T, n=len(s), exp=s.pnl.mean(),
                    win=100 * (s.pnl > 0).mean(), pf=pf,
                    train=tr.mean() if len(tr) else np.nan,
                    test=te.mean() if len(te) else np.nan, t=t))
Rdf = pd.DataFrame(res)

def show(d, title, k=8):
    print(f"\n=== {title} ===")
    print(f"{'stop':>6}{'act':>6}{'trail':>7}{'n':>6}{'exp':>8}{'win':>6}{'pf':>7}{'train':>8}{'test':>8}{'t':>7}")
    for _, r in d.head(k).iterrows():
        print(f"{r['stop']*100:>5.0f}%{r['act']*100:>5.0f}%{r['trail']*100:>6.0f}%{r['n']:>6.0f}"
              f"{r['exp']:>+8.2f}{r['win']:>5.0f}%{r['pf']:>7.2f}{r['train']:>+8.2f}{r['test']:>+8.2f}{r['t']:>7.2f}")

base = Rdf[(Rdf.stop == 0.10) & (Rdf.act == 0.05) & (Rdf.trail == 0.04)]
show(base, "CONFIG ACTUELLE (stop 10 / act 5 / trail 4)", 1)
show(Rdf.sort_values('exp', ascending=False), "TOP par EXPECTANCY (risque de sur-ajustement)")
show(Rdf.sort_values('test', ascending=False), "TOP par période TEST (hors échantillon)")
show(Rdf.sort_values('t', ascending=False), "TOP par t-stat (robustesse)")

print("\n=== EFFET DE CHAQUE PARAMÈTRE (moyenne sur toutes les autres valeurs) ===")
for col, vals in [('stop', STOPS), ('act', ACTS), ('trail', TRAILS)]:
    print(f"  {col}:  " + "   ".join(
        f"{v*100:.0f}%={Rdf[Rdf[col]==v]['exp'].mean():+.2f}" for v in vals))
