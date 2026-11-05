#!/usr/bin/env python3
"""
Le dip -6% sur 1 vs 2 vs 3 bougies : les entrées étalées sont-elles aussi positives ?

Live actuel : entrée quand UNE bougie 1-min ferme à -DIP (%) de son open.
Question : si on autorise le -6% à se former sur les N dernières bougies (baisse plus
douce, étalée), ça donne quoi ? On mesure le drop NET open->close sur une fenêtre de N
bougies : (close[i] - open[i-N+1]) / open[i-N+1] <= -DIP.
  N=1 = la règle live actuelle (une seule bougie)
  N=2 / N=3 = le -6% peut s'accumuler sur 2 ou 3 bougies

Tout le reste FIXE (stop -10%, act +5%, trail 2%, prix 3-20, sélection PM-high, 1
entrée/jour, peak à partir de i+1 comme le live corrigé, slippage aux 2 côtés).

Lancer : source .venv/bin/activate && python research/test_dip_multibar.py
"""
import os
from collections import defaultdict
import numpy as np
import engine
R = os.path.dirname(__file__)

DIP, STOP, ACT, TRAIL = 0.06, 0.10, 0.05, 0.02
PMIN, PMAX = 3.0, 20.0
ES, EE, XE = 570, 960, 990
NBARS = [1, 2, 3]
BUCKETS = [(10, 20), (20, 30), (10, 300)]
def slip_of(p): return max(0.0015, 0.015 / p)


def first_entry_multibar(mins, o, c, dip, n):
    """1re bougie i où le drop NET sur les n dernières bougies <= -dip, dans la fenêtre."""
    for i in range(len(c)):
        j0 = i - n + 1
        if j0 < 0:
            continue
        if not (ES <= mins[j0] and mins[i] < EE):     # fenêtre d'entrée pour toute la plage
            continue
        if o[j0] > 0 and (c[i] - o[j0]) / o[j0] <= -dip and PMIN <= c[i] <= PMAX:
            return i
    return -1


def exit_pnl(mins, h, l, c, i, trail):
    e = float(c[i]); sl = slip_of(e); ef = e * (1 + sl)
    st, ac = e * (1 - STOP), e * (1 + ACT); activ = False; peak = e; ex = None
    for j in range(i + 1, len(c)):                    # peak à partir de i+1 (comme le live corrigé)
        if not (ES <= mins[j] < XE):
            continue
        if not activ:
            if l[j] <= st: ex = st; break
            peak = max(peak, h[j])
            if h[j] >= ac: activ = True
        else:
            ts = peak * (1 - trail)
            if l[j] <= ts: ex = ts; break
            peak = max(peak, h[j])
    if ex is None:
        win = c[(mins >= ES) & (mins < XE)]
        ex = float(win[-1]) if len(win) else e
    return (ex * (1 - sl) - ef) / ef * 100


def bucket_of(gap):
    for b in BUCKETS:
        if b[0] <= gap < b[1] and b != (10, 300):
            return b
    return None


def main():
    df = engine.load_table(os.path.join(R, 'candles.parquet'))
    # data[(bucket, n)] -> list pnl ; on garde aussi 'ALL' = (10,300)
    data = defaultdict(list)
    # pour la décomposition : est-ce que N=2/3 entre PLUS TÔT / différemment que N=1 ?
    entry_delta = defaultdict(list)   # (n) -> diff d'index d'entrée vs N=1 (quand les deux existent)
    for (tk, date), g in df.groupby(['ticker', 'date'], sort=False):
        g = g.reset_index(drop=True)
        mins = (g['datetime'].str.slice(0, 2).astype(int) * 60
                + g['datetime'].str.slice(3, 5).astype(int)).values
        o = g['o'].values; h = g['h'].values; l = g['l'].values; c = g['c'].values
        pc = float(g['prev_close'].iloc[0]) if 'prev_close' in g else np.nan
        if not pc or pc <= 0 or np.isnan(pc):
            continue
        pm = (mins >= 240) & (mins < 570)
        if not pm.any():
            continue
        gap = (h[pm].max() - pc) / pc * 100
        b = bucket_of(gap)
        in_all = 10 <= gap < 300
        i1 = None
        for n in NBARS:
            i = first_entry_multibar(mins, o, c, DIP, n)
            if i < 0:
                continue
            if n == 1:
                i1 = i
            elif i1 is not None:
                entry_delta[n].append(i - i1)   # <0 = entre plus tôt
            pnl = exit_pnl(mins, h, l, c, i, TRAIL)
            if b:
                data[(b, n)].append(pnl)
            if in_all:
                data[('ALL', n)].append(pnl)

    def stat(pnls):
        if not pnls:
            return None
        x = np.array(pnls)
        pf = x[x > 0].sum() / (-x[x < 0].sum() or 1e-9)
        t = x.mean() / (x.std(ddof=1) / np.sqrt(len(x))) if len(x) > 1 else 0
        return dict(n=len(x), exp=x.mean(), win=100 * (x > 0).mean(), pf=pf, tot=x.sum(), t=t)

    def show(key, label):
        print(f"\n########## {label} ##########")
        print(f"  {'dip sur':>8} {'n':>5} {'exp%':>7} {'win':>4} {'pf':>5} {'total':>8} {'t':>5}")
        for n in NBARS:
            s = stat(data.get((key, n), []))
            if not s:
                print(f"  {n} bougie(s) : aucun"); continue
            tag = '  <- LIVE' if n == 1 else ''
            print(f"  {n:>2} bougie(s) {s['n']:>5} {s['exp']:>+7.2f} {s['win']:>3.0f}% "
                  f"{s['pf']:>5.2f} {s['tot']:>+8.0f} {s['t']:>5.1f}{tag}")

    show((10, 20), "GAP 10-20% (tranche live)")
    show((20, 30), "GAP 20-30%")
    show('ALL', "GAP 10-300% (tout)")

    print("\n=== N=2/3 entrent-ils plus tôt que N=1 ? (diff d'index de bougie, <0 = plus tôt) ===")
    for n in (2, 3):
        d = np.array(entry_delta[n])
        if len(d):
            print(f"  N={n} : médiane {np.median(d):+.0f} bougies, "
                  f"{100*(d<0).mean():.0f}% entrent PLUS TÔT, {100*(d==0).mean():.0f}% identique")


if __name__ == '__main__':
    main()
