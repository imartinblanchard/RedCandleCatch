#!/usr/bin/env python3
"""Comparer les stops A DRAWDOWN EGAL (~7%) : on ajuste le sizing de chacun pour viser 7% DD."""
import csv, json, os, sys, math
from datetime import datetime
from zoneinfo import ZoneInfo
sys.path.insert(0, '/home/martin/dev/stock-journal-long')
from bot.indicators import vwap
from bot import strategy as S

ET = ZoneInfo('America/New_York')
CACHE='/home/martin/dev/stock-journal-long/research/bars_cache'
TARGET_DD = 7.0

def load(tk,d):
    cf=os.path.join(CACHE,f"{tk}_{d}.json")
    if not os.path.exists(cf): return []
    return [{'t':datetime.fromisoformat(b['t']),'o':b['o'],'h':b['h'],'l':b['l'],'c':b['c'],'v':b['v']}
            for b in json.load(open(cf))]

def bands_and_sd(bars,k):
    up=[];sdl=[];cv=cpv=cpv2=0.0
    for b in bars:
        tp=(b['h']+b['l']+b['c'])/3;cv+=b['v'];cpv+=tp*b['v'];cpv2+=tp*tp*b['v']
        vw=cpv/cv if cv>0 else b['c']; sd=math.sqrt(max(0.0,cpv2/cv-vw*vw)) if cv>0 else 0
        up.append(vw+k*sd);sdl.append(sd)
    return up,sdl

rows=list(csv.DictReader(open('/home/martin/dev/stock-journal-long/data/long-checklist.csv')))
setups=[]
for r in rows:
    bars=load(r['Ticker'].strip(), r['Date'].strip())
    if not bars: continue
    pm=[b for b in bars if (b['t'].hour,b['t'].minute)<(9,30)]
    rth=[b for b in bars if (b['t'].hour,b['t'].minute)>=(9,30)]
    if len(pm)<S.MIN_ABOVE+2 or not rth: continue
    for i in range(S.MIN_ABOVE+2, len(pm)+1):
        sig=S.check_entry(pm[:i])
        if sig:
            band,sdl=bands_and_sd(pm,S.BAND_K)
            setups.append((r['Date'].strip(),pm,rth,i-1,sig['entry'],vwap(pm[:i])[-1],sdl[i-1],band))
            break
setups.sort(key=lambda x:x[0])

def stop_price(m,pm,i,entry,vw,sd):
    if m=='fixe 3%': return entry*0.97
    if m=='fixe 5%': return entry*0.95
    if m=='ATR x1.5':
        rng=[pm[j]['h']-pm[j]['l'] for j in range(max(0,i-13),i+1)];return entry-1.5*sum(rng)/len(rng)
    if m=='bande basse -2σ': return vw-2*sd
    return entry*0.95

def trades_for(m):
    out=[]
    for date,pm,rth,idx,entry,vw,sd,band in setups:
        stop=stop_price(m,pm,idx,entry,vw,sd); dist=(entry-stop)/entry
        if dist<=0.002: continue
        res=None
        for j in range(idx+1,len(pm)):
            b=pm[j]
            if b['l']<=stop: res=-dist*100; break
            if b['h']>=band[j]: res=(band[j]-entry)/entry*100; break
        if res is None: res=(rth[0]['o']-entry)/entry*100
        out.append((res, dist))          # (pnl%, dist fraction)
    return out

def run(trades, risk, maxpos=0.30, start=100.0):
    acct=start;peak=start;dd=0;wins=0
    for pnl,dist in trades:
        pos=min(acct*risk/dist, acct*maxpos)
        acct+=pos*(pnl/100);
        if pnl>0: wins+=1
        peak=max(peak,acct);dd=max(dd,(peak-acct)/peak)
    return (acct/start-1)*100, dd*100, 100*wins//len(trades)

def risk_for_dd(trades, target):
    lo,hi=0.001,0.20
    for _ in range(40):
        mid=(lo+hi)/2; _,dd,_=run(trades,mid)
        if dd<target: lo=mid
        else: hi=mid
    return lo

print(f"Comparaison a DRAWDOWN EGAL (~{TARGET_DD}%), plafond position 30%\n")
print(f"{'STOP':16} {'risque calibré':>14} {'WIN':>4} {'RENDEMENT':>10} {'DD réel':>8}")
print("-"*58)
for m in ['bande basse -2σ','pullback low' if False else 'ATR x1.5','fixe 5%','fixe 3%']:
    tr=trades_for(m)
    rk=risk_for_dd(tr,TARGET_DD)
    ret,dd,wr=run(tr,rk)
    print(f"{m:16} {rk*100:>13.2f}% {wr:>3}% {ret:>+9.0f}% {dd:>7.1f}%")
# bande basse explicit
tr=trades_for('bande basse -2σ'); rk=risk_for_dd(tr,TARGET_DD); ret,dd,wr=run(tr,rk)
print(f"\n-> BANDE BASSE calibrée a {TARGET_DD}% DD : risque {rk*100:.2f}%/trade, "
      f"win {wr}%, rendement {ret:+.0f}%")
