#!/usr/bin/env python3
"""Le +2% post-open est-il un artefact de LOOK-AHEAD ?
Méthode A (backtest 'validé') : dip dès 09:30, SANS attendre l'éligibilité.
Méthode B (réaliste, = live)   : dip seulement APRÈS que le titre entre dans 10-20.
Sur les mêmes ticker-jours post_open. On mesure aussi, en A, la part de trades dont
l'ENTRÉE précède l'éligibilité (= pur look-ahead) et leur contribution."""
import os, json
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__)); DATA = os.path.join(HERE, 'data')
DIP, STOP, ACT, TRAIL = 0.015, 0.10, 0.10, 0.02
PMIN, PMAX, LIQ = 3.0, 20.0, 200_000
EE, XE = 960, 990
def slip_of(p): return max(0.0015, 0.015/p)

def run(mins,o,h,l,c,v,after):
    """1er dip après 'after' (minute exclue). Renvoie (pnl, entry_min) ou None."""
    chg = np.divide(c-o,o,out=np.full_like(c,1.0),where=o>0)
    idx = np.where((mins>after)&(mins<EE)&(chg<=-DIP)&(c>=PMIN)&(c<=PMAX)&(v*c>=LIQ))[0]
    if not len(idx): return None
    i=idx[0]; e=float(c[i]); sl=slip_of(e); ef=e*(1+sl)
    st,ac=e*(1-STOP),e*(1+ACT); activ=False; peak=e; ex=None
    for j in range(i+1,len(c)):
        if not (570<=mins[j]<XE): continue
        if not activ:
            if l[j]<=st: ex=st; break
            peak=max(peak,h[j])
            if h[j]>=ac: activ=True
        else:
            ts=peak*(1-TRAIL)
            if l[j]<=ts: ex=ts; break
            peak=max(peak,h[j])
    if ex is None:
        w=c[(mins>=570)&(mins<XE)]; ex=float(w[-1]) if len(w) else e
    return (ex*(1-sl)-ef)/ef*100, int(mins[i])

df=pd.read_parquet(os.path.join(DATA,'bars_1min.parquet'))
meta=json.load(open(os.path.join(DATA,'meta.json')))
A=[]; B=[]; look=[]; nonlook=[]
for (tk,date),g in df.groupby(['ticker','date'],sort=False):
    m=meta.get(f"{tk}|{date}")
    if not (m and m['post_open']): continue
    pc=m['prev_close']
    if not pc or pc<=0: continue
    g=g.sort_values('datetime')
    mins=(g['datetime'].str.slice(0,2).astype(int)*60+g['datetime'].str.slice(3,5).astype(int)).values
    o,h,l,c,v=(g[k].values for k in ('o','h','l','c','v'))
    gap=(np.maximum.accumulate(h)-pc)/pc*100
    elig=np.where((mins>=570)&(gap>=10)&(gap<=20))[0]
    if not len(elig): continue
    em=int(mins[elig[0]])
    ra=run(mins,o,h,l,c,v,569)     # A : dès 09:30
    rb=run(mins,o,h,l,c,v,em)      # B : après éligibilité
    if ra is not None:
        A.append(ra[0])
        (look if ra[1]<em else nonlook).append(ra[0])
    if rb is not None:
        B.append(rb[0])

def show(lab,a):
    a=np.array(a,float); n=len(a)
    if n==0: print(f"{lab:<34} (0)"); return
    exp=a.mean(); win=(a>0).mean()*100
    pf=a[a>0].sum()/(-a[a<0].sum() or 1e-9)
    t=exp/(a.std(ddof=1)/np.sqrt(n)) if n>1 and a.std(ddof=1)>0 else 0
    print(f"{lab:<34} n={n:>4} exp={exp:>+6.2f}% win={win:>4.0f}% pf={pf:>4.2f} t={t:>6.2f} total={a.sum():>+7.0f}%")

print("=== Même population post_open, dip -1.5% / act +10% / trail 2% ===")
show("A: dip dès 09:30 (backtest validé)", A)
show("B: dip APRÈS éligibilité (=live)", B)
print("\n--- Décomposition de A ---")
show("  A1: entrée AVANT éligibilité (look-ahead)", look)
show("  A2: entrée APRÈS éligibilité (légitime)", nonlook)
print(f"\npart look-ahead dans A : {len(look)}/{len(look)+len(nonlook)} "
      f"= {100*len(look)/max(len(look)+len(nonlook),1):.0f}% des trades")
