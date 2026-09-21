#!/usr/bin/env python3
"""
Sweep RedCandleCatch (S&P 500, daily).

Passage 1 (ce script) : balaye les DÉFINITIONS D'ENTRÉE (dip % fixe et dip normalisé
volatilité, × 1/2/3 jours) avec une sortie FIXE raisonnable, pour voir quelles entrées
ont un edge. Ensuite on figera la meilleure entrée et on balaiera stop/trail/hold.

Lancer : source .venv/bin/activate && python redcandleCatch_snp500/sweep.py
"""
import os
import engine
import strategies as st

HERE = os.path.dirname(os.path.abspath(__file__))

# --- sortie FIXE pour ce passage (on balaiera stop/trail/hold ensuite) ---
STOP, TRAIL, HOLD = 0.04, 0.03, 10

FIXED_PCTS = [0.01, 0.015, 0.02, 0.025, 0.03, 0.04, 0.05]
VOL_KS = [1.5, 2.0, 2.5, 3.0]
NBARS = [1, 2, 3]


def evaluate(df, signal_fn):
    df = df.copy()
    df['sig'] = signal_fn(df)
    m = engine.metrics(engine.run(df, STOP, TRAIL, HOLD))
    return m


def line(label, m):
    if m.get('n', 0) == 0:
        print(f"  {label:16} aucun trade"); return
    print(f"  {label:16} n={m['n']:>6} exp={m['exp']:>+6.2f}% win={m['win']:>3.0f}% "
          f"pf={m['pf']:>4.2f} total={m['total']:>+8.0f}% t={m['t']:>5.1f} "
          f"jours={m['avg_days']:>4.1f}")


def main():
    print("Chargement daily.parquet + calcul sigma...")
    df = engine.load_table(os.path.join(HERE, 'data', 'daily.parquet'))
    print(f"{df.ticker.nunique()} titres, {len(df)} bougies, "
          f"{df.date.min()} -> {df.date.max()}")
    print(f"Sortie FIXE de ce passage : stop -{STOP*100:.0f}% | trail {TRAIL*100:.0f}% | hold {HOLD}j\n")

    print("========== DIP % FIXE (même seuil pour tous les titres) ==========")
    fixed = []
    for nb in NBARS:
        for pct in FIXED_PCTS:
            m = evaluate(df, st.dip_fixed(pct, nb))
            fixed.append((f'{pct*100:.1f}%/{nb}j', m))
    for label, m in sorted(fixed, key=lambda x: -(x[1].get('exp') or -99))[:12]:
        line(label, m)

    print("\n========== DIP NORMALISÉ VOLATILITÉ (seuil propre à chaque titre) ==========")
    vol = []
    for nb in NBARS:
        for k in VOL_KS:
            m = evaluate(df, st.dip_vol(k, nb))
            vol.append((f'{k:.1f}σ/{nb}j', m))
    for label, m in sorted(vol, key=lambda x: -(x[1].get('exp') or -99))[:12]:
        line(label, m)

    print("\n========== MEILLEURS PAR TOTAL P&L (occasions × edge) ==========")
    allc = [('FIXE ' + l, m) for l, m in fixed] + [('VOL  ' + l, m) for l, m in vol]
    for label, m in sorted(allc, key=lambda x: -(x[1].get('total') or -1e9))[:8]:
        line(label, m)


if __name__ == '__main__':
    main()
