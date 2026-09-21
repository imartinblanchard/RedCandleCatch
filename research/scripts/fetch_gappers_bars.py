#!/usr/bin/env python3
"""Recupere les bougies 1-min SIP (adjustment=all) pour tous les gappers.
Robuste : retry sur echec transitoire (429/500/timeout), n'ecrit PAS de fichier
vide sur echec -> il sera re-essaye au prochain run. Ecrit vide seulement si
Alpaca renvoie vraiment 200-sans-bougie (vrai 'sans data')."""
import sys, json, os, time
from datetime import datetime
from zoneinfo import ZoneInfo
import requests
sys.path.insert(0, '/home/martin/dev/stock-journal-long')
from bot import config as c

ET=ZoneInfo('America/New_York')
H={'APCA-API-KEY-ID':c.ALPACA_API_KEY_ID,'APCA-API-SECRET-KEY':c.ALPACA_API_SECRET_KEY}
CACHE='/home/martin/dev/stock-journal-long/research/bars_cache'
GAPFILE=sys.argv[1] if len(sys.argv)>1 else '/home/martin/dev/stock-journal-long/research/gappers.json'
gappers=json.load(open(GAPFILE))

def fetch(tk,date,retries=3):
    cf=os.path.join(CACHE,f"{tk}_{date}.json")
    if os.path.exists(cf) and len(json.load(open(cf)))>=5: return 'cached'
    for attempt in range(retries):
        try:
            r=requests.get(f"{c.ALPACA_DATA_URL}/v2/stocks/{tk}/bars",headers=H,timeout=25,
                           params={'timeframe':'1Min','start':f"{date}T08:00:00Z",'end':f"{date}T21:00:00Z",
                                   'feed':'sip','adjustment':'all','limit':10000})
            if r.status_code==200:
                bars=r.json().get('bars') or []
                out=[{'t':datetime.fromisoformat(b['t'].replace('Z','+00:00')).astimezone(ET).isoformat(),
                      'o':b['o'],'h':b['h'],'l':b['l'],'c':b['c'],'v':b['v']} for b in bars]
                json.dump(out,open(cf,'w'))
                return 'fetched' if out else 'empty'   # 200-vide = vrai sans-data
            # non-200 (429/500...) -> transitoire
        except Exception:
            pass
        time.sleep(1.5*(attempt+1))                     # backoff
    return 'failed'                                     # pas de fichier ecrit -> re-essai au prochain run

n=len(gappers); c_=dict(fetched=0,cached=0,empty=0,failed=0)
for i,g in enumerate(gappers,1):
    c_[fetch(g['ticker'],g['date'])]+=1
    if i%100==0: print(f"  ...{i}/{n} {c_}",flush=True)
print(f"TERMINE: {c_}")
if c_['failed']: print(f"⚠️ {c_['failed']} echecs transitoires -> relance le script pour les recuperer")
