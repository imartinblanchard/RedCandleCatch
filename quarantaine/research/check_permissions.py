#!/usr/bin/env python3
"""Vérifie si IBKR autorise l'OUVERTURE de positions (sans passer d'ordre réel).

Utilise whatIfOrder : IBKR évalue l'ordre et renvoie l'erreur 201 s'il le refuse,
mais RIEN n'est exécuté. À relancer après tout changement de compte (dépôt, levée
de restriction) pour voir immédiatement si le blocage small-cap est levé.

    python research/check_permissions.py            # tickers du fichier d'éligibles + AAPL
    python research/check_permissions.py ATTT PCLA  # tickers précis
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ib_insync import MarketOrder
from execution.ibkr_broker import IBKRBroker
from bot import eligible

rejets = []

def main():
    tickers = sys.argv[1:]
    if not tickers:
        tickers = list(eligible.load()) or []
        tickers.append('AAPL')                      # témoin large-cap
    br = IBKRBroker(client_id=96)
    if not br.connect():
        print("connexion IBKR KO (Gateway lancé ?)"); return
    ib = br.ib

    def on_err(reqId, code, msg, contract):
        if code == 201:
            sym = getattr(contract, 'symbol', '?') if contract else '?'
            rejets.append((sym, msg))
    ib.errorEvent += on_err

    cap = br.account_summary().get('NetLiquidation')
    print(f"Compte : NetLiquidation = {cap}\n")
    print(f"Test d'OUVERTURE (1 action, MKT) — aucun ordre réel n'est passé :\n")

    for tk in tickers:
        before = len(rejets)
        c = br._contract(tk)
        if c is None:
            print(f"  {tk:6} contrat introuvable"); continue
        o = MarketOrder('BUY', 1); o.tif = 'DAY'
        try:
            ib.whatIfOrder(c, o)
        except Exception:
            pass
        ib.sleep(2)
        new = rejets[before:]
        if new:
            print(f"  {tk:6} ❌ REFUSÉ : {new[-1][1][:110]}")
        else:
            print(f"  {tk:6} ✅ AUTORISÉ (l'ouverture passerait)")
    br.disconnect()
    print("\n(✅ partout = le bot peut trader ; ❌ small caps = restriction toujours active)")

if __name__ == '__main__':
    main()
