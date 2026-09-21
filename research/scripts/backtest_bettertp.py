#!/usr/bin/env python3
"""Combien de trades pourraient sortir PLUS HAUT ? MFE apres la bande + test de TP alternatifs."""
import csv, json, os, sys, math
from datetime import datetime
from zoneinfo import ZoneInfo
sys.path.insert(0, '/home/martin/dev/stock-journal-long')
from bot.indicators import vwap
from bot import strategy as S

ET = ZoneInfo('America/New_York')
CACHE='/home/martin/dev/stock-journal-long/research/bars_cache'
STOP=0.05

def load(tk,d):
    cf=os.path.join(CACHE,f"{tk}_{d}.json")
    if not os.path.exists(cf): return []
    return [{'t':datetime.fromisoformat(b['t']),'o':b['o'],'h':b['h'],'l':b['l'],'c':b['c'],'v':b['v']}
            for b in json.load(open(cf))]

def band_k(bars,k):
    up=[];cv=cpv=cpv2=0.0
    for b in bars:
        tp=(b['h']+b['l']+b['c'])/3;cv+=b['v'];cpv+=tp*b['v'];cpv2+=tp*tp*b['v']
        vw=cpv/cv if cv>0 else b['c'];sd=math.sqrt(max(0.0,cpv2/cv-vw*vw)) if cv>0 else 0
        up.append(vw+k*sd)
    return up

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
        if sig: setups.append((pm,rth,i-1,sig['entry'])); break
print(f"{len(setups)} trades\n")

# --- 1. Combien laissent de l'argent sur la table apres la bande k=2 ? ---
band_hits=0; ran_higher=0; extras=[]
for pm,rth,idx,entry in setups:
    b2=band_k(pm,2); exit_j=None
    stop=entry*(1-STOP)
    for j in range(idx+1,len(pm)):
        if pm[j]['l']<=stop: break
        if pm[j]['h']>=b2[j]: exit_j=j; break
    if exit_j is None: continue
    band_hits+=1
    exit_pct=(b2[exit_j]-entry)/entry*100
    peak_after=max((pm[j]['h'] for j in range(exit_j,len(pm))), default=b2[exit_j])
    peak_pct=(peak_after-entry)/entry*100
    extra=peak_pct-exit_pct
    if extra>0.5: ran_higher+=1
    extras.append(extra)

print(f"Trades qui touchent la bande +2σ (TP actuel) : {band_hits}")
print(f"  -> qui montent ENCORE apres la sortie      : {ran_higher} ({100*ran_higher//band_hits}%)")
print(f"  -> gain moyen laissé sur la table          : +{sum(extras)/len(extras):.1f}%")
print(f"  -> max laissé sur un trade                 : +{max(extras):.1f}%\n")

# --- 2. Test de TP alternatifs (memes entrees, stop -5%) ---
def exit_variant(pm,rth,idx,entry,mode):
    stop=entry*(1-STOP)
    if mode.startswith('bande k='):
        k=float(mode.split('=')[1]); bd=band_k(pm,k)
        for j in range(idx+1,len(pm)):
            if pm[j]['l']<=stop: return -STOP*100
            if pm[j]['h']>=bd[j]: return (bd[j]-entry)/entry*100
        return (rth[0]['o']-entry)/entry*100
    if mode.startswith('bande2+trail'):
        trail=float(mode.split()[1])/100; b2=band_k(pm,2); armed=False; peak=entry
        for j in range(idx+1,len(pm)):
            b=pm[j]
            if not armed:
                if b['l']<=stop: return -STOP*100
                if b['h']>=b2[j]: armed=True; peak=b['h']   # arme, mais on trail des la PROCHAINE bougie
                continue
            peak=max(peak,b['h'])
            if b['l']<=peak*(1-trail): return (peak*(1-trail)-entry)/entry*100
        return (rth[0]['o']-entry)/entry*100

print(f"{'TP / SORTIE':18} {'WIN':>4} {'P&L moy':>9} {'CUMULE':>8}")
print("-"*44)
for mode in ['bande k=2','bande k=2.5','bande k=3','bande2+trail 5','bande2+trail 8','bande2+trail 12']:
    r=[exit_variant(pm,rth,idx,entry,mode) for pm,rth,idx,entry in setups]
    wins=sum(1 for p in r if p>0)
    print(f"{mode:18} {100*wins//len(r):>3}% {sum(r)/len(r):>+7.2f}% {sum(r):>+7.1f}%")
