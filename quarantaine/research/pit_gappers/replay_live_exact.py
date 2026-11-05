#!/usr/bin/env python3
"""RÉPLIQUE EXACTE de la règle du bot live (redcandlecatch_terminator) -> chiffre FIABLE.

Règle live fidèlement reproduite :
  - Éligibilité ('added') = 1re minute (<= midi) où le plus-haut courant 04:00->now (capé midi)
    entre dans [GAP_MIN, GAP_MAX]. STICKY. Prix à cette minute dans [3,20]. (= evaluate du scan)
  - PM DÉSACTIVÉ : si added < 09:31 -> premarket -> SKIP (on ne trade que added >= 09:31).
  - Entrée = 1re bougie clôturée APRÈS 'added' avec (c-o)/o <= -DIP_LIQUID (1,5%), c >= 3,
    et dollar-vol de la bougie >= 200K$. PAS de re-check du gap à l'entrée (comme le bot).
  - 1 entrée/ticker/jour. Sortie : STOP -10%, activation +10%, trail 2%, EOD.
On lance pour la NOUVELLE bande (5-10) et l'ANCIENNE (10-20), OOS train/test.
"""
import os, glob, json
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__)); DATA = os.path.join(HERE, 'data')
BARS_DIR = os.path.join(DATA, 'bars')
DIP, STOP, ACT, TRAIL = 0.015, 0.10, 0.10, 0.02
PMIN, PMAX, LIQ = 3.0, 20.0, 200_000
OPEN_NEXT, NOON, ENTRY_END, EXIT_END = 571, 720, 955, 960   # 09:31, 12:00, 15:55, 16:00
SPLIT = '2026-05-01'
def slip_of(p): return max(0.0015, 0.015 / p)


def exit_trail(mins, h, l, c, i):
    e = float(c[i]); sl = slip_of(e); ef = e*(1+sl); st, ac = e*(1-STOP), e*(1+ACT)
    activ = False; peak = e; ex = None; last = e
    for j in range(i+1, len(c)):
        if mins[j] >= EXIT_END: break
        if not activ:
            if l[j] <= st: ex = st; break
            if h[j] > peak: peak = h[j]
            if h[j] >= ac: activ = True
        else:
            ts = peak*(1-TRAIL)
            if l[j] <= ts: ex = ts; break
            if h[j] > peak: peak = h[j]
        last = c[j]
    if ex is None: ex = last
    return (ex*(1-sl)-ef)/ef*100


def trade_day(mins, o, h, l, c, v, pc, gmin, gmax, added_postopen=True, recheck=False):
    run_gap = (np.maximum.accumulate(h) - pc) / pc * 100
    cand = np.where((mins <= NOON) & (run_gap >= gmin) & (run_gap <= gmax) &
                    (c >= PMIN) & (c <= PMAX))[0]
    if len(cand) == 0:
        return None
    added_i = int(cand[0]); added_min = int(mins[added_i])
    if added_postopen and added_min < OPEN_NEXT:   # PM désactivé (règle live)
        return None
    for i in range(added_i + 1, len(c)):
        if mins[i] >= ENTRY_END:
            break
        if not added_postopen and mins[i] < OPEN_NEXT:      # variante : dip post-open exigé
            continue
        if recheck and not (gmin <= run_gap[i] <= gmax):    # variante : gap encore dans la bande
            continue
        if o[i] > 0 and (c[i]-o[i])/o[i] <= -DIP and c[i] >= PMIN and v[i]*c[i] >= LIQ:
            return (exit_trail(mins, h, l, c, i), added_min, float(c[i]))
    return None


def run(gmin, gmax, added_postopen=True, recheck=False):
    pc_map = {f"{x['ticker']}|{x['date']}": x['prev_close']
              for x in json.load(open(os.path.join(DATA, 'candidates.json')))}
    rows = []
    for path in sorted(glob.glob(os.path.join(BARS_DIR, '*.parquet'))):
        df = pd.read_parquet(path)
        for (tk, date), g in df.groupby(['ticker', 'date'], sort=False):
            pc = pc_map.get(f"{tk}|{date}")
            if not pc or pc <= 0: continue
            g = g.sort_values('datetime')
            mins = (g['datetime'].str.slice(0,2).astype(int)*60 + g['datetime'].str.slice(3,5).astype(int)).to_numpy()
            o, h, l, c, v = (g[k].to_numpy(float) for k in ('o','h','l','c','v'))
            r = trade_day(mins, o, h, l, c, v, pc, gmin, gmax, added_postopen, recheck)
            if r is not None:
                rows.append({'ticker': tk, 'date': date, 'pnl': r[0], 'added': r[1], 'entry': r[2]})
    return pd.DataFrame(rows)


def stat(a):
    a = np.asarray(a, float); n = len(a)
    if n == 0: return "n=0"
    exp = a.mean(); tt = exp/(a.std(ddof=1)/np.sqrt(n)) if n > 1 and a.std(ddof=1) > 0 else 0
    pf = a[a > 0].sum()/(-a[a < 0].sum() or 1e-9)
    return f"n={n:>4} exp={exp:>+6.2f}% win={(a>0).mean()*100:>3.0f}% pf={pf:>4.2f} t={tt:>+5.2f}"


def report(lab, d):
    print(f"===== {lab} =====")
    print(f"  ALL   {stat(d['pnl'])}")
    print(f"  TRAIN {stat(d[d.date <  SPLIT]['pnl'])}")
    print(f"  TEST  {stat(d[d.date >= SPLIT]['pnl'])}")
    if len(d): print(f"  (trades/jour: {len(d)/d['date'].nunique():.2f})")
    print()

print("dip 1.5% act 10% trail 2%. 'recheck' = gap ENCORE dans la bande au moment du dip.\n")
print("###### RÈGLE LIVE ACTUELLE (added>=09:31, PAS de recheck) ######")
report('LIVE 5-10%', run(5, 10))
report('LIVE 10-20%', run(10, 20))
print("###### VARIANTE : + recheck gap à l'entrée (modif candidate du bot) ######")
report('5-10% + recheck (added>=09:31)', run(5, 10, added_postopen=True, recheck=True))
report('5-10% + recheck (dip post-open, added libre)', run(5, 10, added_postopen=False, recheck=True))
report('10-20% + recheck (added>=09:31)', run(10, 20, added_postopen=True, recheck=True))
