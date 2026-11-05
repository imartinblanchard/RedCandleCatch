#!/usr/bin/env python3
"""Quel capital faut-il pour jouer la config candidate en prenant TOUS les signaux ?

Config : gap 10-20%, dip -5%, stop -10%, activation +5%, trail 2%.
On mesure : positions SIMULTANÉES réelles (chevauchement entrée->sortie),
commissions IBKR réelles, expectancy NETTE selon la taille, et le drawdown."""
import os, json
import numpy as np, pandas as pd
import engine
R = os.path.dirname(__file__)

DIP, STOP, ACT, TRAIL = 0.05, 0.10, 0.05, 0.02
def slip_of(p): return max(0.0015, 0.015 / p)
def commission(shares, price):
    """IBKR fixed : max(0,005$/action ; 1,00$) plafonné à 1 % de la valeur."""
    val = shares * price
    return min(max(shares * 0.005, 1.00), 0.01 * val)

df = engine.load_table(os.path.join(R, 'candles.parquet'))
gap = {(x['ticker'], x['date']): x['gap'] for x in json.load(open(os.path.join(R, 'gappers.json')))}

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
    chg = np.divide(c - o, o, out=np.zeros_like(c), where=o > 0)
    idx = np.where((mins >= 570) & (mins < 960) & (chg <= -DIP) & (c >= 3))[0]
    if len(idx) == 0:
        continue
    i = idx[0]
    eraw = float(c[i]); sl = slip_of(eraw)
    st = eraw * (1 - STOP); ac = eraw * (1 + ACT)
    activ = False; peak = eraw; ex = None; t_out = mins[rth][-1]
    for j in range(i + 1, len(g)):
        if not rth[j]:
            continue
        if not activ:
            if l[j] <= st: ex = st; t_out = mins[j]; break
            peak = max(peak, h[j])
            if h[j] >= ac: activ = True
        else:
            ts = peak * (1 - TRAIL)
            if l[j] <= ts: ex = ts; t_out = mins[j]; break
            peak = max(peak, h[j])
    if ex is None:
        ex = float(c[rth][-1])
    rows.append(dict(date=date, t_in=mins[i], t_out=t_out, entry=eraw,
                     exit_px=ex * (1 - sl), pnl_pct=(ex * (1 - sl) - eraw) / eraw * 100))

L = pd.DataFrame(rows)
print(f"\n{len(L)} trades | {L.date.nunique()} jours actifs\n")

# ---------- 1. positions SIMULTANÉES (chevauchement réel) ----------
print("=== 1. POSITIONS SIMULTANÉES (chevauchement entrée->sortie) ===")
maxc = []
for d, s in L.groupby('date'):
    ev = sorted([(r.t_in, 1) for r in s.itertuples()] + [(r.t_out, -1) for r in s.itertuples()])
    cur = mx = 0
    for _, v in ev:
        cur += v; mx = max(mx, cur)
    maxc.append(mx)
maxc = np.array(maxc)
print(f"  simultanées/jour : moyenne={maxc.mean():.1f}  médiane={np.median(maxc):.0f}  "
      f"p90={np.percentile(maxc,90):.0f}  p99={np.percentile(maxc,99):.0f}  max={maxc.max()}")
for k in [1, 2, 3, 4, 5, 6, 8, 10]:
    print(f"    plafond {k:>2} positions -> couvre {100*(maxc<=k).mean():>5.1f}% des jours")

# ---------- 2. commissions selon la taille ----------
print("\n=== 2. EXPECTANCY NETTE selon la taille de position ===")
print(f"{'position':>10}{'comm A/R':>11}{'brut':>9}{'NET':>9}{'verdict':>12}")
for size in [10, 50, 100, 200, 500, 1000, 2000, 5000]:
    nets = []
    for r in L.itertuples():
        sh = max(1, int(size / r.entry))
        cin = commission(sh, r.entry); cout = commission(sh, r.exit_px)
        val = sh * r.entry
        nets.append((sh * (r.exit_px - r.entry) - cin - cout) / val * 100)
    nets = np.array(nets)
    cpct = L.pnl_pct.mean() - nets.mean()
    verdict = "❌ perdant" if nets.mean() <= 0 else ("⚠️ limite" if nets.mean() < 1 else "✅ viable")
    print(f"{size:>9}${cpct:>10.2f}%{L.pnl_pct.mean():>+9.2f}{nets.mean():>+9.2f}{verdict:>12}")

# ---------- 3. risque & capital ----------
print("\n=== 3. CAPITAL REQUIS (prendre TOUS les signaux) ===")
print("   règle : risque/trade = 2% du capital, stop -10% -> position = 20% du capital")
for cap in [3387, 5000, 10000, 25000, 50000]:
    pos = cap * 0.20
    besoin_p90 = int(np.percentile(maxc, 90)) * pos
    sh_ex = max(1, int(pos / L.entry.mean()))
    c_ar = (commission(sh_ex, L.entry.mean()) + commission(sh_ex, L.entry.mean())) / pos * 100
    net = L.pnl_pct.mean() - c_ar
    print(f"  capital {cap:>6}$ -> position {pos:>7.0f}$ | comm A/R {c_ar:>5.2f}% | "
          f"net {net:>+5.2f}%/tr | besoin p90 ({int(np.percentile(maxc,90))} pos) = {besoin_p90:>8.0f}$ "
          + ("✅" if besoin_p90 <= cap else "⚠️ dépasse le capital"))

# ---------- 4. drawdown ----------
print("\n=== 4. RISQUE (en % du capital, position = 20% du capital) ===")
L2 = L.sort_values(['date', 't_in'])
eq = (L2.pnl_pct * 0.20).cumsum()          # chaque trade pèse 20% du capital
dd = (eq - eq.cummax())
print(f"  pire trade   : {L.pnl_pct.min():>+7.2f}% du prix -> {L.pnl_pct.min()*0.20:>+6.2f}% du capital")
print(f"  pire journée : {(L.groupby('date').pnl_pct.sum()*0.20).min():>+6.2f}% du capital")
print(f"  drawdown max : {dd.min():>+6.2f}% du capital")
print(f"  gain cumulé  : {eq.iloc[-1]:>+6.1f}% du capital sur {L.date.nunique()} jours (hors commissions)")
