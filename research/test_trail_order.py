"""
test_trail_order.py — prouve pourquoi le TRAIL du RedCandleCatch est rejeté (err 201).

Hypothèse : `round(px, 4)` produit un prix en SOUS-PENNY (ex 4.8216) qui viole le
tick minimum (0,01$ pour les actions ≥ 1$). IBKR l'accepte au whatIf mais le REJETTE
au vrai placeOrder → err 201 Invalid Price. La position RedCandleCatch reste alors à nu.

Ce test se connecte au compte RÉEL (port 4001, clientId aléatoire pour ne PAS
entrer en conflit avec le bot live sur clientId 31), pose plusieurs variantes de
TRAIL SELL — 1 SEULE ACTION par essai — capture le statut + les erreurs IBKR
pendant ~3s, puis annule chaque ordre immédiatement.

Lancer :
    source .venv/bin/activate
    python research/test_trail_order.py --symbol FTFT

⚠️ Pose de VRAIS ordres (1 action, annulés aussitôt) sur le compte LIVE 4001.
"""
import argparse
import random
from ib_insync import IB, Stock, Order


def round_tick(px: float, min_tick: float) -> float:
    """Arrondit au tick minimum réel de l'instrument (data-driven)."""
    return round(round(px / min_tick) * min_tick, 6)


def build_trail(action, qty, trail_pct, stop_price, outside_rth=True):
    return Order(orderType='TRAIL', action=action, totalQuantity=qty,
                 trailingPercent=round(trail_pct * 100, 2),
                 trailStopPrice=stop_price, tif='DAY', outsideRth=outside_rth)


def try_order(ib, contract, order, label):
    """Pose l'ordre, écoute les erreurs 3s, renvoie (statut, erreurs)."""
    errs = []
    handler = lambda reqId, code, msg, *a: errs.append((code, msg))
    ib.errorEvent += handler
    trade = ib.placeOrder(contract, order)
    ib.sleep(3)
    status = trade.orderStatus.status
    ib.errorEvent -= handler
    try:
        ib.cancelOrder(order)
    except Exception:
        pass
    ib.sleep(0.5)
    rejected = any(code == 201 for code, _ in errs)
    verdict = 'REJETÉ (err 201)' if rejected else f'ACCEPTÉ (status={status})'
    print(f"\n[{label}]")
    print(f"    trailStopPrice = {order.trailStopPrice}  trailingPercent = {order.trailingPercent}")
    print(f"    -> {verdict}")
    for code, msg in errs:
        print(f"       IBKR {code}: {msg}")
    return not rejected


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--symbol', default='FTFT')
    ap.add_argument('--trail', type=float, default=0.02, help='trailing % (0.02 = 2%)')
    ap.add_argument('--port', type=int, default=4001, help='4001 = compte réel')
    args = ap.parse_args()
    qty = 1  # 1 SEULE action par essai (ordres annulés aussitôt)

    ib = IB()
    cid = random.randint(40, 3999)
    print(f"Connexion IBKR 127.0.0.1:{args.port} clientId={cid} (LIVE, {qty} action/essai)...")
    ib.connect('127.0.0.1', args.port, clientId=cid, timeout=15)

    c = Stock(args.symbol, 'SMART', 'USD')
    ib.qualifyContracts(c)

    # tick minimum réel de l'instrument
    details = ib.reqContractDetails(c)
    min_tick = details[0].minTick if details else 0.01
    print(f"{args.symbol}: minTick = {min_tick}")

    # prix courant
    t = ib.reqMktData(c, '', False, False)
    ib.sleep(2)
    px = t.last or t.close or 0
    ib.cancelMktData(c)
    if not px:
        print("⚠️ pas de prix — marché fermé ? on utilise un peak fictif de 5.15")
        px = 5.15
    peak = px
    print(f"prix courant ≈ {px}  (on prend peak = {peak})")

    raw = peak * (1 - args.trail)
    print(f"\npeak*(1-{args.trail}) = {raw}")

    # Variante A : le code ACTUEL (round à 4 décimales → sous-penny probable)
    a_price = round(raw, 4)
    okA = try_order(ib, c, build_trail('SELL', qty, args.trail, a_price),
                    f"A — CODE ACTUEL: round(_,4) = {a_price}")

    # Variante B : le FIX — arrondi au tick réel
    b_price = round_tick(raw, min_tick)
    okB = try_order(ib, c, build_trail('SELL', qty, args.trail, b_price),
                    f"B — FIX: round_tick = {b_price}")

    # Variante C : trailingPercent seul, sans trailStopPrice (IBKR calcule)
    oc = Order(orderType='TRAIL', action='SELL', totalQuantity=qty,
               trailingPercent=round(args.trail * 100, 2), tif='DAY', outsideRth=True)
    okC = try_order(ib, c, oc, "C — trailingPercent seul (pas de trailStopPrice)")

    print("\n================ RÉSUMÉ ================")
    print(f"A (round _,4)        : {'OK' if okA else 'REJETÉ'}")
    print(f"B (round au tick)    : {'OK' if okB else 'REJETÉ'}")
    print(f"C (percent seul)     : {'OK' if okC else 'REJETÉ'}")
    print("Attendu si l'hypothèse tient : A REJETÉ, B et C OK.")
    ib.disconnect()


if __name__ == '__main__':
    main()
