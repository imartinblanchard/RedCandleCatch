#!/usr/bin/env python3
"""
Definitions de STRATEGIES (config) pour le moteur.

Chaque strategie fournit check_entry(g,i) et (optionnel) check_exit(g,i,pos),
qui lisent les colonnes DEJA calculees de la table. Ajouter une strategie =
ajouter une entree dans le dict STRATEGIES, pas un nouveau script.
g = les bougies du ticker-jour (DataFrame) ; i = l'index de la bougie courante.
Point-in-time : on n'indexe JAMAIS au-dela de i.
"""
import numpy as np

# ------------------------------------------------------------------ helpers
def _micro_pullback(g, i, max_pb=5):
    """Impulsion (>=1 bougie verte) -> repli (1 a max_pb bougies rouges, volume plus
    calme) -> cassure du sommet du repli en i. Retourne (pb_high, pb_low, imp_vol)."""
    if i < 2: return None
    # repli = bougies rouges consecutives finissant en i-1 (jusqu'a max_pb)
    k=0
    while k<max_pb and (i-1-k)>=0 and g.iloc[i-1-k].c < g.iloc[i-1-k].o: k+=1
    if k<1: return None
    pb=[g.iloc[i-1-j] for j in range(k)]
    # impulsion = bougies vertes consecutives juste avant le repli (au moins 1)
    j0=i-1-k
    if j0<0 or not (g.iloc[j0].c > g.iloc[j0].o): return None
    m=0
    while (j0-m)>=0 and g.iloc[j0-m].c > g.iloc[j0-m].o: m+=1
    imp=[g.iloc[j0-j] for j in range(m)]
    imp_vol=np.mean([x.v for x in imp]); pb_vol=np.mean([x.v for x in pb])
    if not (imp_vol>0 and pb_vol < imp_vol): return None   # repli plus calme que l'impulsion
    return max(x.h for x in pb), min(x.l for x in pb), imp_vol

def _topping_tail(r):
    return r.range_pct>0 and r.upwick_pct > 2*r.body_pct and r.upwick_pct > 0.6*r.range_pct

# ------------------------------------------------------------------ strat 1
def entry_micropullback(g, i):
    r=g.iloc[i]
    if not (r.perf_close_pct>=10 and 2<=r.c<=20 and r.c>r.vwap and r.c>r.ema9
            and r.macd>0 and r.macd>r.macd_sig and r.rvol>=5):
        return None
    mp=_micro_pullback(g,i)
    if not mp: return None
    pb_high,pb_low,imp_vol=mp
    if g.iloc[i].h < pb_high or pb_high<=pb_low: return None   # trigger = cassure du high
    return {'entry':pb_high,'stop':pb_low,'imp_vol':imp_vol}

def exit_micropullback(g, i, pos):
    r=g.iloc[i]; imp_vol=pos['meta']['imp_vol']
    if r.c<r.o and r.v>imp_vol:      return {'price':r.c,'reason':'REDVOL'}
    if r.macd<r.macd_sig:            return {'price':r.c,'reason':'MACD'}
    if r.c<r.ema9:                   return {'price':r.c,'reason':'EMA9'}
    if _topping_tail(r):             return {'price':r.c,'reason':'TAIL'}
    return None

# ------------------------------------------------------------------ strat 2
def entry_vwap_band(g, i):
    """Repli sur VWAP + rebond vert (stop -5%, cible = bande +2σ)."""
    r=g.iloc[i]
    if not (r.perf_close_pct>=10 and 2<=r.c<=20 and r.c>r.vwap and r.c>r.ema9
            and r.macd>0 and r.rvol>=5): return None
    if not (r.l<=r.vwap*1.003 and r.c>=r.o and r.c>r.vwap): return None
    return {'entry':r.c,'stop':round(r.c*0.95,4)}

def exit_vwap_band(g, i, pos):
    r=g.iloc[i]
    if r.h>=r.vwap_up:   return {'price':r.vwap_up,'reason':'TP_BAND'}   # bande +2σ (mobile)
    return None

