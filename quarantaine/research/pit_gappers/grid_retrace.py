#!/usr/bin/env python3
"""GRILLE : niveau de gap x niveau de REPLI depuis le HOD (obs Martin). Entrée = 1er repli
de X% depuis le plus-haut courant (post-open, prix 3-20, liq 200K), bucketée par le GAP à
l'entrée. Exit = HOLD-TO-EOD + stop -10% (le meilleur, cf retrace_portfolio : le TP n'est
quasi jamais touché). Sort une table gap x repli en expectancy, ALL + TEST OOS.
Sauvegarde les trades bruts dans data/trades_retrace.parquet pour d'autres découpes.
"""
import os, glob, json
import numpy as np, pandas as pd

HERE=os.path.dirname(os.path.abspath(__file__)); DATA=os.path.join(HERE,'data'); BARS=os.path.join(DATA,'bars')
PMIN,PMAX,LIQ=3.0,20.0,200_000
STOP=0.10; OPEN,ENTEND,EXEND=571,955,960
SPLIT='2026-05-01'
RETRS=[3,4,5,6,8,10,12,15]
GAPB=[(5,10),(10,15),(15,20),(20,30),(30,50),(50,100),(100,1e9)]
def slip(p): return max(0.0015,0.015/p)

def eod_stop(mins,h,l,c,i):
    e=float(c[i]); sl=slip(e); ef=e*(1+sl); st=e*(1-STOP); ex=None; last=e
    for j in range(i+1,len(c)):
        if mins[j]<OPEN or mins[j]>=EXEND:
            if mins[j]>=EXEND: break
            continue
        if l[j]<=st: ex=st; break
        last=c[j]
    if ex is None: ex=last
    return (ex*(1-sl)-ef)/ef*100

def build():
    pc_map={f"{x['ticker']}|{x['date']}":x['prev_close'] for x in json.load(open(os.path.join(DATA,'candidates.json')))}
    rows=[]
    for path in sorted(glob.glob(os.path.join(BARS,'*.parquet'))):
        df=pd.read_parquet(path)
        for (tk,d),g in df.groupby(['ticker','date'],sort=False):
            pc=pc_map.get(f"{tk}|{d}")
            if not pc or pc<=0: continue
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
                rows.append((d,retr,float(gap[i0]),eod_stop(mins,h,l,c,i0)))
    return pd.DataFrame(rows,columns=['date','retr','gap','pnl'])

def stat(a):
    a=np.asarray(a,float);n=len(a)
    if n<8: return None
    e=a.mean(); t=e/(a.std(ddof=1)/np.sqrt(n)) if n>1 and a.std(ddof=1)>0 else 0
    return e,t,n

def show(df,title):
    print(f"\n===== {title} : expectancy%/tr (t) [n] =====")
    print(f"{'gap \\ repli':<12}"+"".join(f"{str(r)+'%':>13}" for r in RETRS))
    for lo,hi in GAPB:
        sub=df[(df.gap>=lo)&(df.gap<hi)]
        cells=[]
        for r in RETRS:
            s=stat(sub[sub.retr==r]['pnl'])
            cells.append(f"{s[0]:>+5.2f}({s[1]:>+3.1f})" if s else "     -     ")
        lab=f"{lo}-{hi if hi<1e9 else '+'}%"
        print(f"{lab:<12}"+"".join(f"{c:>13}" for c in cells))

df=build()
out=os.path.join(DATA,'trades_retrace.parquet'); df.to_parquet(out)
print(f"{len(df)} trades (ticker-jour x repli) -> {out}")
show(df,"TOUT (ALL)")
show(df[df.date>=SPLIT],"TEST OOS (mai-août)")
