#!/usr/bin/env python3
"""GRILLE COMPLÈTE : GAP x REPLI(entrée) x STOP x TP. Pour chaque bande de gap, trouve le
MEILLEUR combo (repli, stop, TP) en OOS. Métrique = R (exp%/stop%) car sizing = risque/trade
(la taille dépend du stop). TP='EOD' = pas de TP, on tient jusqu'à 15:55. Point-in-time.
Accumulation incrémentale (n, somme, somme²) -> faible mémoire.
"""
import os, glob, json, math
import numpy as np, pandas as pd

HERE=os.path.dirname(os.path.abspath(__file__)); DATA=os.path.join(HERE,'data'); BARS=os.path.join(DATA,'bars')
PMIN,PMAX,LIQ=3.0,20.0,200_000
OPEN,ENTEND,EXEND=571,955,960
SPLIT='2026-05-01'
RETRS=[5,8,10,12]
STOPS=[0.05,0.07,0.10,0.12,0.15]
TPS=[('+10',0.10),('+15',0.15),('+20',0.20),('+30',0.30),('EOD',9.99)]
GAPB=[(5,10),(10,15),(15,20),(20,30),(30,50),(50,100),(100,1e9)]
def slip(p): return max(0.0015,0.015/p)
def band(g):
    for lo,hi in GAPB:
        if lo<=g<hi: return f"{lo}-{hi if hi<1e9 else '+'}"
    return None

# acc[(band,retr,stop,tpname,split)] = [n, sum, sumsq]
acc={}
def add(key,x):
    a=acc.get(key)
    if a is None: acc[key]=[1,x,x*x]
    else: a[0]+=1; a[1]+=x; a[2]+=x*x

pc_map={f"{x['ticker']}|{x['date']}":x['prev_close'] for x in json.load(open(os.path.join(DATA,'candidates.json')))}
for path in sorted(glob.glob(os.path.join(BARS,'*.parquet'))):
    df=pd.read_parquet(path)
    for (tk,d),g in df.groupby(['ticker','date'],sort=False):
        pc=pc_map.get(f"{tk}|{d}")
        if not pc or pc<=0: continue
        split='TEST' if d>=SPLIT else 'TRAIN'
        g=g.sort_values('datetime')
        mins=(g['datetime'].str.slice(0,2).astype(int)*60+g['datetime'].str.slice(3,5).astype(int)).to_numpy()
        o,h,l,c,v=(g[k].to_numpy(float) for k in ('o','h','l','c','v'))
        hod=np.maximum.accumulate(h); gap=(hod-pc)/pc*100
        for retr in RETRS:
            i0=-1
            for i in range(len(c)):
                if mins[i]<OPEN or mins[i]>=ENTEND or hod[i]<=0: continue
                if (hod[i]-c[i])/hod[i]>=retr/100 and PMIN<=c[i]<=PMAX and v[i]*c[i]>=LIQ: i0=i; break
            if i0<0: continue
            bd=band(gap[i0])
            if bd is None: continue
            e=float(c[i0]); sl=slip(e); ef=e*(1+sl)
            lo=[]; hi=[]
            for j in range(i0+1,len(c)):
                if mins[j]<OPEN or mins[j]>=EXEND:
                    if mins[j]>=EXEND: break
                    continue
                lo.append(l[j]); hi.append(h[j])
            lo=np.array(lo); hi=np.array(hi)
            tail=[c[j] for j in range(i0+1,len(c)) if OPEN<=mins[j]<EXEND]
            eod=tail[-1] if tail else e
            for s in STOPS:
                sp=e*(1-s); ts=int(np.argmax(lo<=sp)) if len(lo) and (lo<=sp).any() else 10**9
                for tn,tp in TPS:
                    tgt=e*(1+tp); tt=int(np.argmax(hi>=tgt)) if len(hi) and (hi>=tgt).any() else 10**9
                    ex=tgt if tt<ts else (sp if ts<tt else eod)
                    add((bd,retr,s,tn,split),(ex*(1-sl)-ef)/ef*100)

def stats(key):
    a=acc.get(key)
    if not a or a[0]<20: return None
    n,sm,sq=a; e=sm/n; var=(sq-sm*sm/n)/(n-1) if n>1 else 0
    t=e/math.sqrt(var/n) if var>0 else 0
    return e,t,n

print("MEILLEUR combo (repli, stop, TP) par bande de gap — OOS TEST, classé par R = exp%/stop\n")
print(f"{'gap':<9}{'meilleur combo':<26}{'R':>7}{'exp%':>8}{'t':>7}{'n':>7}   {'edge ?'}")
for lo,hi in GAPB:
    bd=f"{lo}-{hi if hi<1e9 else '+'}"
    best=None
    for retr in RETRS:
        for s in STOPS:
            for tn,_ in TPS:
                r=stats((bd,retr,s,tn,'TEST'))
                if not r: continue
                R=r[0]/(s*100)
                if best is None or R>best[0]:
                    best=(R,r[0],r[1],r[2],retr,s,tn)
    if best is None:
        print(f"{bd:<9}(pas assez de trades)"); continue
    R,exp,t,n,retr,s,tn=best
    combo=f"repli{retr}% stop-{int(s*100)}% TP{tn}"
    verdict="✅ SIGNIF" if (t>=2 and R>0) else ("~ marginal" if R>0 else "❌ négatif")
    print(f"{bd:<9}{combo:<26}{R:>+6.2f}R{exp:>+7.2f}%{t:>+7.1f}{n:>7}   {verdict}")