# ------------------------------------------------------------------ strat 3 : signal +10% -> sortie horaire
def entry_signal10(g, i):
    """Entree DES que le stock touche +10% vs veille (le signal du scanner)."""
    r=g.iloc[i]
    if r.perf_close_pct>=10 and 2<=r.c<=20:
        return {'entry':1.10*r.prev_close}          # fill au niveau +10%
    return None

def entry_signal10_stop(g, i):
    r=g.iloc[i]
    if r.perf_close_pct>=10 and 2<=r.c<=20:
        e=1.10*r.prev_close
        return {'entry':e,'stop':round(e*0.90,4)}   # stop -10%
    return None

def entry_ross(g, i):
    """Ross Micro-Pullback FIDELE (fill realiste) : stock 'in play' (au-dessus VWAP+EMA9,
    MACD positif, RVOL>=5, +10%, prix 2-20) -> impulsion -> 1-2 rouges legers ->
    cassure du sommet du repli. Fill au pire prix si la bougie ouvre au-dessus (gap)."""
    r=g.iloc[i]
    if not (r.perf_close_pct>=10 and 0.25<=r.c<=20 and r.c>r.vwap and r.c>r.ema9
            and r.macd>0 and r.macd>r.macd_sig and r.rvol>=3):
        return None
    mp=_micro_pullback(g,i)
    if not mp: return None
    pb_high,pb_low,imp_vol=mp
    if r.h < pb_high or pb_high<=pb_low: return None      # trigger = cassure du sommet du repli
    fill = r.o if r.o>=pb_high else pb_high               # gap par-dessus -> pire prix
    return {'entry':fill,'stop':pb_low,'imp_vol':imp_vol}

def entry_signal10_realistic(g, i):
    """Entree REALISTE : watchlist des +7%, ordre stop au repos a +10%.
    - il faut qu'un bar PRECEDENT ait atteint +7% (sinon gap instantane non-watchlistable)
    - trigger quand la bougie touche +10% (h >= niveau)
    - fill: si la bougie a OUVERT au-dessus de +10% (gap par-dessus) -> pire prix (open) ;
      sinon le stop est rempli proprement a +10%."""
    r=g.iloc[i]
    if not (2<=r.c<=20): return None
    lvl=1.10*r.prev_close
    if r.h < lvl: return None                                  # +10% pas encore touche
    if i==0 or not (g['perf_close_pct'].iloc[:i] >= 7).any(): return None   # arme a +7% avant
    fill = r.o if r.o >= lvl else lvl                          # gap par-dessus => fill au pire
    return {'entry':fill}

def _exit_at(hhmm):
    def fn(g, i, pos):
        r=g.iloc[i]
        return {'price':r.o,'reason':'TIME'} if r.datetime>=hhmm else None
    return fn

# ------------------------------------------------------------------ registre
STRATEGIES = {
    'signal10_930': {
        'name':'Signal +10% -> sortie 9:30', 'window':((4,0),(9,30)), 'slippage':0.0015,
        'check_entry':entry_signal10, 'check_exit':_exit_at('09:30'),
    },
    'ross': {
        'name':'Ross Micro-Pullback fidele (fenetre open, sorties Ross)', 'window':((7,0),(9,45)),
        'slippage':0.0015, 'check_entry':entry_ross, 'check_exit':exit_micropullback,
    },
    'signal10r_930': {
        'name':'Signal +10% REALISTE (arme 7%) -> sortie 9:30', 'window':((4,0),(9,30)),
        'slippage':0.0015, 'check_entry':entry_signal10_realistic, 'check_exit':_exit_at('09:30'),
    },
    'signal10_930_stop': {
        'name':'Signal +10% + stop-10% -> 9:30', 'window':((4,0),(9,30)), 'slippage':0.0015,
        'check_entry':entry_signal10_stop, 'check_exit':_exit_at('09:30'),
    },
    'micro_pullback': {
        'name':'Micro Pullback (Ross)', 'window':((7,0),(10,0)), 'slippage':0.003,
        'check_entry':entry_micropullback, 'check_exit':exit_micropullback,
    },
    'vwap_band': {
        'name':'Repli VWAP + bande 2σ', 'window':((7,0),(10,0)), 'slippage':0.003,
        'check_entry':entry_vwap_band, 'check_exit':exit_vwap_band,
    },
}
