#!/usr/bin/env python3
"""ÉTUDE (obs Martin 23/09) : entrer sur un REPLI de X% depuis le PLUS-HAUT DU JOUR (HOD),
au lieu du mini-dip -1,5% d'une bougie. Idée : le titre gappe, fait un sommet, recule ~8%,
PUIS rebondit -> on achète ce repli profond.

Entrée = 1re minute (post-open) où le prix courant <= HOD_courant * (1 - X%), avec gap encore
dans 5-10% (recheck), prix 3-20, liquidité bougie >= 200K$. 1/jour. Sortie = pile déployée
(stop -10%, activation +10%, trail 2%, EOD). Point-in-time (HOD = plus-haut courant, causal). OOS.
"""
import os, glob, json
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__)); DATA = os.path.join(HERE, 'data')
BARS_DIR = os.path.join(DATA, 'bars')
GMIN, GMAX = 5.0, 10.0
PMIN, PMAX, LIQ = 3.0, 20.0, 200_000
STOP, ACT, TRAIL = 0.10, 0.10, 0.02
OPEN_NEXT, ENTRY_END, EXIT_END = 571, 955, 960
SPLIT = '2026-05-01'
def slip_of(p): return max(0.0015, 0.015/p)


def exit_trail(mins, h, l, c, i):
    e=float(c[i]); sl=slip_of(e); ef=e*(1+sl); st,ac=e*(1-STOP),e*(1+ACT)
    activ=False; peak=e; ex=None; last=e
    for j in range(i+1,len(c)):
        if mins[j]>=EXIT_END: break
        if not activ:
            if l[j]<=st: ex=st; break
            if h[j]>peak: peak=h[j]
            if h[j]>=ac: activ=True
        else:
            ts=peak*(1-TRAIL)
            if l[j]<=ts: ex=ts; break
            if h[j]>peak: peak=h[j]
        last=c[j]
    if ex is None: ex=last
    return (ex*(1-sl)-ef)/ef*100


def trade_day(mins,o,h,l,c,v,pc,retr):
    hod=np.maximum.accumulate(h)                       # plus-haut courant (causal)
    run_gap=(hod-pc)/pc*100
    for i in range(len(c)):
        if mins[i]<OPEN_NEXT or mins[i]>=ENTRY_END: continue
        if not (GMIN<=run_gap[i]<=GMAX): continue      # recheck gap
        if hod[i]<=0: continue
        drop=(hod[i]-c[i])/hod[i]                       # repli depuis le HOD
        if drop>=retr and PMIN<=c[i]<=PMAX and v[i]*c[i]>=LIQ:
            return exit_trail(mins,h,l,c,i)
    return None


def run(retr):
    pc_map={f"{x['ticker']}|{x['date']}":x['prev_close'] for x in json.load(open(os.path.join(DATA,'candidates.json')))}
    rows=[]
    for path in sorted(glob.glob(os.path.join(BARS_DIR,'*.parquet'))):
        df=pd.read_parquet(path)
        for (tk,date),g in df.groupby(['ticker','date'],sort=False):
            pc=pc_map.get(f"{tk}|{date}")
            if not pc or pc<=0: continue
            g=g.sort_values('datetime')
            mins=(g['datetime'].str.slice(0,2).astype(int)*60+g['datetime'].str.slice(3,5).astype(int)).to_numpy()
            o,h,l,c,v=(g[k].to_numpy(float) for k in ('o','h','l','c','v'))
            r=trade_day(mins,o,h,l,c,v,pc,retr)
            if r is not None: rows.append({'date':date,'pnl':r})
    return pd.DataFrame(rows)


def st(a):
    a=np.asarray(a,float);n=len(a)
    if n==0: return "n=0"
    e=a.mean();tt=e/(a.std(ddof=1)/np.sqrt(n)) if n>1 and a.std(ddof=1)>0 else 0
    pf=a[a>0].sum()/(-a[a<0].sum() or 1e-9)
    return f"n={n:>4} exp={e:>+6.2f}% win={(a>0).mean()*100:>3.0f}% pf={pf:>4.2f} t={tt:>+5.2f}"

print("ENTRÉE = repli de X% depuis le HOD (gap 5-10 recheck, post-open, sortie déployée)\n")
print(f"{'repli/HOD':>10}  {'ALL':<46} {'TEST (mai-août)'}")
for retr in (0.03,0.04,0.05,0.06,0.08,0.10,0.12):
    d=run(retr)
    all_s=st(d['pnl']); te=st(d[d.date>=SPLIT]['pnl'])
    print(f"{retr*100:>8.0f}%  {all_s:<46} {te}")
print("\n(rappel : dip -1.5% classique = +0,46%/t3,5 ALL, +0,61%/t3,2 TEST)")
