#!/usr/bin/env python3
"""TP sur la bande supérieure du VWAP (VWAP + k*sigma). Entrée repli VWAP+surge, stop -5%."""
import csv, json, os, sys, math
from datetime import datetime
from zoneinfo import ZoneInfo
sys.path.insert(0, '/home/martin/dev/stock-journal-long')
from bot.indicators import vwap

ET = ZoneInfo('America/New_York')
CACHE = '/home/martin/dev/stock-journal-long/research/bars_cache'
STOP = 0.05; MIN_PM_VOL = 150_000; VWAP_TOL = 0.003; MIN_ABOVE = 3; SURGE = 3

def load(tk, d):
    cf = os.path.join(CACHE, f"{tk}_{d}.json")
    if not os.path.exists(cf): return []
    return [{'t': datetime.fromisoformat(b['t']),'o':b['o'],'h':b['h'],'l':b['l'],'c':b['c'],'v':b['v']}
            for b in json.load(open(cf))]

def vwap_bands(bars, k):
    """Bande supérieure cumulée VWAP + k*sigma (sigma pondéré volume, ancré session)."""
    out=[]; cv=cpv=cpv2=0.0
    for b in bars:
        tp=(b['h']+b['l']+b['c'])/3
        cv+=b['v']; cpv+=tp*b['v']; cpv2+=tp*tp*b['v']
        if cv<=0: out.append(b['c']); continue
        vw=cpv/cv; var=max(0.0, cpv2/cv-vw*vw); sd=math.sqrt(var)
        out.append(vw+k*sd)
    return out

def find_entry(bars):
    pm=[b for b in bars if (b['t'].hour,b['t'].minute)<(9,30)]
    rth=[b for b in bars if (b['t'].hour,b['t'].minute)>=(9,30)]
    if len(pm)<MIN_ABOVE+2 or not rth: return None
    for i in range(MIN_ABOVE,len(pm)):
        seg=pm[:i+1]; vw=vwap(seg); last=seg[-1]
        if sum(b['v'] for b in seg)<MIN_PM_VOL: continue
        prev5=[b['v'] for b in pm[max(0,i-5):i]]; avg5=sum(prev5)/len(prev5) if prev5 else 0
        if avg5 and last['v']<SURGE*avg5: continue
        above=all(seg[j]['c']>vwap(seg[:j+1])[-1] for j in range(i-MIN_ABOVE,i))
        if above and last['l']<=vw[-1]*(1+VWAP_TOL) and last['c']>=last['o'] and last['c']>vw[-1]:
            return last['c'],i,pm,rth
    return None

def exit_band(entry, idx, pm, rth, k):
    stop=entry*(1-STOP); band=vwap_bands(pm,k)
    for j in range(idx+1,len(pm)):
        b=pm[j]
        if b['l']<=stop: return -STOP*100
        if b['h']>=band[j]: return (band[j]-entry)/entry*100   # TP à la bande sup
    return (rth[0]['o']-entry)/entry*100

def exit_trail(entry, idx, pm, rth, trail=0.05):
    peak=entry; hard=entry*(1-STOP)
    for b in pm[idx+1:]:
        eff=max(hard, peak*(1-trail))
        if b['l']<=eff: return (eff-entry)/entry*100
        peak=max(peak,b['h'])
    return (rth[0]['o']-entry)/entry*100

def exit_band_or_trail(entry, idx, pm, rth, k, trail=0.05):
    """Bande sup comme TP, MAIS trailing 5% en protection (le premier touché)."""
    stop=entry*(1-STOP); band=vwap_bands(pm,k); peak=entry
    for j in range(idx+1,len(pm)):
        b=pm[j]; eff=max(stop, peak*(1-trail))
        if b['l']<=eff: return (eff-entry)/entry*100
        if b['h']>=band[j]: return (band[j]-entry)/entry*100
        peak=max(peak,b['h'])
    return (rth[0]['o']-entry)/entry*100

rows=list(csv.DictReader(open('/home/martin/dev/stock-journal-long/data/long-checklist.csv')))
entries=[]
for r in rows:
    bars=load(r['Ticker'].strip(), r['Date'].strip())
    if not bars: continue
    e=find_entry(bars)
    if e: entries.append(e)
print(f"Entrées: {len(entries)} | stop -5% | entrée = repli VWAP + surge 3x\n")
print(f"{'SORTIE':30} {'WIN':>4}  {'P&L moy':>9}  {'CUMULÉ':>8}")
print("-"*58)
def rep(name, fn):
    r=[fn(*e) for e in entries]; wins=sum(1 for p in r if p>0)
    print(f"{name:30} {100*wins//len(r):>3}%  moy {sum(r)/len(r):>+6.2f}%  {sum(r):>+7.1f}%")
rep("Trailing 5% (référence)", exit_trail)
for k in (1,2,3):
    rep(f"TP bande sup k={k}", lambda en,i,pm,rth,k=k: exit_band(en,i,pm,rth,k))
for k in (2,3):
    rep(f"TP bande k={k} + trailing 5%", lambda en,i,pm,rth,k=k: exit_band_or_trail(en,i,pm,rth,k))
