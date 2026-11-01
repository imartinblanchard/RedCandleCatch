#!/usr/bin/env python3
"""Recherche swing À TRAVERS L'UNIVERS ETF (non-biaisé). Chaque stratégie (archétype × params) est
évaluée sur CHAQUE ETF, puis AGRÉGÉE : le juge = sur combien de titres elle bat le buy & hold (full
ET OOS), et son profil risque (Sharpe, maxDD) vs B&H. Une stratégie qui tient sur BEAUCOUP de noms
>> une qui gagne sur un seul. Split OOS train 60% / test 40% par titre.

⚠️ Même sur un univers, battre le B&H d'ETF larges est DUR (le marché monte en moyenne). Lire le
'%bat_oos' (part des titres battus en OOS) et le profil risque, pas un titre isolé."""
import os, sys
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(HERE))))
from research.swing_lab import engine as E, signals as S
from research.swing_lab.universes import UNIVERSES
from research.swing_lab.studies.strategy_search import GRIDS, TRAIN_FRAC


def load_universe(name):
    out = {}
    for tk in UNIVERSES[name]:
        f = os.path.join(E.DATA, f'{tk.lower()}_daily.parquet')
        if os.path.exists(f):
            out[tk] = pd.read_parquet(f).sort_values('date').reset_index(drop=True)
    return out


def main():
    name = sys.argv[1] if len(sys.argv) > 1 else 'etf'
    U = load_universe(name)
    print(f"Univers : {len(U)} ETF. Split OOS train {int(TRAIN_FRAC*100)}% / test.\n", flush=True)
    rows = []
    for arch, grid in GRIDS.items():
        fn = S.REGISTRY[arch]
        for P in grid:
            cg, sh, dd, bcg, bsh, bdd = [], [], [], [], [], []
            beat_f, beat_o, pos_both = 0, 0, 0
            for tk, df in U.items():
                c = df['c'].to_numpy(float); n = len(c); isp = int(n * TRAIN_FRAC)
                pos = np.asarray(fn(df, P), float)
                f = E._metrics(pos, c); tr = E._metrics(pos[:isp], c[:isp]); te = E._metrics(pos[isp:], c[isp:])
                bh = E._metrics(np.ones(n), c)          # buy & hold de ce titre (full)
                cg.append(f['cagr']); sh.append(f['sharpe']); dd.append(f['maxDD'])
                bcg.append(bh['bh_cagr']); bsh.append(bh['sharpe']); bdd.append(bh['bh_maxDD'])
                beat_f += f['cagr'] > f['bh_cagr']
                beat_o += te['cagr'] > te['bh_cagr']
                pos_both += (tr['cagr'] > 0 and te['cagr'] > 0)
            m = len(U)
            rows.append(dict(arch=arch, params=str(P),
                             mean_cagr=round(np.mean(cg), 1), mean_bh_cagr=round(np.mean(bcg), 1),
                             excess=round(np.mean(cg) - np.mean(bcg), 1),
                             mean_sharpe=round(np.mean(sh), 2), mean_bh_sharpe=round(np.mean(bsh), 2),
                             mean_maxDD=round(np.mean(dd), 1), mean_bh_maxDD=round(np.mean(bdd), 1),
                             pct_beat_full=round(100 * beat_f / m), pct_beat_oos=round(100 * beat_o / m),
                             pct_pos_both=round(100 * pos_both / m)))
    r = pd.DataFrame(rows)
    r.to_csv(os.path.join(os.path.dirname(HERE), 'results', f'universe_search_{name}.csv'), index=False)

    # moyenne B&H de l'univers (référence)
    bhc = np.mean([E._metrics(np.ones(len(d)), d['c'].to_numpy(float))['bh_cagr'] for d in U.values()])
    bhsh = np.mean([E._metrics(np.ones(len(d)), d['c'].to_numpy(float))['sharpe'] for d in U.values()])
    print(f"BUY & HOLD moyen de l'univers : CAGR {bhc:+.0f}%, Sharpe {bhsh:.2f}\n")
    cols = ['arch', 'params', 'mean_cagr', 'excess', 'mean_sharpe', 'mean_bh_sharpe',
            'mean_maxDD', 'mean_bh_maxDD', 'pct_beat_oos', 'pct_pos_both']
    print(f"{len(r)} combos. TOP 15 par %titres battant le B&H en OOS (puis Sharpe) :")
    top = r.sort_values(['pct_beat_oos', 'mean_sharpe'], ascending=False).head(15)
    print(top[cols].to_string(index=False), flush=True)
    print("\nLECTURE : excess = CAGR strat − CAGR B&H (moyen). mean_maxDD vs mean_bh_maxDD = profil risque.")
    print("  pct_beat_oos = % des 15 ETF où la strat bat le B&H sur la 2e moitié (robustesse cross-titres).")
    print("  pct_pos_both = % des ETF avec CAGR>0 sur train ET test (non dégénéré).")
    print("CSV: research/swing_lab/results/universe_search.csv")


if __name__ == '__main__':
    main()
