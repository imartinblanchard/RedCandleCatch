#!/usr/bin/env python3
"""
MOTEUR de backtest unique (source de verite).

Lit la table candles.parquet (indicateurs deja calcules) et applique N'IMPORTE
QUELLE strategie de la meme facon :
  - parcours point-in-time (a la bougie i, la strategie ne voit que 0..i)
  - une position a la fois par ticker-jour
  - slippage a l'entree ET a la sortie
  - stop / target geres par le moteur ; sorties custom par la strategie
  - metriques honnetes identiques pour toutes les strategies

Une strategie = un dict :
  { 'name', 'window':((7,0),(10,0)), 'slippage':0.003,
    'check_entry': fn(g,i) -> {'entry','stop', 'target'?, ...meta} | None,
    'check_exit':  fn(g,i,pos) -> {'price','reason'} | None   (optionnel) }
"""
import numpy as np, pandas as pd
from statistics import mean, median

def load_table(path):
    return pd.read_parquet(path)

# --------------------------------------------------------------------------
def run(df, strat):
    """Applique une strategie sur toute la table. Retourne la liste des trades."""
    slip = strat.get('slippage', 0.003)
    (ws_h,ws_m),(we_h,we_m) = strat.get('window', ((7,0),(10,0)))
    ws, we = ws_h*60+ws_m, we_h*60+we_m
    check_entry = strat['check_entry']; check_exit = strat.get('check_exit')
    trades=[]
    for (tk,date), g in df.groupby(['ticker','date'], sort=False):
        g = g.reset_index(drop=True)
        mins = g['datetime'].str.slice(0,2).astype(int)*60 + g['datetime'].str.slice(3,5).astype(int)
        pos=None; n=len(g)
        for i in range(n):
            if pos is None:
                if not (ws <= mins.iat[i] < we): continue
                sig = check_entry(g, i)
                if sig:
                    pos = {'entry': sig['entry']*(1+slip),   # fill legerement au-dessus (slippage)
                           'stop': sig.get('stop'), 'target': sig.get('target'),
                           'i0': i, 'meta': sig, 'erow': g.iloc[i]}
            else:
                row = g.iloc[i]; ex=None
                if pos['stop'] is not None and row.l <= pos['stop']:
                    ex = {'price': pos['stop'], 'reason': 'STOP'}
                elif pos['target'] is not None and row.h >= pos['target']:
                    ex = {'price': pos['target'], 'reason': 'TP'}
                elif check_exit:
                    ce = check_exit(g, i, pos)
                    if ce: ex = ce
                if ex:
                    trades.append(_close(tk,date,pos,ex['price']*(1-slip),ex['reason'],g,i))
                    pos=None
        if pos is not None:                               # backstop fin de fenetre
            trades.append(_close(tk,date,pos,g.iloc[n-1].c*(1-slip),'EOD',g,n-1))
    return trades

def _close(tk,date,pos,exit_price,reason,g,i):
    e=pos['entry']; r=pos['erow']
    t={'ticker':tk,'date':date,'entry':round(e,4),'exit':round(exit_price,4),
       'pnl_pct':(exit_price-e)/e*100,'reason':reason,'stop':pos['stop'],
       'entry_time':r.datetime,'exit_time':g.iloc[i].datetime}
    # caracteristiques a l'ENTREE (pour analyser gagnants vs perdants)
    t['f_perf']=r.perf_close_pct; t['f_rvol']=r.rvol; t['f_cumvol']=r.cumvol
    t['f_atr']=r.atr14; t['f_machist']=r.macd_hist; t['f_range']=r.range_pct
    t['f_vwapdist']=(r.c-r.vwap)/r.vwap*100 if r.vwap else 0
    t['f_ema9dist']=(r.c-r.ema9)/r.ema9*100 if r.ema9 else 0
    t['f_price']=r.c; t['f_hour']=int(r.datetime[:2])
    return t

# --------------------------------------------------------------------------
def metrics(trades, risk=0.01, maxpos=0.20, start=10000.0):
    """Metriques HONNETES : per-trade + compte compose (sizing risque) + robustesse."""
    if not trades:
        return {'n':0}
    pnls=[t['pnl_pct'] for t in trades]
    wins=[p for p in pnls if p>0]; losses=[p for p in pnls if p<=0]
    # equity NON-COMPOSEE (mise fixe) : evite l'explosion du compounding sur un
    # edge in-sample. Mise = risque fixe (% du capital de DEPART), plafonnee a maxpos.
    ts=sorted(trades, key=lambda t:(t['date'],t['entry_time']))
    acct=start; peak=start; dd=0.0
    for t in ts:
        sd = (t['entry']-t['stop'])/t['entry'] if t.get('stop') else 0.05
        sd = max(sd, 0.005)                              # plancher pour eviter division ~0
        pos = min(start*risk/sd, start*maxpos)           # mise FIXE (capital de depart)
        acct += pos*(t['pnl_pct']/100)
        peak=max(peak,acct); dd=max(dd,(peak-acct)/peak if peak>0 else 0)
    # robustesse : moyenne sans les 10 meilleurs (detecte la loterie)
    trimmed = sorted(pnls, reverse=True)[10:]
    return {
        'n': len(trades),
        'win%': round(100*len(wins)/len(trades),0),
        'moy%': round(mean(pnls),2),
        'med%': round(median(pnls),2),
        'gain_moy': round(mean(wins),1) if wins else 0,
        'perte_moy': round(mean(losses),1) if losses else 0,
        'compte%': round((acct/start-1)*100,0),
        'maxDD%': round(dd*100,1),
        'moy_sans_top10%': round(mean(trimmed),2) if trimmed else 0,
    }
