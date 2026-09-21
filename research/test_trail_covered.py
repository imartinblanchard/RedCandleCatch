"""
test_trail_covered.py — confirme que le TRAIL 'percent seul' (variante C) est
ACCEPTÉ par IBKR sur une position DÉTENUE (pas de short-locate qui masque le test).

Flux (compte réel 4001, 1 action) :
  1. achat 1 action (limite marketable)
  2. attend le fill -> position = 1
  3. pose TRAIL percent-seul (trailingPercent, PAS de trailStopPrice) -> statut ?
  4. annule le trail
  5. revend l'action (solde)
Un bloc `finally` solde la position quoi qu'il arrive.

Lancer :
    source .venv/bin/activate
    python research/test_trail_covered.py --symbol FTFT

⚠️ VRAI aller-retour d'1 action sur le compte LIVE 4001.
"""
import argparse
import random
from ib_insync import IB, Stock, Order, MarketOrder


def wait_fill(ib, trade, timeout=15):
    """Attend qu'un ordre soit rempli (ou timeout). Renvoie qty remplie."""
    for _ in range(timeout * 2):
        ib.sleep(0.5)
        if trade.orderStatus.status == 'Filled':
            return trade.orderStatus.filled
    return trade.orderStatus.filled


def position_qty(ib, symbol):
    for p in ib.positions():
        if p.contract.symbol.upper() == symbol.upper():
            return int(p.position)
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--symbol', default='FTFT')
    ap.add_argument('--trail', type=float, default=0.02)
    ap.add_argument('--port', type=int, default=4001)
    args = ap.parse_args()
    sym = args.symbol.upper()

    ib = IB()
    cid = random.randint(40, 3999)
    print(f"Connexion IBKR 127.0.0.1:{args.port} clientId={cid} (LIVE, 1 action)...")
    ib.connect('127.0.0.1', args.port, clientId=cid, timeout=15)

    errs = []
    ib.errorEvent += (lambda reqId, code, msg, *a: errs.append((code, msg)))

    c = Stock(sym, 'SMART', 'USD')
    ib.qualifyContracts(c)

    # quote pour des limites marketable
    t = ib.reqMktData(c, '', False, False)
    ib.sleep(2)
    bid, ask, last = t.bid, t.ask, (t.last or t.close)
    ib.cancelMktData(c)
    ref = ask or last
    print(f"{sym}: bid={bid} ask={ask} last={last}")
    if not ref:
        print("✗ pas de prix — abort."); ib.disconnect(); return

    trail_accepted = False
    trail_status = None
    try:
        # 1) ACHAT 1 action au MARCHÉ (séance ouverte -> fill immédiat)
        print(f"\n[1] ACHAT 1 {sym} au marché ...")
        buy = MarketOrder('BUY', 1); buy.tif = 'DAY'
        bt = ib.placeOrder(c, buy)
        filled = wait_fill(ib, bt)
        print(f"    status={bt.orderStatus.status} filled={filled}")
        if position_qty(ib, sym) < 1:
            print("    ✗ achat non rempli -> on n'ira pas plus loin.")
            return

        # 2/3) TRAIL percent-seul sur la position détenue
        print(f"\n[2] Pose TRAIL {args.trail*100:.0f}% (percent seul, pas de trailStopPrice)...")
        errs.clear()
        o = Order(orderType='TRAIL', action='SELL', totalQuantity=1,
                  trailingPercent=round(args.trail * 100, 2), tif='DAY')
        tr = ib.placeOrder(c, o)
        ib.sleep(3)
        trail_status = tr.orderStatus.status
        rejected = any(code == 201 for code, _ in errs)
        trail_accepted = (not rejected) and trail_status in (
            'Submitted', 'PreSubmitted', 'PendingSubmit')
        print(f"    status={trail_status}  trailStopPrice(auto)={tr.order.trailStopPrice}")
        for code, msg in errs:
            print(f"    IBKR {code}: {msg}")
        print(f"    -> {'✅ ACCEPTÉ' if trail_accepted else '❌ REJETÉ'}")

        # 4) annuler le trail
        print("\n[3] Annulation du trail...")
        ib.cancelOrder(o); ib.sleep(1)

    finally:
        # 5) SOLDE : revendre ce qu'on détient (couvert, pas de short)
        q = position_qty(ib, sym)
        if q > 0:
            print(f"\n[4] SOLDE : vente {q} {sym} au marché ...")
            so = MarketOrder('SELL', q); so.tif = 'DAY'
            st = ib.placeOrder(c, so)
            wait_fill(ib, st)
            print(f"    status={st.orderStatus.status} pos_finale={position_qty(ib, sym)}")
        else:
            print("\n[4] rien à solder (position déjà plate).")

    print("\n================ RÉSUMÉ ================")
    print(f"TRAIL percent-seul (C) : {'✅ ACCEPTÉ par IBKR' if trail_accepted else '❌ rejeté'} "
          f"(status={trail_status})")
    print(f"Position finale {sym} : {position_qty(ib, sym)} (doit être 0)")
    ib.disconnect()


if __name__ == '__main__':
    main()
