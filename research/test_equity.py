#!/usr/bin/env python3
"""Courbe de capital réaliste : gap 10-20%, dip -5%, stop -10%, act +5%, trail 2%.

Simulation chronologique avec :
  - plafond de N positions simultanées (on SAUTE les signaux au-delà)
  - taille = 20% du capital COURANT (composé)
  - commissions IBKR réelles
  - capital insuffisant => signal sauté"""
import os, json
import numpy as np, pandas as pd
import engine
R = os.path.dirname(__file__)

DIP, STOP, ACT, TRAIL = 0.05, 0.10, 0.05, 0.02
CAP0 = 5000.0
PCT = 0.20
MAXPOS = 4
def slip_of(p): return max(0.0015, 0.015 / p)
def commission(sh, px): return min(max(sh * 0.005, 1.00), 0.01 * sh * px)

df = engine.load_table(os.path.join(R, 'candles.parquet'))
gap = {(x['ticker'], x['date']): x['gap'] for x in json.load(open(os.path.join(R, 'gappers.json')))}

sig = []
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
    chg = np.divide(c - o, o, out=np.zeros_like(c), where=o > 0)
    idx = np.where((mins >= 570) & (mins < 960) & (chg <= -DIP) & (c >= 3))[0]
    if len(idx) == 0:
        continue
    i = idx[0]
    eraw = float(c[i]); sl = slip_of(eraw)
    st = eraw * (1 - STOP); ac = eraw * (1 + ACT)
    activ = False; peak = eraw; ex = None; t_out = int(mins[rth][-1])
    for j in range(i + 1, len(g)):
        if not rth[j]:
            continue
        if not activ:
            if l[j] <= st: ex = st; t_out = int(mins[j]); break
            peak = max(peak, h[j])
            if h[j] >= ac: activ = True
        else:
            ts = peak * (1 - TRAIL)
            if l[j] <= ts: ex = ts; t_out = int(mins[j]); break
            peak = max(peak, h[j])
    if ex is None:
        ex = float(c[rth][-1])
    sig.append((date, int(mins[i]), t_out, eraw, ex * (1 - sl)))

S = pd.DataFrame(sig, columns=['date', 't_in', 't_out', 'entry', 'exit_px']).sort_values(['date', 't_in'])
print(f"\n{len(S)} signaux sur {S.date.nunique()} jours\n")

def run(cap0, pct, maxpos):
    cap = cap0; open_pos = []; eq = []; pris = saute = 0
    for d, day in S.groupby('date', sort=True):
        for r in day.itertuples():
            open_pos = [p for p in open_pos if p[0] > r.t_in]        # libérer les sorties
            if len(open_pos) >= maxpos:
                saute += 1; continue
            size = cap * pct
            sh = int(size / r.entry)
            if sh < 1 or sh * r.entry > cap:
                saute += 1; continue
            pnl = sh * (r.exit_px - r.entry) - commission(sh, r.entry) - commission(sh, r.exit_px)
            open_pos.append((r.t_out, pnl))
            cap += pnl; pris += 1
        open_pos = []
        eq.append((d, cap))
    return cap, pris, saute, pd.DataFrame(eq, columns=['date', 'cap'])

print("=== COURBE DE CAPITAL (plafond 4 positions, 20% du capital, composé) ===")
for cap0 in [3387, 5000, 10000, 25000]:
    fin, pris, saute, eq = run(cap0, PCT, MAXPOS)
    eq['dd'] = eq.cap / eq.cap.cummax() - 1
    mult = fin / cap0
    print(f"  départ {cap0:>6}$ -> fin {fin:>10,.0f}$  (×{mult:>5.1f}, {100*(mult-1):>+8.0f}%)  "
          f"| trades pris {pris}/{len(S)} (sautés {saute}) | DD max {100*eq.dd.min():>+6.1f}%")

print("\n=== SENSIBILITÉ AU % PAR POSITION (départ 5000$, plafond 4) ===")
for pct in [0.05, 0.10, 0.15, 0.20, 0.25]:
    fin, pris, saute, eq = run(CAP0, pct, MAXPOS)
    eq['dd'] = eq.cap / eq.cap.cummax() - 1
    print(f"  {pct*100:>4.0f}% par position -> fin {fin:>10,.0f}$ ({100*(fin/CAP0-1):>+8.0f}%) "
          f"| DD max {100*eq.dd.min():>+6.1f}% | trades {pris}")

print("\n=== MOIS PAR MOIS (5000$, 20%, plafond 4) ===")
fin, pris, saute, eq = run(CAP0, PCT, MAXPOS)
eq['mois'] = pd.to_datetime(eq.date).dt.to_period('M')
m = eq.groupby('mois').cap.last()
prev = CAP0
for k, v in m.items():
    print(f"  {k}: {prev:>10,.0f}$ -> {v:>10,.0f}$   {100*(v/prev-1):>+7.1f}%")
    prev = v
eq['dd'] = eq.cap / eq.cap.cummax() - 1
print(f"\n  drawdown max sur la période : {100*eq.dd.min():+.1f}%")
