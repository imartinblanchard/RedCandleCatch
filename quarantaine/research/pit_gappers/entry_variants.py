#!/usr/bin/env python3
"""PIT rebuild — le DIP sert-il à quelque chose ? Entrée IMMÉDIATE (à l'éligibilité, sans
attendre le dip) vs entrée sur DIP −1,5%. Sorties : trailing (actuel) vs stop + take-profit
FIXE (le « seuil de profit »). Poche validée : post-open, gap 5-10%, prix 3-20$. OOS.

Point-in-time : entrée immédiate = close de la 1re minute où le plus-haut courant entre dans
la bande (causal, pas de look-ahead). Liquidité 200K$ exigée sur la bougie d'entrée.
"""
import os, glob, json
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__)); DATA = os.path.join(HERE, 'data')
BARS_DIR = os.path.join(DATA, 'bars')
BAND = (0.05, 0.10)                 # poche gap 5-10%
PMIN_A, PMAX_A, LIQ = 3.0, 20.0, 200_000
OPEN_MIN, ENTRY_END, EXIT_END = 570, 955, 960
SPLIT = '2026-05-01'
def slip_of(p): return max(0.0015, 0.015 / p)


def exit_trail(mins, h, l, c, i, stop=0.10, act=0.10, trail=0.02):
    e = float(c[i]); sl = slip_of(e); ef = e*(1+sl); st, ac = e*(1-stop), e*(1+act)
    activ = False; peak = e; ex = None; last = e
    for j in range(i+1, len(c)):
        if mins[j] >= EXIT_END: break
        if not activ:
            if l[j] <= st: ex = st; break
            if h[j] > peak: peak = h[j]
            if h[j] >= ac: activ = True
        else:
            ts = peak*(1-trail)
            if l[j] <= ts: ex = ts; break
            if h[j] > peak: peak = h[j]
        last = c[j]
    if ex is None: ex = last
    return (ex*(1-sl)-ef)/ef*100


def exit_bracket(mins, h, l, c, i, stop, tp):
    """Stop -stop OU take-profit +tp, le 1er touché ; sinon close EOD. (stop prioritaire si même bougie.)"""
    e = float(c[i]); sl = slip_of(e); ef = e*(1+sl); st, tgt = e*(1-stop), e*(1+tp)
    ex = None; last = e
    for j in range(i+1, len(c)):
        if mins[j] >= EXIT_END: break
        if l[j] <= st: ex = st; break
        if h[j] >= tgt: ex = tgt; break
        last = c[j]
    if ex is None: ex = last
    return (ex*(1-sl)-ef)/ef*100


POLICIES = [
    ('trail s10/a10/t2', lambda m,h,l,c,i: exit_trail(m,h,l,c,i,0.10,0.10,0.02)),
    ('bracket s10/tp3',  lambda m,h,l,c,i: exit_bracket(m,h,l,c,i,0.10,0.03)),
    ('bracket s10/tp5',  lambda m,h,l,c,i: exit_bracket(m,h,l,c,i,0.10,0.05)),
    ('bracket s10/tp10', lambda m,h,l,c,i: exit_bracket(m,h,l,c,i,0.10,0.10)),
    ('bracket s5/tp5',   lambda m,h,l,c,i: exit_bracket(m,h,l,c,i,0.05,0.05)),
    ('bracket s7/tp7',   lambda m,h,l,c,i: exit_bracket(m,h,l,c,i,0.07,0.07)),
    ('EOD stop10 only',  lambda m,h,l,c,i: exit_bracket(m,h,l,c,i,0.10,9.99)),  # tp inatteignable = hold/stop
]

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
        run_gap = (np.maximum.accumulate(h) - pc) / pc
        el = np.where((run_gap >= BAND[0]) & (run_gap <= BAND[1]))[0]
        if len(el) == 0: continue
        i0 = int(el[0])
        if mins[i0] < OPEN_MIN: continue                      # post-open seulement
        # ENTRÉE IMMÉDIATE (éligibilité)
        for entry, idx in (('IMMEDIATE', i0), ('DIP-1.5%', None)):
            if entry == 'DIP-1.5%':
                # dip AVEC run_gap encore dans la bande 5-10% (même population que l'immédiat)
                cand = [k for k in range(i0, len(c)) if mins[k] < ENTRY_END and o[k] > 0
                        and (c[k]-o[k])/o[k] <= -0.015
                        and BAND[0] <= run_gap[k] <= BAND[1]]
                idx = cand[0] if cand else None
            if idx is None or mins[idx] >= ENTRY_END: continue
            if not (PMIN_A <= c[idx] <= PMAX_A) or v[idx]*c[idx] < LIQ: continue
            rec = {'ticker': tk, 'date': date, 'entry': entry}
            for name, fn in POLICIES:
                rec[name] = round(fn(mins, h, l, c, idx), 3)
            rows.append(rec)

d = pd.DataFrame(rows)
def st(a):
    a = np.asarray(a, float); n = len(a)
    if n == 0: return None
    exp = a.mean(); tt = exp/(a.std(ddof=1)/np.sqrt(n)) if n > 1 and a.std(ddof=1) > 0 else 0
    return dict(n=n, exp=exp, t=tt, win=(a > 0).mean()*100)

print(f"poche post-open gap 5-10%, prix 3-20$ | {len(d)} entrées (1/jour par méthode)\n")
for entry in ('IMMEDIATE', 'DIP-1.5%'):
    sub = d[d['entry'] == entry]
    print(f"===== ENTRÉE {entry} (n={len(sub)}) =====")
    print(f"  {'sortie':<20} {'exp%':>7} {'win%':>5} {'t':>6} | {'TEST exp/t/n':>18}")
    for name, _ in POLICIES:
        s = st(sub[name]); te = st(sub[sub.date >= SPLIT][name])
        if s: print(f"  {name:<20} {s['exp']:>+7.2f} {s['win']:>5.0f} {s['t']:>+6.2f} | "
                    f"{te['exp']:>+6.2f}/{te['t']:>+4.1f}/{te['n']:>4}")
    print()
