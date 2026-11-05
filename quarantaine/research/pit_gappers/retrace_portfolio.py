#!/usr/bin/env python3
"""PORTEFEUILLE de la stratégie RETRACE (entrée = repli X% depuis le HOD), compte 10 000$.
Sizing BASÉ SUR LE STOP : risque R% de l'équité/trade -> shares = risque$/(entrée-stop) ;
comme stop=10%, position = (R%/10%) de l'équité (capée). Positions concurrentes, compounding,
commissions IBKR. On TESTE plusieurs PRISES DE PROFIT (trailing vs take-profit fixes).

Univers : gap 5-10 recheck, post-open, prix 3-20, liq bougie >=200K. OOS non séparé ici
(rendement composé sur toute la période) ; l'edge/OOS a déjà été validé (retrace_study.py).
"""
import os, glob, json, itertools
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__)); DATA = os.path.join(HERE, 'data')
BARS_DIR = os.path.join(DATA, 'bars')
GMIN, GMAX = 5.0, 10.0
PMIN, PMAX, LIQ = 3.0, 20.0, 200_000
STOP = 0.10
OPEN_NEXT, ENTRY_END, EXIT_END = 571, 955, 960
INIT = 10_000.0
COMM_SH, COMM_MIN = 0.005, 1.0
RETRS = [0.08, 0.10]
def slip_of(p): return max(0.0015, 0.015 / p)

# ---- prises de profit à comparer : renvoie (pnl%, exit_index) depuis l'entrée i ----
def ex_trail(mins, h, l, c, i, act, trail=0.02):
    e=float(c[i]); sl=slip_of(e); ef=e*(1+sl); st,ac=e*(1-STOP),e*(1+act)
    activ=False; peak=e; ex=None; xi=len(c)-1
    for j in range(i+1,len(c)):
        if mins[j]<OPEN_NEXT or mins[j]>=EXIT_END:
            if mins[j]>=EXIT_END: xi=j-1; break
            continue
        if not activ:
            if l[j]<=st: ex=st; xi=j; break
            peak=max(peak,h[j])
            if h[j]>=ac: activ=True
        else:
            ts=peak*(1-trail)
            if l[j]<=ts: ex=ts; xi=j; break
            peak=max(peak,h[j])
    if ex is None: ex=float(c[xi])
    return (ex*(1-sl)-ef)/ef*100, xi

def ex_bracket(mins, h, l, c, i, tp):
    e=float(c[i]); sl=slip_of(e); ef=e*(1+sl); st,tgt=e*(1-STOP),e*(1+tp)
    ex=None; xi=len(c)-1
    for j in range(i+1,len(c)):
        if mins[j]<OPEN_NEXT or mins[j]>=EXIT_END:
            if mins[j]>=EXIT_END: xi=j-1; break
            continue
        if l[j]<=st: ex=st; xi=j; break
        if h[j]>=tgt: ex=tgt; xi=j; break
    if ex is None: ex=float(c[xi])
    return (ex*(1-sl)-ef)/ef*100, xi

EXITS = {
    'trail act+10':  lambda m,h,l,c,i: ex_trail(m,h,l,c,i,0.10),
    'trail act+5':   lambda m,h,l,c,i: ex_trail(m,h,l,c,i,0.05),
    'TP +10%':       lambda m,h,l,c,i: ex_bracket(m,h,l,c,i,0.10),
    'TP +15%':       lambda m,h,l,c,i: ex_bracket(m,h,l,c,i,0.15),
    'TP +20%':       lambda m,h,l,c,i: ex_bracket(m,h,l,c,i,0.20),
}

