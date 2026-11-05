#!/usr/bin/env python3
"""Le REPLI est multi-bougies (obs Martin). On mesure sur TOUT le repli (du sommet HOD à
l'entrée) : $vol cumulé, durée (nb bougies), tendance du volume (décroissant=sain vs
croissant=distribution). Base = repli 8% / stop -10% / EOD, gap 5-10. SANS le gate 200K mono-
bougie (c'est lui qu'on veut remplacer). Bucket + edge/tr OOS. Rappel run-up : faible vol = bon."""
import os, glob, json
import numpy as np, pandas as pd

HERE=os.path.dirname(os.path.abspath(__file__)); DATA=os.path.join(HERE,'data'); BARS=os.path.join(DATA,'bars')
GMIN,GMAX,PMIN,PMAX=5,10,3,20; OPEN,ENTEND,EXEND=571,955,960
RETR,STOP=0.08,0.10; SPLIT='2026-05-01'
def slip(p): return max(0.0015,0.015/p)
pc={f"{x['ticker']}|{x['date']}":x['prev_close'] for x in json.load(open(os.path.join(DATA,'candidates.json')))}

def eod(mins,h,l,c,i):
    e=c[i];sl=slip(e);ef=e*(1+sl);st=e*(1-STOP);ex=None;last=e
    for j in range(i+1,len(c)):
        if mins[j]<OPEN or mins[j]>=EXEND:
            if mins[j]>=EXEND:break
            continue
        if l[j]<=st:ex=st;break
        last=c[j]
    return (((ex if ex is not None else last)*(1-sl))-ef)/ef*100

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
            if (hod[i]-c[i])/hod[i]>=RETR and PMIN<=c[i]<=PMAX: i0=i; break   # PAS de gate liq
        if i0<0: continue
        hidx=int(np.argmax(h[:i0+1]))
        dv=v[hidx+1:i0+1]*c[hidx+1:i0+1]                 # $vol des bougies DU REPLI
        pb_dvol=float(dv.sum()); dur=i0-hidx
        if dur>=4:
            half=dur//2; a1=dv[:half].mean(); a2=dv[half:].mean()
            trend=a2/a1 if a1>0 else np.nan
        else: trend=np.nan
        runup=float((v[:hidx+1]*c[:hidx+1]).sum())
        rows.append({'date':d,'pnl':eod(mins,h,l,c,i0),'pb_m':pb_dvol/1e6,'dur':dur,
                     'trend':trend,'runup_m':runup/1e6})
t=pd.DataFrame(rows); te=t[t.date>=SPLIT]
def stat(a):
    a=np.asarray(a,float);n=len(a)
    if n<25: return None
    e=a.mean();tt=e/(a.std(ddof=1)/np.sqrt(n)) if n>1 and a.std(ddof=1)>0 else 0
    return e,tt,n
print(f"BASE repli8/stop10/EOD SANS gate liq | n={len(t)} | OOS n={len(te)} exp={te['pnl'].mean():+.2f}%\n")
def buckets(col,edges,lab,unit=''):
    print(f"--- {lab} ---")
    for lo,hi in edges:
        sub=te[(te[col]>=lo)&(te[col]<hi)]; s=stat(sub['pnl'])
        name=f"{lo}-{hi if hi<1e9 else '+'}{unit}"
        if s: print(f"  {name:<14} n={s[2]:>4} exp={s[0]:>+6.2f}% t={s[1]:>+5.2f}")
    print()
buckets('pb_m',[(0,0.2),(0.2,0.5),(0.5,1),(1,3),(3,8),(8,1e9)],'$VOL CUMULÉ DU REPLI','M$')
buckets('dur',[(1,3),(3,6),(6,12),(12,25),(25,1e9)],'DURÉE DU REPLI (bougies)','')
print("--- TENDANCE VOL PENDANT LE REPLI (dur>=4) ---")
for lo,hi,nm in [(0,0.7,'décroissant <0.7'),(0.7,1.3,'plat 0.7-1.3'),(1.3,1e9,'croissant >1.3')]:
    sub=te[(te['trend']>=lo)&(te['trend']<hi)]; s=stat(sub['pnl'])
    if s: print(f"  {nm:<20} n={s[2]:>4} exp={s[0]:>+6.2f}% t={s[1]:>+5.2f}")
