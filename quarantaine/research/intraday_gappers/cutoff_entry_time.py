#!/usr/bin/env python3
"""Retarder l'entrée après l'open réduit-il les GROS stops sans tuer l'edge ?
Population = runners POST-OPEN (meta.post_open) — ce que le bot trade. Config DÉPLOYÉE :
dip -1.5%, stop -10%, act +10%, trail 2%, prix 3-20, filtre liquidité bougie 200K$.
On balaie l'heure-plancher d'entrée. Slippage modélisé.
CAVEAT: in-sample, univers survivant = borne SUPÉRIEURE ; les radiés manquants sont
sans doute des blow-ups d'open -> les gros stops du matin sont SOUS-estimés ici."""
import os, json
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__)); DATA = os.path.join(HERE, 'data')
DIP, STOP, ACT, TRAIL = 0.015, 0.10, 0.10, 0.02
PMIN, PMAX, LIQ = 3.0, 20.0, 200_000
EE, XE = 960, 990
BIG_STOP = -8.0
def slip_of(p): return max(0.0015, 0.015 / p)

def trade(mins, o, h, l, c, v, floor):
    chg = np.divide(c - o, o, out=np.full_like(c, 1.0), where=o > 0)
    idx = np.where((mins >= floor) & (mins < EE) & (chg <= -DIP) &
                   (c >= PMIN) & (c <= PMAX) & (v * c >= LIQ))[0]
    if not len(idx):
        return None
    i = idx[0]; e = float(c[i]); sl = slip_of(e); ef = e * (1 + sl)
    st, ac = e * (1 - STOP), e * (1 + ACT); activ = False; peak = e; ex = None
    for j in range(i + 1, len(c)):
        if not (570 <= mins[j] < XE):
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
        win = c[(mins >= 570) & (mins < XE)]
        ex = float(win[-1]) if len(win) else e
    return (ex * (1 - sl) - ef) / ef * 100

df = pd.read_parquet(os.path.join(DATA, 'bars_1min.parquet'))
meta = json.load(open(os.path.join(DATA, 'meta.json')))
# ne garder que les ticker-jours post-open
groups = []
dates = set()
for (tk, date), g in df.groupby(['ticker', 'date'], sort=False):
    m = meta.get(f"{tk}|{date}")
    if not (m and m['post_open']):
        continue
    mins = (g['datetime'].str.slice(0,2).astype(int)*60 + g['datetime'].str.slice(3,5).astype(int)).values
    groups.append((mins, g['o'].values, g['h'].values, g['l'].values, g['c'].values, g['v'].values))
    dates.add(date)
ndays = len(dates)
print(f"runners post-open = {len(groups)} ticker-jours sur {ndays} jours "
      f"({df['date'].min()} -> {df['date'].max()})\n")

CUTOFFS = [(570,'aucun (>=09:30)'), (575,'>=09:35'), (585,'>=09:45'),
           (600,'>=10:00'), (630,'>=10:30'), (690,'>=11:30')]
print(f"{'plancher entrée':<18} {'n':>4} {'exp%':>7} {'win%':>6} {'pf':>5} {'t':>6} "
      f"{'tr/j':>5} {'gStop':>6} {'%gS':>5} {'total%':>8}")
for floor, lab in CUTOFFS:
    pnls = [p for grp in groups if (p := trade(*grp, floor)) is not None]
    a = np.array(pnls, float); n = len(a)
    if n == 0:
        print(f"{lab:<18}  (0)"); continue
    exp = a.mean(); win = (a>0).mean()*100
    pf = a[a>0].sum() / (-a[a<0].sum() or 1e-9)
    t = exp/(a.std(ddof=1)/np.sqrt(n)) if n>1 and a.std(ddof=1)>0 else 0
    big = int((a <= BIG_STOP).sum())
    print(f"{lab:<18} {n:>4} {exp:>7.2f} {win:>6.1f} {pf:>5.2f} {t:>6.2f} "
          f"{n/ndays:>5.2f} {big:>6} {big/n*100:>5.1f} {a.sum():>+8.0f}")
