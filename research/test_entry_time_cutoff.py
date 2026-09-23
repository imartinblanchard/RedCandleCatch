#!/usr/bin/env python3
"""HYPOTHÈSE MARTIN (22/09) : retarder l'entrée après l'ouverture réduit-il les GROS
stops sans tuer l'edge ? Observé en live : les stops secs (-9 à -11%) se concentrent
à 09:33-09:52.

Population = RUNNERS POST-OUVERTURE (ce que le bot trade réellement) :
  - le gap (plus-haut courant vs clôture veille) N'atteint PAS 10% avant l'ouverture
    (sinon = gapper pré-marché, non tradé), ET
  - entre dans la bande 10-20% APRÈS 09:30.
Entrée = 1re bougie de dip -1.5% (DIP_LIQUID) au-delà du cutoff, prix>=3, bougie>=200K$.
Sortie = STOP -10% -> activation +10% -> TRAIL 2% (config déployée). Slippage modélisé.

On balaie plusieurs heures-plancher d'entrée et on mesure edge + fréquence des gros stops.
CAVEAT: in-sample, univers survivant (borne SUPÉRIEURE ; les radiés manquants sont
probablement des blow-ups d'open -> les gros stops du matin sont SOUS-estimés ici)."""
import os
import numpy as np, pandas as pd

R = os.path.dirname(__file__)
PMIN, LIQ = 3.0, 200_000
DIP, STOP, ACT, TRAIL = 0.015, 0.10, 0.10, 0.02
BIG_STOP = -8.0          # seuil "gros stop" (le -10% brut après slippage)

def slip_of(p): return max(0.0015, 0.015 / p)

df = pd.read_parquet(os.path.join(R, 'candles.parquet'),
                     columns=['ticker','date','o','h','l','c','v','datetime','prev_close'])
df['min'] = df['datetime'].str.slice(0,2).astype(int)*60 + df['datetime'].str.slice(3,5).astype(int)

def simulate(g, mins, i0, N):
    for i in range(i0, N):
        if mins[i] < 570 or mins[i] >= 955:
            continue
        o, c = g['o'][i], g['c'][i]
        if o > 0 and (c-o)/o <= -DIP and c >= PMIN and g['v'][i]*c >= LIQ:
            eraw = float(c); sl = slip_of(eraw)
            st = eraw*(1-STOP); ac = eraw*(1+ACT); activ=False; peak=eraw; ex=None
            for j in range(i+1, N):
                if mins[j] < 570 or mins[j] >= 985:
                    continue
                lo, hi = g['l'][j], g['h'][j]
                if not activ:
                    if lo <= st: ex = st; break
                    peak = max(peak, hi)
                    if hi >= ac: activ = True
                else:
                    ts = peak*(1-TRAIL)
                    if lo <= ts: ex = ts; break
                    peak = max(peak, hi)
            if ex is None:
                tail = [g['c'][k] for k in range(i+1, N) if 570 <= mins[k] < 985]
                ex = float(tail[-1]) if tail else eraw
            return (ex*(1-sl) - eraw)/eraw*100, mins[i]
    return None

# pré-calcule la population post-open + added_min une seule fois
POP = []   # (g-dict, mins, N, added_min)
for (tk, date), grp in df.groupby(['ticker','date'], sort=False):
    grp = grp.sort_values('min')
    mins = grp['min'].to_numpy()
    pc = float(grp['prev_close'].iloc[0])
    if not pc or pc <= 0:
        continue
    h = grp['h'].to_numpy()
    runmax = np.maximum.accumulate(h)
    gap = (runmax - pc)/pc*100
    pre = mins < 570
    if pre.any() and gap[pre].max() >= 10:      # déjà 10%+ avant l'open -> gapper PM, exclu
        continue
    inband = (mins >= 570) & (gap >= 10) & (gap <= 20)
    if not inband.any():                         # n'entre jamais dans la bande post-open
        continue
    added_min = int(mins[np.argmax(inband)])     # 1re minute post-open dans la bande
    g = {k: grp[k].to_numpy() for k in ('o','h','l','c','v')}
    POP.append((g, mins, len(mins), added_min))

print(f"candles.parquet: {df['date'].min()} -> {df['date'].max()}")
print(f"population runners post-open = {len(POP)} ticker-jours\n")

CUTOFFS = [(570,'aucun (>=09:30)'), (575,'>=09:35'), (585,'>=09:45'),
           (600,'>=10:00'), (630,'>=10:30')]
ndays = df['date'].nunique()
print(f"{'plancher entrée':<18} {'n':>4} {'exp%':>7} {'win%':>6} {'pf':>5} {'t':>6} "
      f"{'tr/j':>5} {'gStop':>6} {'%gS':>5}")
for cut, lab in CUTOFFS:
    pnls = []
    for g, mins, N, added_min in POP:
        start = max(added_min, cut)
        i0 = int(np.searchsorted(mins, start))
        r = simulate(g, mins, i0, N)
        if r is not None:
            pnls.append(r[0])
    a = np.array(pnls, float); n = len(a)
    if n == 0:
        print(f"{lab:<18}  (0 trades)"); continue
    exp = a.mean(); win = (a>0).mean()*100
    pos, neg = a[a>0].sum(), -a[a<0].sum()
    pf = pos/neg if neg else float('inf')
    t = exp/(a.std(ddof=1)/np.sqrt(n)) if n>1 and a.std(ddof=1)>0 else 0
    big = int((a <= BIG_STOP).sum())
    print(f"{lab:<18} {n:>4} {exp:>7.2f} {win:>6.1f} {pf:>5.2f} {t:>6.2f} "
          f"{n/ndays:>5.2f} {big:>6} {big/n*100:>5.1f}")
