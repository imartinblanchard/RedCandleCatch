#!/usr/bin/env python3
"""ÉTUDE DES SORTIES sur les trades RÉELS (journal) + données follow-through (jour N + N+1).
Compare, pour chaque trade, la sortie ACTUELLE (15:55 EOD) à des sorties AU-DELÀ de la clôture :
 - after-hours (plus-haut 16:00-20:00 du jour N, sur VOLUME réel >0 = négociable)
 - lendemain OPEN (N+1 09:30) / lendemain 15:55 / lendemain plus-haut RTH (borne sup look-ahead)
Entrée = prix du journal. Stop overnight non garanti (gap) -> on signale les gaps.
Usage : python research/live_lab/exit_study.py
"""
import os, sys, csv, glob
import numpy as np, pandas as pd
HERE=os.path.dirname(os.path.abspath(__file__)); ROOT=os.path.dirname(os.path.dirname(HERE))
DATA=os.path.join(ROOT,'data','collected_live')
JOURNAL=os.path.join(ROOT,'data','computed','redcandlecatch-journal.csv')

def px_at(df, day, hhmm):
    r=df[(df.date==day)&(df.datetime.str[11:]==hhmm)]
    return float(r.c.iloc[0]) if len(r) else None

def main():
    trades=list(csv.DictReader(open(JOURNAL)))
    rows=[]
    for tr in trades:
        day=tr['date']; tk=tr['ticker']
        fp=os.path.join(DATA,f'followthrough-{day}.parquet')
        if not os.path.exists(fp): continue
        f=pd.read_parquet(fp); f=f[f.ticker==tk]
        if not len(f): continue
        entry=float(tr['entry'])
        days=sorted(f.date.unique());
        if len(days)<2: continue
        N, N1 = days[0], days[1]
        dN=f[f.date==N]; dN1=f[f.date==N1]
        # sortie 15:55 jour N (actuelle)
        eod=px_at(f,N,'15:55') or float(tr['exit'])
        # after-hours jour N : plus-haut sur bougies a VOLUME>0 (negociable), apres 16:00
        ah=dN[(dN.datetime.str[11:]>='16:00')&(dN.v>0)]
        ah_hi=float(ah.h.max()) if len(ah) else None
        # lendemain
        rth1=dN1[dN1.datetime.str[11:]>='09:30']
        nopen=float(rth1.o.iloc[0]) if len(rth1) else None
        nclose=px_at(f,N1,'15:55')
        nhigh=float(rth1[rth1.datetime.str[11:]<='15:55'].h.max()) if len(rth1) else None
        def pnl(x): return round((x-entry)/entry*100,2) if x else None
        rows.append(dict(date=day,ticker=tk,entry=entry,
            eod=pnl(eod), ah_high=pnl(ah_hi), next_open=pnl(nopen),
            next_close=pnl(nclose), next_high=pnl(nhigh),
            gap_overnight=pnl(nopen) if nopen else None))
    d=pd.DataFrame(rows)
    print(f"{len(d)} trades avec donnees follow-through N+1\n")
    def stat(col):
        v=d[col].dropna()
        return f"n={len(v):>2} moy={v.mean():>+6.2f}% med={v.median():>+6.2f}% win={(v>0).mean()*100:>3.0f}% pire={v.min():>+6.1f}%"
    print("STRATÉGIE DE SORTIE                         "+"")
    print(f"  15:55 EOD (ACTUELLE)        {stat('eod')}")
    print(f"  after-hours high (vol>0)    {stat('ah_high')}   [borne sup AH, limite requise]")
    print(f"  lendemain OPEN (09:30)      {stat('next_open')}   [realiste, liquide]")
    print(f"  lendemain 15:55            {stat('next_close')}")
    print(f"  lendemain HIGH RTH          {stat('next_high')}   [borne sup look-ahead]")
    # recents (v3, a partir du 07/10) a part
    dr=d[d.date>='2026-10-07']
    print(f"\n--- seulement trades RÉCENTS v3 (>=07/10, n={len(dr)}) ---")
    for c,lab in [('eod','15:55 EOD'),('ah_high','AH high'),('next_open','lend. open'),('next_high','lend. high')]:
        v=dr[c].dropna(); print(f"  {lab:<12} moy={v.mean():>+6.2f}% (n={len(v)})" if len(v) else f"  {lab}: 0")
    d.to_csv(os.path.join(HERE,'exit_study.csv'),index=False)
    print(f"\n-> detail par trade : research/live_lab/exit_study.csv")

if __name__=='__main__': main()
