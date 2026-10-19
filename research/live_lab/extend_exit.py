#!/usr/bin/env python3
"""EXTENSION DE LA SORTIE : MÊME stratégie v3 (stop -10% + sortie forcée), mais on repousse
l'HEURE de sortie forcée au-delà de 15:55. Le stop -10% reste actif tout du long (after-hours
+ overnight : un gap sous le stop sort au prix d'ouverture). Entrées = celles de la v3.
Données = follow-through (jour N + N+1, 1-min). Compare 15:55 (actuel) a des cutoffs plus tardifs.
Usage : python research/live_lab/extend_exit.py
"""
import os, sys, glob
import numpy as np, pandas as pd
HERE=os.path.dirname(os.path.abspath(__file__)); ROOT=os.path.dirname(os.path.dirname(HERE))
DATA=os.path.join(ROOT,'data','collected_live')
sys.path.insert(0, ROOT)
import research.live_lab.backtest as bt

# cutoffs de sortie forcée : (offset_jour, 'HH:MM')
CUTOFFS=[('15:55 (ACTUEL)',0,'15:55'), ('17:00 N',0,'17:00'), ('19:59 N (fin AH)',0,'19:59'),
         ('N+1 open 09:30',1,'09:30'), ('N+1 12:00',1,'12:00'), ('N+1 15:55',1,'15:55')]
STOP=0.10

def exit_pnl(bars, entry, stop_px, cutoff_day, cutoff_hhmm):
    """bars: DataFrame (datetime 'YYYY-MM-DD HH:MM', date, o,h,l,c) depuis l'entrée, trie.
    Marche jusqu'au cutoff ; si low<=stop avant -> sortie au stop ; sinon close du cutoff."""
    days=sorted(bars.date.unique())
    if cutoff_day>=len(days): cutoff_hhmm='23:59'; cutoff_day=len(days)-1
    limit_day=days[cutoff_day]
    for _,b in bars.iterrows():
        if b.date>limit_day or (b.date==limit_day and b.datetime[11:]>cutoff_hhmm):
            break
        if b.l<=stop_px:                        # stop touché (gap inclus : on sort au stop)
            return (stop_px-entry)/entry*100
        last=b.c
    return (last-entry)/entry*100

def main():
    g,dates=bt.load_groups()
    t=bt.simulate(g,bt.LIVE,slip=True)
    res={lab:[] for lab,_,_ in CUTOFFS}; miss=0; used=0
    for _,r in t.iterrows():
        fp=os.path.join(DATA,f'followthrough-{r.date}.parquet')
        if not os.path.exists(fp): miss+=1; continue
        f=pd.read_parquet(fp); f=f[(f.ticker==r.ticker)].sort_values('datetime')
        # bars depuis l'entrée (jour N, heure >= entry_min)
        em=f"{int(r.entry_min)//60:02d}:{int(r.entry_min)%60:02d}"
        f=f[(f.date>r.date) | ((f.date==r.date)&(f.datetime.str[11:]>=em))]
        if len(f)<2 or f.date.nunique()<2: miss+=1; continue
        used+=1; entry=float(r.entry); stop_px=entry*(1-STOP)
        for lab,off,hh in CUTOFFS:
            res[lab].append(exit_pnl(f, entry, stop_px, off, hh))
    print(f"{used} entrées v3 avec follow-through complet (N+1) | {miss} sans donnée\n")
    print(f"{'SORTIE FORCÉE':<20}{'moy':>8}{'médiane':>9}{'win':>6}{'pire':>8}")
    for lab,_,_ in CUTOFFS:
        v=np.array(res[lab])
        if not len(v): print(f"  {lab:<18} (n=0)"); continue
        print(f"  {lab:<18}{v.mean():>+7.2f}%{np.median(v):>+8.2f}%{(v>0).mean()*100:>5.0f}%{v.min():>+7.1f}%")
    print(f"\n(stop -10% actif en continu ; cutoffs after-hours = close de la minute, "
          f"idéalisé car l'AH est peu liquide)")

if __name__=='__main__': main()
