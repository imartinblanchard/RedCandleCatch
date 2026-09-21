#!/usr/bin/env python3
"""
Construit LA table 1-min consolidee (source unique) depuis bars_cache.
- format long : 1 ligne / bougie, fenetre 04:00-09:30 ET
- indicateurs pre-calcules UNE fois (groupby ticker/date) -> colonnes pretes
- controles qualite (prix impossibles, splits) integres
Sortie : research/candles.parquet
"""
import json, os, glob
import numpy as np, pandas as pd

R='/home/martin/dev/stock-journal-long/research'
CACHE=f'{R}/bars_cache'; DCACHE=f'{R}/daily_cache'
import sys
GAPFILE=sys.argv[1] if len(sys.argv)>1 else f'{R}/gappers.json'
OUT=sys.argv[2] if len(sys.argv)>2 else f'{R}/candles.parquet'

# reference par ticker-jour (prev_close, avg daily vol pour le RVOL)
gap={(x['ticker'],x['date']):x for x in json.load(open(GAPFILE))}
def adv(tk,d):
    p=f'{DCACHE}/{tk}_{d}.json'
    return json.load(open(p)) if os.path.exists(p) else 0

# ---------- 1) charger toutes les bougies (long) ----------
rows=[]
for f in glob.glob(f'{CACHE}/*.json'):
    tk,d=os.path.basename(f)[:-5].rsplit('_',1)
    if (tk,d) not in gap: continue                      # seulement les ticker-jours du fichier gappers
    data=json.load(open(f))
    if not data or len(data)<5: continue
    for b in data:
        rows.append((tk,d,b['t'],b['o'],b['h'],b['l'],b['c'],b['v']))
df=pd.DataFrame(rows,columns=['ticker','date','t','o','h','l','c','v'])
df['t']=pd.to_datetime(df['t'], utc=True); df['et']=df['t'].dt.tz_convert('America/New_York')  # utc=True: gere EST/EDT mixtes
hm=df['et'].dt.hour*60+df['et'].dt.minute
df=df[(hm>=240)&(hm<990)].copy()  # 04:00-16:30 (indicateurs ancrés PM 04:00 ; trading 08:00-16:30)
df['datetime']=df['et'].dt.strftime('%H:%M')
df=df.sort_values(['ticker','date','t']).reset_index(drop=True)
ntj=df.groupby(['ticker','date']).ngroups
print(f'{len(df):,} bougies, {ntj} ticker-jours')

# ---------- 2) controles qualite ----------
n0=len(df)
df=df[(df[['o','h','l','c']]>0).all(axis=1)]            # prix > 0
df=df[(df['h']>=df['l'])&(df['h']>=df['c'])&(df['l']<=df['c'])]  # OHLC coherent
print(f'controle qualite : {n0-len(df)} bougies rejetees (prix impossibles/incoherents)')

# ---------- 3) indicateurs (vectorises par ticker-jour) ----------
key=[df['ticker'],df['date']]; g=df.groupby(['ticker','date'])
tp=(df.h+df.l+df.c)/3
# VWAP + bandes 2 sigma (ponderees volume, cumulatives)
cpv=(tp*df.v).groupby(key).cumsum(); cvv=df.v.groupby(key).cumsum()
cpv2=(tp*tp*df.v).groupby(key).cumsum()
df['vwap']=cpv/cvv
var=(cpv2/cvv-df['vwap']**2).clip(lower=0)
sd=np.sqrt(var)
df['vwap_up']=df['vwap']+2*sd; df['vwap_dn']=df['vwap']-2*sd
# EMA
for p in (9,20,200): df[f'ema{p}']=g['c'].transform(lambda s,p=p:s.ewm(span=p,adjust=False).mean())
# MACD
e12=g['c'].transform(lambda s:s.ewm(span=12,adjust=False).mean())
e26=g['c'].transform(lambda s:s.ewm(span=26,adjust=False).mean())
df['macd']=e12-e26
df['macd_sig']=df.groupby(['ticker','date'])['macd'].transform(lambda s:s.ewm(span=9,adjust=False).mean())
df['macd_hist']=df['macd']-df['macd_sig']
# Momentum periode 80 (close - close d'il y a 80 bougies)
df['mom80']=g['c'].transform(lambda s:s-s.shift(80))
# Volume
df['cumvol']=df.v.groupby(key).cumsum()
df['vol_sma5']=g['v'].transform(lambda s:s.rolling(5).mean().shift(1))
# RVOL time-of-day : cumvol(T) aujourd'hui / profil moyen a T sur 14 jours (rvol_cache)
RCACHE=f'{R}/rvol_cache'; _bc={}
def baseline(tk,d):
    if (tk,d) not in _bc:
        p=f'{RCACHE}/{tk}_{d}.json'
        _bc[(tk,d)]=json.load(open(p)) if os.path.exists(p) else None
    return _bc[(tk,d)]
def rvol_at(tk,d,cv,m):
    b=baseline(tk,d)
    if not b: return 0.0
    grid=b['grid']; base=b['base']
    j=min(max((m-grid[0])//(grid[1]-grid[0]),0),len(base)-1)
    return round(cv/base[j],3) if base[j]>0 else 0.0
mday=df['datetime'].str.slice(0,2).astype(int)*60+df['datetime'].str.slice(3,5).astype(int)
df['rvol']=[rvol_at(tk,d,cv,m) for tk,d,cv,m in zip(df['ticker'],df['date'],df['cumvol'],mday)]
# Volatilite
prev_c=g['c'].shift(1)
tr=np.maximum(df.h-df.l, np.maximum((df.h-prev_c).abs(),(df.l-prev_c).abs()))
df['atr14']=tr.groupby(key).transform(lambda s:s.rolling(14).mean())
# Session
df['hod']=df.h.groupby(key).cummax(); df['lod']=df.l.groupby(key).cummin()
# Perf
df['prev_close']=[gap.get((tk,d),{}).get('prev_close') for tk,d in zip(df['ticker'],df['date'])]
df['dayopen']=g['o'].transform('first')
df['perf_close_pct']=(df['c']-df['prev_close'])/df['prev_close']*100
df['perf_open_pct']=(df['c']-df['dayopen'])/df['dayopen']*100
# Forme de bougie
rng=(df.h-df.l).replace(0,np.nan)
df['range_pct']=(df.h-df.l)/df.c*100
df['body_pct']=(df.c-df.o).abs()/df.c*100
df['upwick_pct']=(df.h-df[['o','c']].max(axis=1))/df.c*100

# arrondi + sortie
for col in df.select_dtypes('float').columns: df[col]=df[col].round(4)
df=df.drop(columns=['t','et'])
df.to_parquet(OUT,index=False)
print(f'\\n-> {OUT}')
print(f'{len(df):,} lignes, {len(df.columns)} colonnes')
print('colonnes:', list(df.columns))
