#!/usr/bin/env python3
"""Portefeuille (10k$, sizing RISQUE/trade -> position = risk%/stop, commissions IBKR, positions
concurrentes, compounding) du combo gagnant de la grille vs l'actuel. Gap 5-10, post-open.
+ expectancy TRAIN vs TEST par config (anti sur-ajustement). Point-in-time.
Configs :
  ACTUEL   : dip -1.5%, stop -10%, activation +10% -> trail 2%
  retrace8 : repli 8% du HOD, stop -10%, hold-to-EOD
  retrace10: repli 10% du HOD, stop -7%, hold-to-EOD
  GRILLE   : repli 12% du HOD, stop -5%, hold-to-EOD   <- gagnant grille
"""
import os, glob, json, itertools
import numpy as np, pandas as pd

HERE=os.path.dirname(os.path.abspath(__file__)); DATA=os.path.join(HERE,'data'); BARS=os.path.join(DATA,'bars')
GMIN,GMAX,PMIN,PMAX,LIQ=5.0,10.0,3.0,20.0,200_000
OPEN,ENTEND,EXEND=571,955,960
INIT=10_000.0; COMM_SH,COMM_MIN=0.005,1.0; SPLIT='2026-05-01'
def slip(p): return max(0.0015,0.015/p)

def eod_stop(mins,h,l,c,i,stop):
    e=float(c[i]); sl=slip(e); ef=e*(1+sl); st=e*(1-stop); ex=None; xi=len(c)-1
    for j in range(i+1,len(c)):
        if mins[j]<OPEN or mins[j]>=EXEND:
            if mins[j]>=EXEND: xi=j-1; break
            continue
        if l[j]<=st: ex=st; xi=j; break
        xi=j
    if ex is None: ex=float(c[xi])
    return (ex*(1-sl)-ef)/ef*100, xi

def trail(mins,h,l,c,i,stop,act,tr):
    e=float(c[i]); sl=slip(e); ef=e*(1+sl); st,ac=e*(1-stop),e*(1+act); activ=False; peak=e; ex=None; xi=len(c)-1
    for j in range(i+1,len(c)):
        if mins[j]<OPEN or mins[j]>=EXEND:
            if mins[j]>=EXEND: xi=j-1; break
            continue
        if not activ:
            if l[j]<=st: ex=st; xi=j; break
            peak=max(peak,h[j])
            if h[j]>=ac: activ=True
        else:
            ts=peak*(1-tr)
            if l[j]<=ts: ex=ts; xi=j; break
            peak=max(peak,h[j])
        xi=j
    if ex is None: ex=float(c[xi])
    return (ex*(1-sl)-ef)/ef*100, xi

# config -> (entry_kind, param, stop_frac, exit_fn)
def entry_dip(mins,o,h,l,c,v,gap):     # -1.5% intra-bougie
    for i in range(len(c)):
        if mins[i]<OPEN or mins[i]>=ENTEND: continue
        if not(GMIN<=gap[i]<=GMAX): continue
        if o[i]>0 and (c[i]-o[i])/o[i]<=-0.015 and PMIN<=c[i]<=PMAX and v[i]*c[i]>=LIQ: return i
    return -1
def entry_retr(mins,o,h,l,c,v,gap,hod,retr):
    for i in range(len(c)):
        if mins[i]<OPEN or mins[i]>=ENTEND or hod[i]<=0: continue
        if not(GMIN<=gap[i]<=GMAX): continue
        if (hod[i]-c[i])/hod[i]>=retr and PMIN<=c[i]<=PMAX and v[i]*c[i]>=LIQ: return i
    return -1

CONFIGS={
 'ACTUEL dip1.5/stop10/trail': ('dip',None,0.10,lambda m,h,l,c,i:trail(m,h,l,c,i,0.10,0.10,0.02)),
 'retrace8 stop10 EOD':        ('retr',0.08,0.10,lambda m,h,l,c,i:eod_stop(m,h,l,c,i,0.10)),
 'retrace10 stop7 EOD':        ('retr',0.10,0.07,lambda m,h,l,c,i:eod_stop(m,h,l,c,i,0.07)),
 'GRILLE retrace12 stop5 EOD': ('retr',0.12,0.05,lambda m,h,l,c,i:eod_stop(m,h,l,c,i,0.05)),
}

