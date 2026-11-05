#!/usr/bin/env python3
"""PIT rebuild — Phase 3 : moteur point-in-time ÉPISODIQUE (le cœur, sans look-ahead).

Pour chaque ticker-jour : suit le PRIX COURANT minute par minute, repère l'éligibilité
CAUSALE (le plus-haut courant entre dans la bande), et enregistre CHAQUE dip qui survient
PENDANT/APRÈS l'éligibilité (jamais avant -> pas de look-ahead). Une ligne par dip, avec
tout le contexte (heure, gap courant, pm_had_gap, phase, dépasse_20, rang...) pour que
l'analyse reconstruise n'importe quelle règle (sticky live / épisodique / re-gap post-open).

Détection à DIP_MIN (1,5%) : on enregistre le dip réel `dip_pct`, l'analyse filtre au-dessus
(un seul passage supporte tout le sweep de dip). prev_close vient de candidates.json.
Sortie : data/trades.parquet
"""
import os, sys, glob, json
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__)); DATA = os.path.join(HERE, 'data')
BARS_DIR = os.path.join(DATA, 'bars')

BAND_LO, BAND_HI = 0.10, 0.20      # bande d'éligibilité (re-jouable pour d'autres bandes)
DIP_MIN = 0.015                    # plancher de DÉTECTION (analyse filtre >= ça)
PMIN_A, PMAX_A = 0.50, 50.0        # prix d'entrée capturé large (filtrage fin à l'analyse)
LIQ = 200_000                      # $ dollar-vol min sur la bougie de dip
STOP, TRAIL = 0.10, 0.02
ACT_PM, ACT_POST = 0.05, 0.10      # activation adaptative (comme déployé)
OPEN_MIN = 570                     # 09:30
ENTRY_END = 955                    # 15:55 (dernières entrées)
EXIT_END = 960                     # 16:00 (fin fenêtre de sortie)

def slip_of(p): return max(0.0015, 0.015 / p)


def simulate_exit(mins, o, h, l, c, i, act):
    """Rejoue STOP/activation/TRAIL à partir du dip index i. Renvoie (pnl%, mfe%)."""
    e = float(c[i]); sl = slip_of(e); ef = e * (1 + sl)
    st, ac = e * (1 - STOP), e * (1 + act)
    activ = False; peak = e; ex = None; N = len(c)
    for j in range(i + 1, N):
        if mins[j] >= EXIT_END:
            break
        if not activ:
            if l[j] <= st: ex = st; break
            if h[j] > peak: peak = h[j]
            if h[j] >= ac: activ = True
        else:
            ts = peak * (1 - TRAIL)
            if l[j] <= ts: ex = ts; break
            if h[j] > peak: peak = h[j]
    if ex is None:
        tail_idx = [k for k in range(i + 1, N) if mins[k] < EXIT_END]
        ex = float(c[tail_idx[-1]]) if tail_idx else e
    pnl = (ex * (1 - sl) - ef) / ef * 100
    mfe = (peak - e) / e * 100
    return pnl, mfe


def replay_day(tk, date, g, pc):
    """g : DataFrame trié d'un ticker-jour. Renvoie une liste de lignes de trade."""
    mins = (g['datetime'].str.slice(0, 2).astype(int) * 60 +
            g['datetime'].str.slice(3, 5).astype(int)).to_numpy()
    o, h, l, c, v = (g[k].to_numpy(dtype=float) for k in ('o', 'h', 'l', 'c', 'v'))
    if pc <= 0:
        return []
    run_high = np.maximum.accumulate(h)
    run_gap = (run_high - pc) / pc               # plus-haut courant vs veille (causal)
    gap_now = (c - pc) / pc                       # prix courant vs veille
    elig = np.where(run_gap >= BAND_LO)[0]
    if len(elig) == 0:
        return []                                 # n'entre jamais dans la bande -> rien
    elig_from = int(elig[0])
    elig_min = int(mins[elig_from])                          # heure de 1re éligibilité (=~ 'added')
    elig_run_gap = float(run_gap[elig_from])                 # niveau au 1er franchissement
    elig_in_band = bool(elig_run_gap <= BAND_HI)             # entré DANS la bande (pas sauté >20)
    pm_had_gap = bool((run_gap[mins < OPEN_MIN] >= BAND_LO).any()) if (mins < OPEN_MIN).any() else False
    depasse_20 = bool(run_gap.max() > BAND_HI)

    out = []; rank = 0
    for i in range(elig_from, len(c)):
        if mins[i] < mins[elig_from] or mins[i] >= ENTRY_END:
            continue
        if o[i] <= 0:
            continue
        dip = (c[i] - o[i]) / o[i]
        if dip > -DIP_MIN:
            continue
        if not (PMIN_A <= c[i] <= PMAX_A):
            continue
        if v[i] * c[i] < LIQ:
            continue
        rank += 1
        act = ACT_PM if mins[i] < OPEN_MIN else ACT_POST
        pnl, mfe = simulate_exit(mins, o, h, l, c, i, act)
        out.append({
            'ticker': tk, 'date': date,
            'entry_time': g['datetime'].iloc[i], 'entry_min': int(mins[i]),
            'entry_price': round(float(c[i]), 4), 'dip_pct': round(dip * 100, 2),
            'phase': 'PM' if mins[i] < OPEN_MIN else 'post-open',
            'gap_now': round(float(gap_now[i]) * 100, 1),
            'run_gap': round(float(run_gap[i]) * 100, 1),
            'in_band_now': bool(BAND_LO <= gap_now[i] <= BAND_HI),
            'elig_min': elig_min, 'elig_run_gap': round(elig_run_gap * 100, 1),
            'elig_in_band': elig_in_band, 'elig_phase': 'PM' if elig_min < OPEN_MIN else 'post-open',
            'pm_had_gap': pm_had_gap, 'depasse_20': depasse_20,
            'dip_dvol': int(v[i] * c[i]), 'dip_rank': rank,
            'pnl_pct': round(pnl, 3), 'mfe_pct': round(mfe, 2),
        })
    return out


def main():
    pc_map = {f"{x['ticker']}|{x['date']}": x['prev_close']
              for x in json.load(open(os.path.join(DATA, 'candidates.json')))}
    files = sorted(glob.glob(os.path.join(BARS_DIR, '*.parquet')))
    print(f"{len(files)} fichiers de bougies (dates) à rejouer", flush=True)
    rows = []
    for fi, path in enumerate(files):
        df = pd.read_parquet(path)
        for (tk, date), g in df.groupby(['ticker', 'date'], sort=False):
            pc = pc_map.get(f"{tk}|{date}")
            if pc is None:
                continue
            g = g.sort_values('datetime')
            rows.extend(replay_day(tk, date, g, pc))
        if fi % 20 == 0:
            print(f"  ...{fi+1}/{len(files)} dates, {len(rows)} trades", flush=True)
    out = pd.DataFrame(rows)
    outp = os.path.join(DATA, 'trades.parquet')
    out.to_parquet(outp)
    print(f"\n✅ {len(out)} dip-entrées enregistrées -> {outp}")
    if len(out):
        print(f"   PM={sum(out['phase']=='PM')}  post-open={sum(out['phase']=='post-open')}")
        print(f"   dip_rank==1 (1re du jour) : {sum(out['dip_rank']==1)}")


if __name__ == '__main__':
    main()