def gen_all():
    """1 passe : pour chaque ticker-jour, entrée retrace (8 et 10%) + toutes les sorties.
    -> trades[(retr,exit)] = [(entry_dt, exit_dt, entry_price, pnl%)]."""
    pc_map={f"{x['ticker']}|{x['date']}":x['prev_close'] for x in json.load(open(os.path.join(DATA,'candidates.json')))}
    trades={(r,e):[] for r in RETRS for e in EXITS}
    for path in sorted(glob.glob(os.path.join(BARS_DIR,'*.parquet'))):
        df=pd.read_parquet(path)
        for (tk,date),g in df.groupby(['ticker','date'],sort=False):
            pc=pc_map.get(f"{tk}|{date}")
            if not pc or pc<=0: continue
            g=g.sort_values('datetime'); dt=g['datetime'].to_numpy()
            mins=(g['datetime'].str.slice(0,2).astype(int)*60+g['datetime'].str.slice(3,5).astype(int)).to_numpy()
            o,h,l,c,v=(g[k].to_numpy(float) for k in ('o','h','l','c','v'))
            hod=np.maximum.accumulate(h); run_gap=(hod-pc)/pc*100
            for retr in RETRS:
                i0=-1
                for i in range(len(c)):
                    if mins[i]<OPEN_NEXT or mins[i]>=ENTRY_END: continue
                    if not (GMIN<=run_gap[i]<=GMAX) or hod[i]<=0: continue
                    if (hod[i]-c[i])/hod[i]>=retr and PMIN<=c[i]<=PMAX and v[i]*c[i]>=LIQ:
                        i0=i; break
                if i0<0: continue
                for en,fn in EXITS.items():
                    pnl,xi=fn(mins,h,l,c,i0)
                    edt=pd.Timestamp(f"{date} {dt[i0]}"); xdt=pd.Timestamp(f"{date} {dt[xi]}")
                    trades[(retr,en)].append((edt,xdt,float(c[i0]),pnl))
    return trades

def simulate(trades, risk_pct, max_pos, max_frac=0.25):
    """Sizing basé sur le stop : position = (risk_pct/STOP) de l'équité, capée à max_frac."""
    frac=min(risk_pct/STOP, max_frac)
    ev=[]
    for idx,(edt,xdt,ep,pnl) in enumerate(trades):
        ev.append((edt,1,idx)); ev.append((xdt,0,idx))
    ev.sort(key=lambda e:(e[0],e[1]))
    cash=INIT; openp={}; peak=INIT; maxdd=0.0; nt=0; wins=0
    for _,typ,idx in ev:
        if typ==0:
            if idx in openp:
                sh,ep=openp.pop(idx); pnl=trades[idx][3]
                cash+=sh*ep*(1+pnl/100)-max(COMM_MIN,COMM_SH*sh); wins+=pnl>0
        else:
            if len(openp)>=max_pos: continue
            ep=trades[idx][2]; equity=cash+sum(s*p for s,p in openp.values())
            alloc=min(equity*frac,cash); sh=int(alloc/ep)
            if sh<1: continue
            cash-=sh*ep+max(COMM_MIN,COMM_SH*sh); openp[idx]=(sh,ep); nt+=1
        eq=cash+sum(s*p for s,p in openp.values()); peak=max(peak,eq); maxdd=min(maxdd,eq/peak-1)
    final=cash+sum(s*p for s,p in openp.values())
    return final,maxdd,nt,(wins/nt*100 if nt else 0)

def main():
    trades=gen_all()
    days=len({t[0].date() for r in RETRS for e in EXITS for t in trades[(r,e)]})
    years=days/252 if days else 1
    RISK, MAXP = 0.01, 10        # risque 1%/trade (=10% position), max 10 positions concurrentes
    print(f"Compte {INIT:,.0f}$ | sizing RISQUE {RISK*100:.0f}%/trade (stop {STOP*100:.0f}% -> position {RISK/STOP*100:.0f}%), "
          f"max {MAXP} pos | {days} jours (~{years:.1f} an) | commissions IBKR\n")
    for retr in RETRS:
        print(f"===== ENTRÉE : repli {retr*100:.0f}% du HOD =====")
        print(f"  {'prise de profit':16}{'final$':>11}{'rend':>8}{'CAGR':>8}{'maxDD':>8}{'win%':>6}{'trades':>7}")
        for en in EXITS:
            f,dd,nt,w=simulate(trades[(retr,en)],RISK,MAXP)
            cagr=(f/INIT)**(1/years)-1 if years>0 and f>0 else -1
            print(f"  {en:16}{f:>11,.0f}{(f/INIT-1)*100:>+7.0f}%{cagr*100:>+7.0f}%{dd*100:>+7.0f}%{w:>6.0f}{nt:>7}")
        print()
    # petit balayage de sizing sur le meilleur combo (repli 10% / trail act+10)
    print("=== sizing sweep — repli 10%, trail act+10 ===")
    print(f"  {'risque/trade':14}{'max pos':>8}{'final$':>11}{'rend':>8}{'maxDD':>8}")
    for risk,mp in itertools.product([0.005,0.01,0.02],[5,10,15]):
        f,dd,nt,w=simulate(trades[(0.10,'trail act+10')],risk,mp)
        print(f"  {f'{risk*100:.1f}%':14}{mp:>8}{f:>11,.0f}{(f/INIT-1)*100:>+7.0f}%{dd*100:>+7.0f}%")

if __name__=='__main__':
    main()
