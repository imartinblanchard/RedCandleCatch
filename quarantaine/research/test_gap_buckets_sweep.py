#!/usr/bin/env python3
"""
GRILLE (dip × trail) PAR TRANCHE DE GAP : quelle est la meilleure entrée/sortie à
chaque niveau de gap ?

Tout le reste de la stratégie est FIXE (stop -10%, activation +5%, prix 3-20$,
sélection sur PM-high, 1 entrée/jour, fenêtre RTH, slippage aux 2 côtés). On ne fait
varier que DIP (profondeur du repli d'entrée) et TRAIL (trailing de sortie).

Sortie : par tranche de gap, le top des combos (dip,trail) + la ligne LIVE (5%/2%) en
référence + le meilleur combo ROBUSTE (exp max parmi t>=2 et n>=30).

⚠️ OPTIMISATION IN-SAMPLE : balayer dip×trail par tranche = beaucoup de degrés de
liberté -> on TROUVERA toujours un "meilleur". Lire la FORME (le dip s'approfondit-il
avec le gap ?), pas le gagnant exact. Le juge reste le forward-test.

Lancer : source .venv/bin/activate && python research/test_gap_buckets_sweep.py
"""
import os
from collections import defaultdict
import numpy as np
import engine
R = os.path.dirname(__file__)

# --- FIXE ---
STOP, ACT = 0.10, 0.05
PMIN, PMAX = 3.0, 20.0
ES, EE, XE = 570, 960, 990          # 9:30 / 16:00 / 16:30
def slip_of(p): return max(0.0015, 0.015 / p)

# --- ce qu'on balaye ---
DIPS   = [0.03, 0.04, 0.05, 0.06, 0.08, 0.10]
TRAILS = [0.02, 0.03, 0.04, 0.05, 0.06, 0.08]
BUCKETS = [(10, 20), (20, 30), (30, 40), (40, 50), (50, 60), (60, 70), (70, 100), (100, 300)]
LIVE = (0.05, 0.02)


def first_entry(mins, o, c, dip):
    """1re bougie de la fenêtre avec repli <= -dip et prix 3-20. Renvoie l'index ou -1."""
    for i in range(len(c)):
        if not (ES <= mins[i] < EE):
            continue
        if o[i] > 0 and (c[i] - o[i]) / o[i] <= -dip and PMIN <= c[i] <= PMAX:
            return i
    return -1


def exit_pnl(mins, h, l, c, i, trail):
    """P&L two-phase à partir de l'entrée i, pour un trail donné."""
    e = float(c[i]); sl = slip_of(e); ef = e * (1 + sl)
    st, ac = e * (1 - STOP), e * (1 + ACT); activ = False; peak = e; ex = None
    for j in range(i + 1, len(c)):
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
    for lo, hi in BUCKETS:
        if lo <= gap < hi:
            return (lo, hi)
    return None


def main():
    df = engine.load_table(os.path.join(R, 'candles.parquet'))
    # data[(bucket, dip, trail)] -> liste de pnl
    data = defaultdict(list)
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
        b = bucket_of((h[pm].max() - pc) / pc * 100)
        if b is None:
            continue
        for dip in DIPS:
            i = first_entry(mins, o, c, dip)
            if i < 0:
                continue
            for trail in TRAILS:
                data[(b, dip, trail)].append(exit_pnl(mins, h, l, c, i, trail))

    def stat(pnls):
        x = np.array(pnls)
        if len(x) == 0:
            return None
        pf = x[x > 0].sum() / (-x[x < 0].sum() or 1e-9)
        t = x.mean() / (x.std(ddof=1) / np.sqrt(len(x))) if len(x) > 1 else 0
        return dict(n=len(x), exp=x.mean(), win=100 * (x > 0).mean(), pf=pf, tot=x.sum(), t=t)

    for b in BUCKETS:
        combos = []
        for dip in DIPS:
            for trail in TRAILS:
                s = stat(data.get((b, dip, trail), []))
                if s:
                    combos.append((dip, trail, s))
        if not combos:
            print(f"\n########## GAP {b[0]}-{b[1]}% : aucun trade ##########")
            continue
        print(f"\n########## GAP {b[0]}-{b[1]}% ##########")
        print(f"  {'dip':>4} {'trail':>6} {'n':>5} {'exp%':>7} {'win':>4} {'pf':>5} {'total':>8} {'t':>5}")
        # top 6 par expectancy
        for dip, trail, s in sorted(combos, key=lambda x: -x[2]['exp'])[:6]:
            tag = '  <- LIVE' if (dip, trail) == LIVE else ''
            print(f"  {dip*100:>3.0f}% {trail*100:>5.0f}% {s['n']:>5} {s['exp']:>+7.2f} "
                  f"{s['win']:>3.0f}% {s['pf']:>5.2f} {s['tot']:>+8.0f} {s['t']:>5.1f}{tag}")
        # ligne LIVE si pas déjà affichée
        live = next((s for d, tr, s in combos if (d, tr) == LIVE), None)
        if live:
            print(f"  -- LIVE 5%/2% : n={live['n']} exp={live['exp']:+.2f}% pf={live['pf']:.2f} t={live['t']:.1f}")
        # meilleur robuste : exp max parmi t>=2 et n>=30
        robust = [(d, tr, s) for d, tr, s in combos if s['t'] >= 2 and s['n'] >= 30]
        if robust:
            d, tr, s = max(robust, key=lambda x: x[2]['exp'])
            print(f"  >> ROBUSTE : dip {d*100:.0f}% / trail {tr*100:.0f}%  "
                  f"exp={s['exp']:+.2f}%  pf={s['pf']:.2f}  n={s['n']}  t={s['t']:.1f}")
        else:
            print("  >> ROBUSTE : aucun combo t>=2 & n>=30 (tranche trop fine / peu d'edge)")


if __name__ == '__main__':
    main()
