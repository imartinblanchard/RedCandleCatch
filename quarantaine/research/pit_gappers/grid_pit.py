#!/usr/bin/env python3
"""PIT rebuild — grille dip × trailing, PROPRE et point-in-time.

Une passe chère : pour chaque dip (>= DIP_MIN, après éligibilité causale), simule la sortie
pour TOUTE la grille (activation × trailing) en un seul parcours de bougies. Stocke un P&L
par combo. L'analyse (grid_analyze.py) balaie ENSUITE dip / gap% / phase / heure par simple
découpage (ce sont des filtres, pas des chemins de sortie -> gratuits).

Éligibilité = 1re minute où le plus-haut courant >= BAND_LO (5% -> capte tous les gap%).
STOP fixe -10%. Contexte riche pour toutes les tranches. Sortie : data/trades_grid.parquet
"""
import os, sys, glob, json
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__)); DATA = os.path.join(HERE, 'data')
BARS_DIR = os.path.join(DATA, 'bars')

BAND_LO = 0.05                     # éligibilité élargie (bucket gap% de 5% à 500%)
DIP_MIN = 0.015                    # détection (dip slicé >= ça à l'analyse)
PMIN_A, PMAX_A = 0.50, 50.0
LIQ = 200_000
STOP = 0.10
OPEN_MIN, ENTRY_END, EXIT_END = 570, 955, 960

ACTS = [0.05, 0.10, 0.15]
TRAILS = [0.01, 0.02, 0.03, 0.04, 0.06]
COMBOS = [(a, tr) for a in ACTS for tr in TRAILS]
COL = [f"a{int(a*100):02d}_t{int(tr*100):02d}" for a, tr in COMBOS]

def slip_of(p): return max(0.0015, 0.015 / p)


def exit_grid(mins, h, l, c, i):
    """Sortie pour tous les combos (act,trail) en UN parcours. Renvoie liste pnl% alignée COMBOS."""
    e = float(c[i]); sl = slip_of(e); ef = e * (1 + sl); st = e * (1 - STOP)
    nk = len(COMBOS)
    acx = np.array([e * (1 + a) for a, _ in COMBOS])
    trx = np.array([tr for _, tr in COMBOS])
    done = np.zeros(nk, bool); activ = np.zeros(nk, bool); expx = np.full(nk, np.nan)
    peak = e; N = len(c); last_c = e
    for j in range(i + 1, N):
        if mins[j] >= EXIT_END:
            break
        loj, hij = l[j], h[j]
        # 1) trailing exits (activés) avec peak AVANT ce high
        m = activ & ~done
        if m.any():
            ts = peak * (1 - trx)
            hit = m & (loj <= ts)
            expx[hit] = ts[hit]; done[hit] = True
        # 2) stop (non activés)
        m = (~activ) & (~done)
        if m.any() and loj <= st:
            expx[m] = st; done[m] = True
        # 3) maj peak avec le high courant
        if hij > peak: peak = hij
        # 4) activation (non activés restants)
        m = (~activ) & (~done)
        if m.any():
            activ[m & (hij >= acx)] = True
        last_c = c[j]
        if done.all():
            break
    expx[np.isnan(expx)] = last_c            # pas sorti -> dernière close vue
    return list((expx * (1 - sl) - ef) / ef * 100)


def replay_day(tk, date, g, pc):
    mins = (g['datetime'].str.slice(0, 2).astype(int) * 60 +
            g['datetime'].str.slice(3, 5).astype(int)).to_numpy()
    o, h, l, c, v = (g[k].to_numpy(dtype=float) for k in ('o', 'h', 'l', 'c', 'v'))
    if pc <= 0:
        return []
    run_gap = (np.maximum.accumulate(h) - pc) / pc
    elig = np.where(run_gap >= BAND_LO)[0]
    if len(elig) == 0:
        return []
    ef0 = int(elig[0]); elig_min = int(mins[ef0])
    pm_had_gap = bool((run_gap[mins < OPEN_MIN] >= 0.10).any()) if (mins < OPEN_MIN).any() else False
    depasse_20 = bool(run_gap.max() > 0.20)
    out = []
    for i in range(ef0, len(c)):
        if mins[i] < mins[ef0] or mins[i] >= ENTRY_END or o[i] <= 0:
            continue
        dip = (c[i] - o[i]) / o[i]
        if dip > -DIP_MIN or not (PMIN_A <= c[i] <= PMAX_A) or v[i] * c[i] < LIQ:
            continue
        pnls = exit_grid(mins, h, l, c, i)
        row = {'ticker': tk, 'date': date, 'entry_min': int(mins[i]),
               'entry_price': round(float(c[i]), 4), 'dip_pct': round(dip * 100, 2),
               'phase': 'PM' if mins[i] < OPEN_MIN else 'post-open',
               'run_gap': round(float(run_gap[i]) * 100, 1),
               'elig_min': elig_min, 'elig_phase': 'PM' if elig_min < OPEN_MIN else 'post-open',
               'pm_had_gap': pm_had_gap, 'depasse_20': depasse_20}
        row.update({COL[k]: round(pnls[k], 3) for k in range(len(COMBOS))})
        out.append(row)
    return out


def main():
    pc_map = {f"{x['ticker']}|{x['date']}": x['prev_close']
              for x in json.load(open(os.path.join(DATA, 'candidates.json')))}
    files = sorted(glob.glob(os.path.join(BARS_DIR, '*.parquet')))
    print(f"{len(files)} dates, grille {len(COMBOS)} combos (act×trail)", flush=True)
    rows = []
    for fi, path in enumerate(files):
        df = pd.read_parquet(path)
        for (tk, date), g in df.groupby(['ticker', 'date'], sort=False):
            pc = pc_map.get(f"{tk}|{date}")
            if pc is None:
                continue
            rows.extend(replay_day(tk, date, g.sort_values('datetime'), pc))
        if fi % 20 == 0:
            print(f"  ...{fi+1}/{len(files)} dates, {len(rows)} dips", flush=True)
    out = pd.DataFrame(rows)
    outp = os.path.join(DATA, 'trades_grid.parquet')
    out.to_parquet(outp)
    print(f"\n✅ {len(out)} dips × {len(COMBOS)} combos -> {outp}")


if __name__ == '__main__':
    main()
