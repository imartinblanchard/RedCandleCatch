#!/usr/bin/env python3
"""TOUTES les combinaisons repli(entrée) x STOP x TP, gap 5-10, post-open. Métrique CLÉ au
niveau compte = expectancy en R (exp% / stop%), car le sizing est risque/trade = position
risk%/stop% -> le stop change la taille. TP=EOD signifie 'pas de TP, on tient jusqu'à 15:55'.
Sort, par niveau de repli, une table STOP x TP en R (et exp%), en OOS test. Point-in-time.
"""
import os, glob, json
import numpy as np, pandas as pd

HERE=os.path.dirname(os.path.abspath(__file__)); DATA=os.path.join(HERE,'data'); BARS=os.path.join(DATA,'bars')
GMIN,GMAX,PMIN,PMAX,LIQ=5.0,10.0,3.0,20.0,200_000
OPEN,ENTEND,EXEND=571,955,960
SPLIT='2026-05-01'
RETRS=[5,8,10,12]
STOPS=[0.05,0.07,0.10,0.12,0.15]
TPS=[('+10',0.10),('+15',0.15),('+20',0.20),('+30',0.30),('EOD',9.99)]
def slip(p): return max(0.0015,0.015/p)

def build():
    pc_map={f"{x['ticker']}|{x['date']}":x['prev_close'] for x in json.load(open(os.path.join(DATA,'candidates.json')))}
    recs={(r,s,tn):[] for r in RETRS for s in STOPS for tn,_ in TPS}
    dates={k:[] for k in recs}
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
                    if not(GMIN<=gap[i]<=GMAX): continue
                    if (hod[i]-c[i])/hod[i]>=retr/100 and PMIN<=c[i]<=PMAX and v[i]*c[i]>=LIQ: i0=i; break
                if i0<0: continue
                e=float(c[i0]); sl=slip(e); ef=e*(1+sl)
                # bougies forward valides (RTH jusqu'à 16:00)
                m=[]; lo=[]; hi=[]
                for j in range(i0+1,len(c)):
                    if mins[j]<OPEN or mins[j]>=EXEND:
                        if mins[j]>=EXEND: break
                        continue
                    lo.append(l[j]); hi.append(h[j])
                lo=np.array(lo); hi=np.array(hi)
                eod=float(c[i0]) if len(lo)==0 else None
                # dernière close valide pour EOD
                if eod is None:
                    tail=[c[j] for j in range(i0+1,len(c)) if OPEN<=mins[j]<EXEND]
                    eod=tail[-1] if tail else e
                for s in STOPS:
                    sp=e*(1-s)
                    ts=np.argmax(lo<=sp) if len(lo) and (lo<=sp).any() else 10**9
                    for tn,tp in TPS:
                        tgt=e*(1+tp)
                        tt=np.argmax(hi>=tgt) if len(hi) and (hi>=tgt).any() else 10**9
                        if tt<ts: ex=tgt
                        elif ts<tt: ex=sp
                        else: ex=eod                       # ni l'un ni l'autre -> EOD
                        pnl=(ex*(1-sl)-ef)/ef*100
                        recs[(retr,s,tn)].append(pnl); dates[(retr,s,tn)].append(d)
    return recs,dates

def st(a):
    a=np.asarray(a,float);n=len(a)
    if n<10: return None
    e=a.mean(); t=e/(a.std(ddof=1)/np.sqrt(n)) if n>1 and a.std(ddof=1)>0 else 0
    return e,t,n

recs,dates=build()
for retr in RETRS:
    print(f"\n===== repli {retr}% — STOP x TP, TEST OOS : R (exp%/stop) [exp%] =====")
    print(f"{'stop \\ TP':<10}"+"".join(f"{tn:>16}" for tn,_ in TPS))
    for s in STOPS:
        cells=[]
        for tn,_ in TPS:
            d=np.array(dates[(retr,s,tn)]); a=np.array(recs[(retr,s,tn)])
            mask=d>=SPLIT
            r=st(a[mask])
            if r: cells.append(f"{r[0]/(s*100):>+5.2f}R[{r[0]:>+4.2f}]")
            else: cells.append("      -       ")
        print(f"{('-'+str(int(s*100))+'%'):<10}"+"".join(f"{c:>16}" for c in cells))
