#!/usr/bin/env python3
"""Quel FILTRE améliore l'edge/trade ? Base = entrée repli 8% / stop -10% / hold-EOD, gap 5-10.
Par trade on enregistre : pnl, float, inst%, $vol de la MONTÉE au sommet (cumul v*c jusqu'au HOD),
$vol de la bougie de repli. Puis on bucket chaque filtre et on lit l'edge/tr OOS (test mai-août).
Base OOS ~ +0,91%/tr : les buckets qui font MIEUX concentrent l'edge."""
import os, glob, json
import numpy as np, pandas as pd

HERE=os.path.dirname(os.path.abspath(__file__)); DATA=os.path.join(HERE,'data'); BARS=os.path.join(DATA,'bars')
GMIN,GMAX,PMIN,PMAX,LIQ=5,10,3,20,200_000; OPEN,ENTEND,EXEND=571,955,960
RETR,STOP=0.08,0.10; SPLIT='2026-05-01'
def slip(p): return max(0.0015,0.015/p)
pc={f"{x['ticker']}|{x['date']}":x['prev_close'] for x in json.load(open(os.path.join(DATA,'candidates.json')))}
fc=json.load(open(os.path.join(DATA,'float_cache.json')))

def eod(mins,h,l,c,i):
    e=c[i];sl=slip(e);ef=e*(1+sl);st=e*(1-STOP);ex=None;last=e
    for j in range(i+1,len(c)):
        if mins[j]<OPEN or mins[j]>=EXEND:
            if mins[j]>=EXEND:break
            continue
        if l[j]<=st:ex=st;break
        last=c[j]
    return (( (ex if ex is not None else last)*(1-sl))-ef)/ef*100

rows=[]
for path in sorted(glob.glob(os.path.join(BARS,'*.parquet'))):
    df=pd.read_parquet(path)
    for (tk,d),g in df.groupby(['ticker','date'],sort=False):
        p0=pc.get(f"{tk}|{d}")
        if not p0 or p0<=0: continue
        g=g.sort_values('datetime')
        mins=(g['datetime'].str.slice(0,2).astype(int)*60+g['datetime'].str.slice(3,5).astype(int)).to_numpy()
        o,h,l,c,v=(g[k].to_numpy(float) for k in ('o','h','l','c','v'))
        hod=np.maximum.accumulate(h);gap=(hod-p0)/p0*100;i0=-1
        for i in range(len(c)):
            if mins[i]<OPEN or mins[i]>=ENTEND or hod[i]<=0: continue
            if not(GMIN<=gap[i]<=GMAX): continue
            if (hod[i]-c[i])/hod[i]>=RETR and PMIN<=c[i]<=PMAX and v[i]*c[i]>=LIQ: i0=i; break
        if i0<0: continue
        hidx=int(np.argmax(h[:i0+1]))                 # bougie du sommet
        runup=float((v[:hidx+1]*c[:hidx+1]).sum())    # $vol cumulé jusqu'au sommet
        dvol=float(v[i0]*c[i0])                        # $vol de la bougie de repli
        f=fc.get(tk,{})
        rows.append({'date':d,'pnl':eod(mins,h,l,c,i0),
                     'float_m':(f.get('float')/1e6 if f.get('float') else np.nan),
                     'inst':(f.get('inst') if f.get('inst') is not None else np.nan),
                     'runup_m':runup/1e6,'dvol_k':dvol/1e3})
t=pd.DataFrame(rows)
te=t[t.date>=SPLIT]
def stat(a):
    a=np.asarray(a,float);n=len(a)
    if n<25: return None
    e=a.mean();tt=e/(a.std(ddof=1)/np.sqrt(n)) if n>1 and a.std(ddof=1)>0 else 0
    return e,tt,n
print(f"BASE repli8/stop10/EOD | n={len(t)} | OOS n={len(te)} exp={te['pnl'].mean():+.2f}%\n")
def buckets(col,edges,lab,unit=''):
    print(f"--- {lab} ---")
    for lo,hi in edges:
        if lo=='NA': sub=te[te[col].isna()]; name='inconnu'
        else: sub=te[(te[col]>=lo)&(te[col]<hi)]; name=f"{lo}-{hi if hi<1e12 else '+'}{unit}"
        s=stat(sub['pnl'])
        if s: print(f"  {name:<14} n={s[0+2]:>4} exp={s[0]:>+6.2f}% t={s[1]:>+5.2f}")
    print()
buckets('float_m',[(0,5),(5,10),(10,20),(20,50),(50,150),(150,1e12),('NA',0)],'FLOAT (M actions)','M')
buckets('inst',[(0,5),(5,15),(15,30),(30,60),(60,1e12),('NA',0)],'INSTITUTIONS (%)','%')
buckets('runup_m',[(0,2),(2,5),(5,15),(15,40),(40,100),(100,1e12)],'$VOL MONTÉE AU SOMMET','M$')
buckets('dvol_k',[(200,500),(500,1000),(1000,3000),(3000,1e12)],'$VOL BOUGIE DE REPLI','K$')
