#!/usr/bin/env python3
"""Ajoute des colonnes descriptives a gappers.json, calculees depuis les bougies 1-min :
  pct_930   : prix a 9:30 vs cloture veille (le run a-t-il tenu jusqu'a l'ouverture ?)
  drop_high : chute max DEPUIS LE SOMMET du jour (pump & dump ?)
  drop_10   : chute max DEPUIS le niveau +10% (ou le scanner alerte) = risque cote scanner
  drop_open : chute max DEPUIS l'ouverture 04:00
A lancer APRES le fetch des 1-min."""
import json, os
import pandas as pd

R='/home/martin/dev/stock-journal-long/research'; CACHE=f'{R}/bars_cache'
g=json.load(open(f'{R}/gappers.json'))

def et_hm(ts): return (ts.hour, ts.minute)

done=0
for x in g:
    f=f"{CACHE}/{x['ticker']}_{x['date']}.json"
    x['pct_930']=x['drop_high']=x['drop_10']=x['drop_open']=None
    if not os.path.exists(f): continue
    raw=json.load(open(f))
    if len(raw)<5: continue
    df=pd.DataFrame(raw); df['t']=pd.to_datetime(df['t'])
    df['et']=df['t'].dt.tz_convert('America/New_York')
    df=df.sort_values('t').reset_index(drop=True)
    pc=x.get('prev_close'); po=x.get('pm_open')
    if not pc or pc<=0: continue

    # prix a 9:30 (1ere bougie >= 09:30) vs cloture veille
    mask=df['et'].apply(lambda t: et_hm(t)>=(9,30))
    if mask.any():
        p930=df.loc[mask.idxmax(),'o']
        x['pct_930']=round((p930-pc)/pc*100,1)

    # chute max depuis le sommet du jour
    hidx=df['h'].idxmax(); hi=df.loc[hidx,'h']
    low_after=df.loc[hidx:,'l'].min()
    x['drop_high']=round((low_after-hi)/hi*100,1)

    # chute max depuis le niveau +10% (1.10 x cloture veille)
    ref10=1.10*pc
    crossed=df.index[df['h']>=ref10]
    if len(crossed):
        ci=crossed[0]; low_after10=df.loc[ci:,'l'].min()
        x['drop_10']=round((low_after10-ref10)/ref10*100,1)

    # chute max depuis l'ouverture 04:00
    if po and po>0:
        x['drop_open']=round((df['l'].min()-po)/po*100,1)
    done+=1

json.dump(g,open(f'{R}/gappers.json','w'))
print(f"colonnes ajoutees pour {done}/{len(g)} gappers")
print("exemple:", {k:g[0][k] for k in ('ticker','date','gap','pct_930','drop_high','drop_10','drop_open')} if g else '-')
