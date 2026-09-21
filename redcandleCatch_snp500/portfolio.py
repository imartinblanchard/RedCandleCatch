#!/usr/bin/env python3
"""
Backtest PORTEFEUILLE RedCandleCatch (S&P 500, daily) — compte réel de 50 000$.

Event-driven jour par jour : gère le cash, les positions SIMULTANÉES, le sizing, et
sort une vraie courbe d'équité (rendement, CAGR, max drawdown, Sharpe) — contrairement
aux sweeps précédents qui sommaient des % de trades (trompeur).

Stratégie (gagnante du sweep de sortie) :
  ENTRÉE : dip normalisé volatilité (~2σ en 1 jour), on priorise les plus survendus.
  SORTIE : stop large, PAS de trailing, PAS de take-profit, tenir HOLD jours.

On balaye le SIZING : fraction de l'équité par position × nb max de positions simultanées.

Lancer : source .venv/bin/activate && python redcandleCatch_snp500/portfolio.py
"""
import os, math, itertools
import numpy as np
import pandas as pd
import engine
import strategies as st

HERE = os.path.dirname(os.path.abspath(__file__))
INIT = 50_000.0
SLIP = 0.001

# stratégie fixée (gagnante du sweep de sortie)
ENTRY = st.dip_vol(2.0, 1)
STOP, TRAIL, HOLD, TARGET = 0.12, None, 10, None

# sizing à balayer
FRACS = [0.05, 0.10, 0.20]         # part de l'équité par position
MAXPOS = [10, 20, 50]              # positions simultanées max


def build(df):
    """Prépare : bars[tk] = dict date->(o,h,l,c) ; signals_by_date = date->[(ret,tk)]."""
    df = df.copy()
    df['sig'] = ENTRY(df)
    df['ret1'] = df.groupby('ticker', sort=False)['c'].pct_change()
    bars = {}
    sig_by_date = {}
    for tk, g in df.groupby('ticker', sort=False):
        d = {}
        for row in g.itertuples(index=False):
            d[row.date] = (row.o, row.h, row.l, row.c)
            if row.sig:
                sig_by_date.setdefault(row.date, []).append((row.ret1, tk))
        bars[tk] = d
    dates = sorted(set().union(*[set(b) for b in bars.values()]))
    didx = {dt: i for i, dt in enumerate(dates)}
    return bars, sig_by_date, dates, didx


def simulate(bars, sig_by_date, dates, didx, frac, maxpos):
    cash = INIT
    pos = {}                        # tk -> dict
    equity_curve = []
    ntrades = 0
    exposure_sum = 0
    for d in dates:
        di = didx[d]
        # 1) SORTIES
        for tk in list(pos.keys()):
            b = bars[tk].get(d)
            if b is None:
                continue
            o, h, l, c = b
            p = pos[tk]
            p['peak'] = max(p['peak'], h)
            held = di - p['di0']
            stop_lvl = p['eraw'] * (1 - STOP)
            if TRAIL is not None:
                stop_lvl = max(stop_lvl, p['peak'] * (1 - TRAIL))
            exit_px = None
            if TARGET is not None and h >= p['eraw'] * (1 + TARGET):
                exit_px = p['eraw'] * (1 + TARGET) * (1 - SLIP)
            elif l <= stop_lvl:
                exit_px = stop_lvl * (1 - SLIP)
            elif held >= HOLD:
                exit_px = c * (1 - SLIP)
            if exit_px is not None:
                cash += p['shares'] * exit_px
                del pos[tk]
        # 2) ENTRÉES (priorité aux plus survendus)
        for ret, tk in sorted(sig_by_date.get(d, [])):
            if tk in pos or len(pos) >= maxpos:
                if len(pos) >= maxpos:
                    break
                continue
            b = bars[tk].get(d)
            if b is None:
                continue
            fill = b[3] * (1 + SLIP)                 # close du jour de signal
            equity = cash + sum(pp['shares'] * bars[t].get(d, (0, 0, 0, pp['eraw']))[3]
                                for t, pp in pos.items())
            budget = min(equity * frac, cash)
            shares = math.floor(budget / fill)
            if shares < 1:
                continue
            cash -= shares * fill
            pos[tk] = {'eraw': b[3], 'shares': shares, 'di0': di, 'peak': b[3]}
            ntrades += 1
        # 3) mark-to-market
        equity = cash + sum(pp['shares'] * bars[t].get(d, (0, 0, 0, pp['eraw']))[3]
                            for t, pp in pos.items())
        equity_curve.append(equity)
        exposure_sum += len(pos)
    eq = pd.Series(equity_curve, index=pd.to_datetime(dates))
    return eq, ntrades, exposure_sum / len(dates)


def stats(eq, ntrades, avg_exposure):
    ret = eq.pct_change().dropna()
    years = len(eq) / 252
    cagr = (eq.iloc[-1] / eq.iloc[0]) ** (1 / years) - 1
    dd = (eq / eq.cummax() - 1).min()
    sharpe = ret.mean() / ret.std() * math.sqrt(252) if ret.std() > 0 else 0
    return dict(final=eq.iloc[-1], ret=eq.iloc[-1] / eq.iloc[0] - 1, cagr=cagr,
                maxdd=dd, sharpe=sharpe, ntrades=ntrades, expo=avg_exposure)


def main():
    print("Chargement + signaux...")
    df = engine.load_table(os.path.join(HERE, 'data', 'daily.parquet'))
    print(f"{df.ticker.nunique()} titres, {df.date.min()} -> {df.date.max()}")
    bars, sig_by_date, dates, didx = build(df)
    print(f"{len(dates)} jours de bourse, {sum(len(v) for v in sig_by_date.values())} signaux\n")
    print(f"Stratégie : entrée 2σ/1j | stop {STOP*100:.0f}% no-trail no-TP hold {HOLD}j | capital {INIT:,.0f}$\n")

    print(f"  {'sizing':22} {'final$':>12} {'rend':>7} {'CAGR':>7} {'maxDD':>7} {'Sharpe':>7} {'trades':>7} {'expo':>5}")
    rows = []
    for frac, mp in itertools.product(FRACS, MAXPOS):
        eq, nt, expo = simulate(bars, sig_by_date, dates, didx, frac, mp)
        s = stats(eq, nt, expo)
        rows.append(((frac, mp), s, eq))
        print(f"  {f'{frac*100:.0f}%/pos, max {mp}':22} {s['final']:>12,.0f} "
              f"{s['ret']*100:>+6.0f}% {s['cagr']*100:>+6.1f}% {s['maxdd']*100:>+6.1f}% "
              f"{s['sharpe']:>7.2f} {s['ntrades']:>7} {s['expo']:>5.1f}")

    best = max(rows, key=lambda r: r[1]['sharpe'])
    (frac, mp), s, eq = best
    print(f"\n>> MEILLEUR (Sharpe) : {frac*100:.0f}%/pos, max {mp} positions")
    print(f"   {INIT:,.0f}$ -> {s['final']:,.0f}$  ({s['ret']*100:+.0f}%, CAGR {s['cagr']*100:+.1f}%, "
          f"maxDD {s['maxdd']*100:.1f}%, Sharpe {s['sharpe']:.2f})")
    eq.to_csv(os.path.join(HERE, 'results_equity_best.csv'))
    print(f"   courbe d'équité -> results_equity_best.csv")


if __name__ == '__main__':
    main()
