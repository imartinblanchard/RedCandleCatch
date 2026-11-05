#!/usr/bin/env python3
"""CORRECTION Défaut 1 : bucketer l'edge par HEURE DE 1re ÉLIGIBILITÉ (comme le 'added'
du bot live), calculée en 1-min : 1re minute où le plus-haut courant entre dans 10-20%.
Puis dip -1.5% APRÈS cette minute (comme en live), sortie déployée, liquidité 200K$.
Question : les titres qui deviennent éligibles TARD (>10:30) ont-ils un edge ?
⚠️ Dataset encore biaisé (Défaut 2 : exclut les runners qui dépassent 20% avant midi)."""
import os, json
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__)); DATA = os.path.join(HERE, 'data')
DIP, STOP, ACT, TRAIL = 0.015, 0.10, 0.10, 0.02
PMIN, PMAX, LIQ = 3.0, 20.0, 200_000
EE, XE = 960, 990
def slip_of(p): return max(0.0015, 0.015 / p)

def entry_dip(mins, o, h, l, c, v, after):
    chg = np.divide(c - o, o, out=np.full_like(c, 1.0), where=o > 0)
    idx = np.where((mins > after) & (mins < EE) & (chg <= -DIP) &
                   (c >= PMIN) & (c <= PMAX) & (v * c >= LIQ))[0]
    if not len(idx):
        return None
    i = idx[0]; e = float(c[i]); sl = slip_of(e); ef = e*(1+sl)
    st, ac = e*(1-STOP), e*(1+ACT); activ=False; peak=e; ex=None
    for j in range(i+1, len(c)):
        if not (570 <= mins[j] < XE): continue
        if not activ:
            if l[j] <= st: ex=st; break
            peak=max(peak,h[j])
            if h[j] >= ac: activ=True
        else:
            ts=peak*(1-TRAIL)
            if l[j] <= ts: ex=ts; break
            peak=max(peak,h[j])
    if ex is None:
        w = c[(mins>=570)&(mins<XE)]; ex=float(w[-1]) if len(w) else e
    return (ex*(1-sl)-ef)/ef*100

df = pd.read_parquet(os.path.join(DATA, 'bars_1min.parquet'))
meta = json.load(open(os.path.join(DATA, 'meta.json')))

BUCKETS = [(570,575,'09:30-09:35'),(575,600,'09:35-10:00'),(600,630,'10:00-10:30'),
           (630,690,'10:30-11:30'),(690,720,'11:30-12:00')]
res = {b[2]: [] for b in BUCKETS}
n_noelig = 0
for (tk, date), g in df.groupby(['ticker','date'], sort=False):
    m = meta.get(f"{tk}|{date}")
    if not (m and m['post_open']):        # fresh movers seulement (pm_gap<10)
        continue
    pc = m['prev_close']
    if not pc or pc <= 0: continue
    g = g.sort_values('datetime')
    mins = (g['datetime'].str.slice(0,2).astype(int)*60 + g['datetime'].str.slice(3,5).astype(int)).values
    o,h,l,c,v = (g[k].values for k in ('o','h','l','c','v'))
    runmax = np.maximum.accumulate(h)
    gap = (runmax - pc)/pc*100
    # 1re minute POST-OPEN où gap entre dans 10-20
    elig = np.where((mins >= 570) & (gap >= 10) & (gap <= 20))[0]
    if not len(elig):
        n_noelig += 1; continue
    em = int(mins[elig[0]])
    lab = next((b[2] for b in BUCKETS if b[0] <= em < b[1]), None)
    if lab is None:
        continue
    pnl = entry_dip(mins, o, h, l, c, v, em)   # dip STRICTEMENT après l'éligibilité
    if pnl is not None:
        res[lab].append(pnl)

print(f"{'éligibilité (added)':<16} {'n':>4} {'exp%':>7} {'win%':>6} {'pf':>5} {'t':>6} {'total%':>8}")
for _,_,lab in BUCKETS:
    a = np.array(res[lab], float); n=len(a)
    if n==0:
        print(f"{lab:<16}  (0)"); continue
    exp=a.mean(); win=(a>0).mean()*100
    pf=a[a>0].sum()/(-a[a<0].sum() or 1e-9)
    t=exp/(a.std(ddof=1)/np.sqrt(n)) if n>1 and a.std(ddof=1)>0 else 0
    print(f"{lab:<16} {n:>4} {exp:>7.2f} {win:>6.1f} {pf:>5.2f} {t:>6.2f} {a.sum():>+8.0f}")