def gen():
    pc_map={f"{x['ticker']}|{x['date']}":x['prev_close'] for x in json.load(open(os.path.join(DATA,'candidates.json')))}
    trades={k:[] for k in CONFIGS}
    for path in sorted(glob.glob(os.path.join(BARS,'*.parquet'))):
        df=pd.read_parquet(path)
        for (tk,d),g in df.groupby(['ticker','date'],sort=False):
            pc=pc_map.get(f"{tk}|{d}")
            if not pc or pc<=0: continue
            g=g.sort_values('datetime'); dt=g['datetime'].to_numpy()
            mins=(g['datetime'].str.slice(0,2).astype(int)*60+g['datetime'].str.slice(3,5).astype(int)).to_numpy()
            o,h,l,c,v=(g[k].to_numpy(float) for k in ('o','h','l','c','v'))
            hod=np.maximum.accumulate(h); gap=(hod-pc)/pc*100
            for name,(kind,param,stopf,exfn) in CONFIGS.items():
                i0=entry_dip(mins,o,h,l,c,v,gap) if kind=='dip' else entry_retr(mins,o,h,l,c,v,gap,hod,param)
                if i0<0: continue
                pnl,xi=exfn(mins,h,l,c,i0)
                trades[name].append((pd.Timestamp(f"{d} {dt[i0]}"),pd.Timestamp(f"{d} {dt[xi]}"),float(c[i0]),pnl,stopf,d))
    return trades

def simulate(tr,risk,maxpos,maxfrac=0.25):
    ev=[]
    for idx,t in enumerate(tr):
        ev.append((t[0],1,idx)); ev.append((t[1],0,idx))
    ev.sort(key=lambda e:(e[0],e[1]))
    cash=INIT; openp={}; peak=INIT; maxdd=0.0; nt=0; wins=0
    for _,typ,idx in ev:
        if typ==0:
            if idx in openp:
                sh,ep=openp.pop(idx); pnl=tr[idx][3]
                cash+=sh*ep*(1+pnl/100)-max(COMM_MIN,COMM_SH*sh); wins+=pnl>0
        else:
            if len(openp)>=maxpos: continue
            ep=tr[idx][2]; stopf=tr[idx][4]; equity=cash+sum(s*p for s,p in openp.values())
            frac=min(risk/stopf,maxfrac); alloc=min(equity*frac,cash); sh=int(alloc/ep)
            if sh<1: continue
            cash-=sh*ep+max(COMM_MIN,COMM_SH*sh); openp[idx]=(sh,ep); nt+=1
        eq=cash+sum(s*p for s,p in openp.values()); peak=max(peak,eq); maxdd=min(maxdd,eq/peak-1)
    final=cash+sum(s*p for s,p in openp.values())
    return final,maxdd,nt,(wins/nt*100 if nt else 0)

tr=gen()
days=len({t[5] for k in CONFIGS for t in tr[k]}); years=days/252
print(f"Compte {INIT:,.0f}$ | risque 1%/trade | max 10 pos | {days} jours (~{years:.1f} an) | commissions IBKR\n")
print(f"{'config':<30}{'final$':>10}{'rend':>7}{'CAGR':>7}{'maxDD':>7}{'win%':>6}{'n':>6}  {'exp TRAIN/TEST'}")
for name in CONFIGS:
    f,dd,nt,w=simulate(tr[name],0.01,10)
    a=np.array([t[3] for t in tr[name]]); dts=np.array([t[5] for t in tr[name]])
    eTr=a[dts<SPLIT].mean() if (dts<SPLIT).any() else 0; eTe=a[dts>=SPLIT].mean() if (dts>=SPLIT).any() else 0
    cagr=(f/INIT)**(1/years)-1 if years>0 and f>0 else -1
    print(f"{name:<30}{f:>10,.0f}{(f/INIT-1)*100:>+6.0f}%{cagr*100:>+6.0f}%{dd*100:>+6.0f}%{w:>6.0f}{nt:>6}  {eTr:+.2f}%/{eTe:+.2f}%")

print("\n=== GRILLE retrace12/stop5/EOD — sweep sizing ===")
print(f"  {'risque/trade':14}{'max pos':>8}{'final$':>11}{'rend':>8}{'maxDD':>8}")
for risk,mp in itertools.product([0.005,0.01,0.02],[5,10,15]):
    f,dd,nt,w=simulate(tr['GRILLE retrace12 stop5 EOD'],risk,mp)
    print(f"  {f'{risk*100:.1f}%':14}{mp:>8}{f:>11,.0f}{(f/INIT-1)*100:>+7.0f}%{dd*100:>+7.0f}%")
