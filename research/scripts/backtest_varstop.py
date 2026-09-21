#!/usr/bin/env python3
"""Stops variables selon differents parametres. Metrique cle = R-multiple (sizing-independant)
+ rendement compte compose (risque 1%, plafond 20%)."""
import csv, json, os, sys, math
from datetime import datetime
from zoneinfo import ZoneInfo
sys.path.insert(0, '/home/martin/dev/stock-journal-long')
from bot.indicators import vwap
from bot import strategy as S

ET = ZoneInfo('America/New_York')
CACHE='/home/martin/dev/stock-journal-long/research/bars_cache'

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

# --- collecte les entrees (strat 7 filtres, MEMES pour tous les stops) ---
rows=list(csv.DictReader(open('/home/martin/dev/stock-journal-long/data/long-checklist.csv')))
setups=[]  # (date, pm, rth, idx, entry, vw_i, sd_i, band_array)
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
            setups.append((r['Date'].strip(), pm, rth, i-1, sig['entry'], vwap(pm[:i])[-1], sdl[i-1], band))
            break
setups.sort(key=lambda x:x[0])
print(f"{len(setups)} entrees (identiques pour chaque methode de stop)\n")

def stop_price(method, pm, i, entry, vw, sd):
    if method=='fixe 5%':   return entry*0.95
    if method=='fixe 3%':   return entry*0.97
    if method=='fixe 7%':   return entry*0.93
    if method=='VWAP':      return vw*0.999
    if method=='pullback low': return min(b['l'] for b in pm[max(0,i-4):i+1])
    if method=='ATR x1.5':
        rng=[pm[j]['h']-pm[j]['l'] for j in range(max(0,i-13),i+1)]; atr=sum(rng)/len(rng)
        return entry-1.5*atr
    if method=='bande basse -2σ': return vw-2*sd
    return entry*0.95

def sim(method):
    trades=[]  # (pnl_pct, R)
    for date,pm,rth,idx,entry,vw,sd,band in setups:
        stop=stop_price(method,pm,idx,entry,vw,sd)
        dist=(entry-stop)/entry
        if dist<=0.002: continue          # stop trop serre/invalide -> skip
        res=None
        for j in range(idx+1,len(pm)):
            b=pm[j]
            if b['l']<=stop: res=-(entry-stop)/entry*100; break
            if b['h']>=band[j]: res=(band[j]-entry)/entry*100; break
        if res is None: res=(rth[0]['o']-entry)/entry*100
        trades.append((res, res/(dist*100)))   # R = pnl% / dist%
    return trades

def account(trades, risk=0.01, maxpos=0.20, start=100.0):
    acct=start; peak=start; dd=0
    for pnl,R in trades:
        dist=pnl/R/100 if R else 0.05        # retrouve la distance
        pos=min(acct*risk/max(dist,1e-6), acct*maxpos)
        acct+=pos*(pnl/100); peak=max(peak,acct); dd=max(dd,(peak-acct)/peak)
    return (acct/start-1)*100, dd*100

print(f"{'STOP':16} {'N':>3} {'stop%moy':>8} {'WIN':>4} {'R moy':>6} {'R tot':>6} {'compte(1%)':>10} {'DD':>6}")
print("-"*72)
for m in ['fixe 3%','fixe 5%','fixe 7%','VWAP','pullback low','ATR x1.5','bande basse -2σ']:
    tr=sim(m)
    if not tr: print(f"{m:16} 0"); continue
    wins=sum(1 for p,_ in tr if p>0)
    avgdist=sum((p/R) for p,R in tr if R)/len(tr)  # ~ pnl/R = dist% ... approx
    ret,dd=account(tr)
    dists=[ (p/R) for p,R in tr if R]
    avg_stop=sum(abs(d) for d in dists)/len(dists)
    print(f"{m:16} {len(tr):>3} {avg_stop:>7.1f}% {100*wins//len(tr):>3}% "
          f"{sum(R for _,R in tr)/len(tr):>+5.2f} {sum(R for _,R in tr):>+6.1f} {ret:>+9.0f}% {dd:>5.1f}%")
