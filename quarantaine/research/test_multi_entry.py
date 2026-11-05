#!/usr/bin/env python3
"""
Combien de trades/ticker/jour ? Le bot live bride à 1 (self.done.add(tk)).
Question : si on autorise les RÉ-ENTRÉES (2, 3, illimité) dans le même ticker-jour,
qu'est-ce que ça donne ? On compare sur l'historique, config LIVE réelle.

Config two-phase (identique au bot redcandlecatch_terminator) :
  dip -5% (entrée) | stop -10% | activation +5% | trail 2% | prix 3-20$ | fenêtre RTH
Univers : gappers, tranche gap 10-20% (celle du bot). Slippage réaliste aux DEUX côtés
(chaque ré-entrée repaie le spread — c'est là qu'une règle multi peut perdre).

Une "ré-entrée" = après la sortie à la bougie j, on reprend le scan à j+1 pour un
nouveau dip -5%, jusqu'à N trades max (ou fin de journée).

Lancer : source .venv/bin/activate && python research/test_multi_entry.py
"""
import os, json
import numpy as np, pandas as pd
import engine
R = os.path.dirname(__file__)

# --- config LIVE ---
DIP, STOP, ACT, TRAIL = 0.05, 0.10, 0.05, 0.02
PRICE_MIN, PRICE_MAX = 3.0, 20.0
GAP_LO, GAP_HI = 10.0, 20.0
ENTRY_START, ENTRY_END, EXIT_END = 570, 960, 990   # 9:30 / 16:00 / 16:30 en minutes
def slip_of(p): return max(0.0015, 0.015 / p)


def simulate(g, mins, i):
    """Simule un trade two-phase à partir d'un dip à la bougie i.
    Retourne (pnl_pct, exit_bar_index, reason)."""
    e = float(g.iloc[i].c)
    sl = slip_of(e)
    e_fill = e * (1 + sl)                      # slippage à l'ENTRÉE
    st, ac = e * (1 - STOP), e * (1 + ACT)
    activ, peak, ex, reason, jx = False, e, None, 'EOD', len(g) - 1
    for j in range(i + 1, len(g)):
        if not (ENTRY_START <= mins.iat[j] < EXIT_END):
            continue
        rr = g.iloc[j]
        if not activ:
            if rr.l <= st: ex, reason, jx = st, 'STOP', j; break
            peak = max(peak, rr.h)
            if rr.h >= ac: activ = True
        else:
            ts = peak * (1 - TRAIL)
            if rr.l <= ts: ex, reason, jx = ts, 'TRAIL', j; break
            peak = max(peak, rr.h)
    if ex is None:
        win = g['c'][(mins >= ENTRY_START) & (mins < EXIT_END)]
        ex = float(win.iloc[-1]) if len(win) else e
    pnl = (ex * (1 - sl) - e_fill) / e_fill * 100   # slippage à la SORTIE aussi
    return pnl, jx, reason


def run(df, gap, cap):
    """cap = nb max de trades par ticker-jour (1 = règle live actuelle)."""
    rows = []
    for (tk, date), g in df.groupby(['ticker', 'date'], sort=False):
        gp = gap.get((tk, date))
        if gp is None or not (GAP_LO <= gp < GAP_HI):
            continue
        g = g.reset_index(drop=True)
        mins = g['datetime'].str.slice(0, 2).astype(int) * 60 + g['datetime'].str.slice(3, 5).astype(int)
        i, n_today = 0, 0
        while i < len(g):
            if not (ENTRY_START <= mins.iat[i] < ENTRY_END):
                i += 1; continue
            r = g.iloc[i]
            if r.o > 0 and (r.c - r.o) / r.o <= -DIP and PRICE_MIN <= r.c <= PRICE_MAX:
                pnl, jx, reason = simulate(g, mins, i)
                n_today += 1
                rows.append((tk, date, gp, float(r.c), pnl, reason, n_today))
                i = jx + 1                       # reprendre APRÈS la sortie
                if n_today >= cap:
                    break
            else:
                i += 1
    return pd.DataFrame(rows, columns=['ticker', 'date', 'gap', 'price', 'pnl', 'reason', 'rank'])


def stats(L, label):
    if len(L) == 0:
        print(f"{label:22} aucun trade"); return
    pf = L.pnl[L.pnl > 0].sum() / (-L.pnl[L.pnl < 0].sum() or 1e-9)
    x = L.pnl.values
    t = x.mean() / (x.std(ddof=1) / np.sqrt(len(x))) if len(x) > 1 else 0
    print(f"{label:22} n={len(L):>5}  exp={x.mean():+.2f}%/tr  win={100*(x>0).mean():>3.0f}%  "
          f"pf={pf:.2f}  total={x.sum():>+7.0f}%  t={t:>4.1f}")


def main():
    df = engine.load_table(os.path.join(R, 'candles.parquet'))
    gap = {(x['ticker'], x['date']): x['gap'] for x in json.load(open(os.path.join(R, 'gappers.json')))}
    print(f"config LIVE: dip -{DIP*100:.0f}% stop -{STOP*100:.0f}% act +{ACT*100:.0f}% "
          f"trail {TRAIL*100:.0f}% | gap {GAP_LO:.0f}-{GAP_HI:.0f} | prix {PRICE_MIN:.0f}-{PRICE_MAX:.0f}$")

    caps = {1: '1/jour (LIVE actuel)', 2: 'max 2/jour', 3: 'max 3/jour', 99: 'illimité'}
    results = {}
    print("\n=== GLOBAL par plafond ===")
    for cap, lab in caps.items():
        L = run(df, gap, cap)
        results[cap] = L
        stats(L, lab)

    print("\n=== APPORT des ré-entrées (illimité) : trades par rang d'entrée ===")
    Lu = results[99]
    for rk in sorted(Lu['rank'].unique()):
        if rk > 6: break
        stats(Lu[Lu['rank'] == rk], f"  {rk}e entrée du jour")

    print("\n=== DELTA vs LIVE (total P&L cumulé, mise fixe) ===")
    base = results[1].pnl.sum()
    for cap, lab in caps.items():
        d = results[cap].pnl.sum() - base
        extra = len(results[cap]) - len(results[1])
        print(f"  {lab:22} total={results[cap].pnl.sum():>+7.0f}%  "
              f"Δ={d:>+7.0f}%  (+{extra} trades)")

    print("\n=== combien de jours ont réellement ≥2 entrées ? ===")
    Lu = results[99]
    multi_days = Lu[Lu['rank'] >= 2].groupby(['ticker', 'date']).size()
    tot_days = Lu.groupby(['ticker', 'date']).ngroups
    print(f"  {len(multi_days)}/{tot_days} ticker-jours ont une 2e entrée ou plus "
          f"({100*len(multi_days)/tot_days:.0f}%)")


if __name__ == '__main__':
    main()
