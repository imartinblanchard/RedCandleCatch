#!/usr/bin/env python3
"""
Sweep de SORTIE RedCandleCatch — le 1er passage a montré que le trailing serré perd
(logique momentum vs thèse mean-reversion). On teste ici les bons modèles de sortie sur
2 entrées fixées : stop large, trailing désactivé/large, take-profit, hold variable.

Lancer : source .venv/bin/activate && python redcandleCatch_snp500/sweep_exit.py
"""
import os, itertools
import engine
import strategies as st

HERE = os.path.dirname(os.path.abspath(__file__))

ENTRIES = [('dip 3%/1j', st.dip_fixed(0.03, 1)),
           ('dip 2σ/1j', st.dip_vol(2.0, 1))]
STOPS = [0.05, 0.08, 0.12]
TRAILS = [None, 0.10]          # None = pas de trailing (mean-reversion pure)
HOLDS = [3, 5, 10]
TARGETS = [None, 0.03, 0.05]   # None = pas de take-profit


def line(label, m):
    print(f"  {label:34} n={m['n']:>6} exp={m['exp']:>+6.2f}% win={m['win']:>3.0f}% "
          f"pf={m['pf']:>4.2f} total={m['total']:>+7.0f}% t={m['t']:>5.1f} j={m['avg_days']:>4.1f}")


def main():
    print("Chargement...")
    df = engine.load_table(os.path.join(HERE, 'data', 'daily.parquet'))
    print(f"{df.ticker.nunique()} titres, {df.date.min()} -> {df.date.max()}\n")

    for ename, efn in ENTRIES:
        df['sig'] = efn(df)
        results = []
        for stop, trail, hold, tgt in itertools.product(STOPS, TRAILS, HOLDS, TARGETS):
            m = engine.metrics(engine.run(df, stop, trail, hold, target=tgt))
            if m.get('n', 0) == 0:
                continue
            tl = 'off' if trail is None else f'{trail*100:.0f}%'
            gl = 'off' if tgt is None else f'+{tgt*100:.0f}%'
            results.append((f'stop{stop*100:.0f}% trail{tl} tp{gl} hold{hold}j', m))

        print(f"########## ENTRÉE : {ename} ##########")
        print("  -- TOP 8 par expectancy/trade --")
        for label, m in sorted(results, key=lambda x: -x[1]['exp'])[:8]:
            line(label, m)
        print("  -- TOP 6 par P&L total --")
        for label, m in sorted(results, key=lambda x: -x[1]['total'])[:6]:
            line(label, m)
        # combien de combos sortie sont POSITIFS et significatifs ?
        pos = [r for r in results if r[1]['exp'] > 0]
        sig = [r for r in results if r[1]['exp'] > 0 and r[1]['t'] >= 2]
        print(f"  => {len(pos)}/{len(results)} combos positifs, dont {len(sig)} significatifs (t>=2)\n")


if __name__ == '__main__':
    main()
