#!/usr/bin/env python3
"""Compare les stratégies SWING daily sur NVDA vs BUY & HOLD (le vrai benchmark d'un seul titre).
Classé par CAGR. ⚠️ 1 titre + 3 ans = quasi aucune indépendance stat -> hypothèses, pas des vérités.
Un swing qui bat le B&H sur NVDA (fort trend haussier) est RARE et probablement sur-ajusté."""
import os, sys
import pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(HERE))))
from research.swing_lab import engine as E
from research.swing_lab import signals as S

# (nom affiché, fonction, params)
VARIANTS = [
    ('sma_cross 20/50',        'sma_cross', dict(fast=20, slow=50)),
    ('sma_cross 50/200',       'sma_cross', dict(fast=50, slow=200)),
    ('ema_cross 10/20',        'ema_cross', dict(fast=10, slow=20)),
    ('ema_cross 20/50',        'ema_cross', dict(fast=20, slow=50)),
    ('donchian 50/20',         'donchian_breakout', dict(n_in=50, n_out=20)),
    ('donchian 20/10',         'donchian_breakout', dict(n_in=20, n_out=10)),
    ('trend_pullback r35/200', 'trend_pullback', dict(rsi_lo=35, rsi_hi=55, trend=200)),
    ('rsi_meanrev 30 (trend)', 'rsi_meanrev', dict(rsi_lo=30, rsi_hi=50, trend=200)),
    ('rsi_meanrev 30 (nu)',    'rsi_meanrev', dict(rsi_lo=30, rsi_hi=50)),
    ('momentum 63j',           'momentum', dict(n=63)),
    ('momentum 126j',          'momentum', dict(n=126)),
]


def main():
    df = E.load_daily('nvda')
    print(f"NVDA daily : {len(df)} séances {df.date.iloc[0]}..{df.date.iloc[-1]}\n", flush=True)
    rows = []
    for name, fn, P in VARIANTS:
        m = E.evaluate(df, S.REGISTRY[fn](df, P))
        rows.append(dict(strategie=name, ret=round(m['ret']), cagr=round(m['cagr'], 1),
                         maxDD=round(m['maxDD'], 1), expo=round(m['expo']), ntr=m['ntr'],
                         win=round(m['win']), avgtr=round(m['avgtr'], 1), sharpe=round(m['sharpe'], 2)))
    r = pd.DataFrame(rows).sort_values('cagr', ascending=False).reset_index(drop=True)
    bh = E.evaluate(df, [1.0] * len(df))        # buy & hold = toujours investi

    print(f"{'STRATÉGIE':<24}{'RET%':>7}{'CAGR%':>7}{'maxDD%':>8}{'expo%':>7}{'ntr':>5}{'win%':>6}{'avg/tr%':>8}{'Sharpe':>8}")
    print("─" * 80)
    print(f"{'>>> BUY & HOLD <<<':<24}{bh['ret']:>7.0f}{bh['bh_cagr']:>7.1f}{bh['bh_maxDD']:>8.1f}"
          f"{100:>7.0f}{'—':>5}{'—':>6}{'—':>8}{bh['sharpe']:>8.2f}")
    print("─" * 80)
    for _, x in r.iterrows():
        beat = '✅' if x.cagr > bh['bh_cagr'] else ''
        print(f"{x.strategie:<24}{x.ret:>7.0f}{x.cagr:>7.1f}{x.maxDD:>8.1f}{x.expo:>7.0f}"
              f"{x.ntr:>5.0f}{x.win:>6.0f}{x.avgtr:>8.1f}{x.sharpe:>8.2f} {beat}")
    r.to_csv(os.path.join(os.path.dirname(HERE), 'results', 'swing_compare.csv'), index=False)
    print(f"\nBenchmark BUY & HOLD : +{bh['ret']:.0f}% (CAGR {bh['bh_cagr']:.0f}%, maxDD {bh['bh_maxDD']:.0f}%).")
    print("✅ = bat le buy & hold en CAGR. Sur un titre en fort trend, c'est rare et souvent du sur-ajustement.")
    print("CSV: research/nvda_lab/results/swing_compare.csv")


if __name__ == '__main__':
    main()
