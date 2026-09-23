#!/usr/bin/env python3
"""Config combinée : repli 8% + VOLUME DU REPLI CROISSANT (capitulation) + gate liquidité cumulé
>=300K$. Stop -10%, hold-EOD, gap 5-10. On (1) VALIDE train->test le filtre volume (choisi sur
le test), (2) mesure la config combinée train/test, (3) la passe au portefeuille (rend/DD)."""
import os, glob, json, itertools
import numpy as np, pandas as pd

HERE=os.path.dirname(os.path.abspath(__file__)); DATA=os.path.join(HERE,'data'); BARS=os.path.join(DATA,'bars')
GMIN,GMAX,PMIN,PMAX=5,10,3,20; OPEN,ENTEND,EXEND=571,955,960
RETR,STOP=0.08,0.10; GATE=300_000; SPLIT='2026-05-01'
INIT=10_000.0; COMM_SH,COMM_MIN=0.005,1.0
def slip(p): return max(0.0015,0.015/p)
pc={f"{x['ticker']}|{x['date']}":x['prev_close'] for x in json.load(open(os.path.join(DATA,'candidates.json')))}

def eod(mins,h,l,c,i):
    e=c[i];sl=slip(e);ef=e*(1+sl);st=e*(1-STOP);ex=None;xi=len(c)-1
    for j in range(i+1,len(c)):
        if mins[j]<OPEN or mins[j]>=EXEND:
            if mins[j]>=EXEND:xi=j-1;break
            continue
        if l[j]<=st:ex=st;xi=j;break
        xi=j
    return (((ex if ex is not None else c[xi])*(1-sl))-ef)/ef*100, xi

rows=[]
for path in sorted(glob.glob(os.path.join(BARS,'*.parquet'))):
    df=pd.read_parquet(path)
    for (tk,d),g in df.groupby(['ticker','date'],sort=False):
        p0=pc.get(f"{tk}|{d}")
        if not p0 or p0<=0: continue
        g=g.sort_values('datetime'); dt=g['datetime'].to_numpy()
        mins=(g['datetime'].str.slice(0,2).astype(int)*60+g['datetime'].str.slice(3,5).astype(int)).to_numpy()
        o,h,l,c,v=(g[k].to_numpy(float) for k in ('o','h','l','c','v'))
        hod=np.maximum.accumulate(h);gap=(hod-p0)/p0*100;i0=-1
        for i in range(len(c)):
            if mins[i]<OPEN or mins[i]>=ENTEND or hod[i]<=0: continue
            if not(GMIN<=gap[i]<=GMAX): continue
            if (hod[i]-c[i])/hod[i]>=RETR and PMIN<=c[i]<=PMAX: i0=i; break
        if i0<0: continue
        hidx=int(np.argmax(h[:i0+1])); dv=v[hidx+1:i0+1]*c[hidx+1:i0+1]
        pb=float(dv.sum()); dur=i0-hidx
        if pb<GATE: continue                              # gate liquidité CUMULÉ
        if dur>=4:
            hh=dur//2; a1=dv[:hh].mean(); trend=(dv[hh:].mean()/a1) if a1>0 else np.nan
        else: trend=np.nan
        pnl,xi=eod(mins,h,l,c,i0)
        rows.append({'date':d,'edt':pd.Timestamp(f"{d} {dt[i0]}"),'xdt':pd.Timestamp(f"{d} {dt[xi]}"),
                     'entry':float(c[i0]),'pnl':pnl,'dur':dur,'trend':trend})
t=pd.DataFrame(rows)
def ex(a):
    a=np.asarray(a,float);n=len(a)
    if n<20: return None
    e=a.mean();tt=e/(a.std(ddof=1)/np.sqrt(n)) if n>1 and a.std(ddof=1)>0 else 0
    return e,tt,n

print(f"Base repli8/stop10/EOD, gate cumulé >=300K$ | n={len(t)}\n")
print("=== (1) VALIDATION train->test du filtre 'volume du repli' (dur>=4) ===")
for lo,hi,nm in [(0,0.7,'décroissant'),(0.7,1.3,'plat'),(1.3,1e9,'CROISSANT (capit.)')]:
    tr=t[(t.trend>=lo)&(t.trend<hi)&(t.date<SPLIT)]; te=t[(t.trend>=lo)&(t.trend<hi)&(t.date>=SPLIT)]
    a=ex(tr['pnl']); b=ex(te['pnl'])
    f=lambda s:(f"{s[0]:+.2f}% t={s[1]:+.1f} n={s[2]}" if s else "n/a")
    print(f"  {nm:<20} TRAIN[{f(a)}]  TEST[{f(b)}]")

print("\n=== (2) Configs : expectancy train / test ===")
confs={'A base (gate 300K)':t, 'B + volume CROISSANT':t[(t.dur>=4)&(t.trend>1.3)]}
for nm,dd in confs.items():
    a=ex(dd[dd.date<SPLIT]['pnl']); b=ex(dd[dd.date>=SPLIT]['pnl'])
    f=lambda s:(f"{s[0]:+.2f}% (t{s[1]:+.1f}, n{s[2]})" if s else "n/a")
    print(f"  {nm:<24} TRAIN {f(a)}  |  TEST {f(b)}")

def sim(dd,risk,maxpos,maxfrac=0.25):
    tr=[(r.edt,r.xdt,r.entry,r.pnl) for r in dd.itertuples()]
    evs=[]
    for i,x in enumerate(tr): evs.append((x[0],1,i)); evs.append((x[1],0,i))
    evs.sort(key=lambda e:(e[0],e[1]))
    cash=INIT;op={};pk=INIT;mdd=0.0;nt=0;wins=0
    frac=min(risk/STOP,maxfrac)
    for _,ty,i in evs:
        if ty==0:
            if i in op:
                sh,ep=op.pop(i);pnl=tr[i][3];cash+=sh*ep*(1+pnl/100)-max(COMM_MIN,COMM_SH*sh);wins+=pnl>0
        else:
            if len(op)>=maxpos: continue
            ep=tr[i][2];eq=cash+sum(s*p for s,p in op.values());al=min(eq*frac,cash);sh=int(al/ep)
            if sh<1: continue
            cash-=sh*ep+max(COMM_MIN,COMM_SH*sh);op[i]=(sh,ep);nt+=1
        eq=cash+sum(s*p for s,p in op.values());pk=max(pk,eq);mdd=min(mdd,eq/pk-1)
    fin=cash+sum(s*p for s,p in op.values());return fin,mdd,nt,(wins/nt*100 if nt else 0)

days=t['date'].nunique(); years=days/252
print(f"\n=== (3) Portefeuille 10k$, risque 1%/tr, max 10 pos, ~{years:.1f} an ===")
for nm,dd in confs.items():
    f,mdd,nt,w=sim(dd,0.01,10); cagr=(f/INIT)**(1/years)-1 if f>0 else -1
    print(f"  {nm:<24} final {f:>9,.0f}$  rend {(f/INIT-1)*100:>+5.0f}%  CAGR {cagr*100:>+5.0f}%  maxDD {mdd*100:>+5.0f}%  win {w:.0f}%  n {nt}")
print("\n  sweep sizing (config B):")
for risk,mp in itertools.product([0.005,0.01,0.02],[10]):
    f,mdd,nt,w=sim(confs['B + volume CROISSANT'],risk,mp)
    print(f"    risque {risk*100:.1f}% -> {f:,.0f}$ ({(f/INIT-1)*100:+.0f}%), maxDD {mdd*100:+.0f}%")
