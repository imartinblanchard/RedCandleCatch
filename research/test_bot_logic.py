#!/usr/bin/env python3
"""Test unitaire de la machine à états two-phase (mode PAPER, sans IBKR)."""
import sys; sys.path.insert(0,'/home/martin/dev/stock-journal-long')
from datetime import datetime
from zoneinfo import ZoneInfo
import bot.redcandlecatch_terminator as w
ET=ZoneInfo('America/New_York')

trades=[]
w.append_journal = lambda row: trades.append(row)   # capture au lieu d'écrire le CSV
w.save_state = lambda s: None
w.load_state = lambda: {}

term = w.RedCandleCatchTerminator(broker=None, live=False)
term.gap_ok['TEST'] = 60.0

def bar(hm, o,h,l,c):
    t=datetime(2026,9,3,int(hm[:2]),int(hm[3:]),tzinfo=ET)
    return {'o':o,'h':h,'l':l,'c':c,'v':1000,'t':t}

# Scénario : entrée dip -5%, montée à +5% (activation), sommet, puis retombée (trail 2%)
seq=[
    bar('09:30', 5.00,5.02,4.95,5.00),
    bar('09:31', 5.00,5.01,4.65,4.70),   # DIP -6% -> entrée @ 4.70 (stop 4.23)
    bar('09:32', 4.70,4.80,4.68,4.78),   #
    bar('09:33', 4.78,5.10,4.75,5.05),   # high 5.10 -> ACTIVATION (seuil +5% = 4.935)
    bar('09:34', 5.05,5.30,5.02,5.25),   # sommet 5.30 -> trail = 5.30*0.98 = 5.194
    bar('09:35', 5.25,5.26,5.00,5.02),   # low 5.00 <= 5.194 -> SORTIE TRAIL @ 5.194
    bar('09:36', 5.02,5.05,4.98,5.00),
]
print("Déroulé (mode paper) :")
for k in range(2,len(seq)):
    bars=seq[:k+1]                       # bars[-1]=en formation, bars[-2]=dernière clôturée
    t=bars[-1]['t']
    if 'TEST' in term.state:
        term._manage('TEST', bars, t)
        p=term.state.get('TEST',{})
        print(f"  {bars[-2]['t']:%H:%M} clôt {bars[-2]['c']:.2f}  activated={p.get('activated')}  {'(sortie)' if 'TEST' not in term.state else ''}")
    else:
        term._maybe_enter('TEST', bars)
        if 'TEST' in term.state:
            print(f"  {bars[-2]['t']:%H:%M} ENTRÉE @ {term.state['TEST']['entry']:.2f}")

print("\nTrade journalisé :")
for tr in trades:
    print(f"  entrée {tr['entry']}  sortie {tr['exit']}  raison {tr['reason']}  pnl {tr['pnl_pct']}%  mfe {tr['mfe_pct']}%")
print(f"\nAttendu : entrée 4.70, sortie ~5.19 (TRAIL), pnl ~+10% -> {'✅ OK' if trades and trades[0]['reason']=='TRAIL' and trades[0]['pnl_pct']>8 else '❌ PROBLÈME'}")
