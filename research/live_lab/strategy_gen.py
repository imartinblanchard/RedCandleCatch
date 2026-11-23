#!/usr/bin/env python3
"""GÉNÉRATEUR de stratégies : au lieu d'un menu fixe d'archétypes, ASSEMBLE des règles d'achat
à partir de ~24 briques (conditions par bougie), combos de 1 ou 2 briques, et les teste toutes
sur l'univers LARGE (bars-*.parquet) × gap × fenêtre × sortie × stop × liquidité. Classe par
ROBUSTESSE (OOS + 2 moitiés + t). Réutilise le moteur price_lab (engine/indicators/backtest).

⚠️ ÉNORME risque de faux positifs (45 j × ~500k configs) : ne RIEN prendre pour argent comptant,
lire la robustesse. Le nightly re-testera la liste courte sur la data accumulée.

Usage : python -m research.live_lab.strategy_gen            (recherche complète)
        python -m research.live_lab.strategy_gen --calib    (mesure la vitesse sur un échantillon)
        python -m research.live_lab.strategy_gen --validate (prouve que (rsi^20 & green) == archétype rsi_bounce)
"""
import os, sys, time, itertools, argparse, glob, pickle, hashlib
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
from research.live_lab import backtest as bt
from research.price_lab import engine as E

PM_LO, PM_HI = 480, 570
GAPS = [('3-5', 3, 5), ('5-7', 5, 7), ('7-10', 7, 10), ('10-14', 10, 14), ('14-20', 14, 20),
        ('20-30', 20, 30), ('30-50', 30, 50), ('50-70', 50, 70), ('70-90', 70, 90),
        ('90-120', 90, 120), ('120-160', 120, 160), ('160-220', 160, 220), ('220-500', 220, 500),
        ('all', -100, 9999)]
WINS = [('9:30>midi', 570, 720), ('9:30>15:55', 570, 955)]
EXITS = {'tp15': dict(exit_mode='tp', tp_pct=0.15), 'tp20': dict(exit_mode='tp', tp_pct=0.20),
         'trail10/5': dict(exit_mode='trail', activate_pct=0.10, trail_pct=0.05), 'eod': dict(exit_mode='eod')}
STOPS = [0.08, 0.10]
LIQ = [('none', None, None), ('pm0.20', 'pm', 0.20), ('pm0.35', 'pm', 0.35),
       ('act30>=10', 'entry', ('act_30', 10)), ('act30>=15', 'entry', ('act_30', 15)),
       ('dvol30>=100k', 'entry', ('dvol_30', 100_000)), ('dvol30>=200k', 'entry', ('dvol_30', 200_000))]
N_MIN = 30
OUT = os.path.join(HERE, 'results', 'strategy_gen-results.csv')
DONE = os.path.join(HERE, 'results', 'strategy_gen-done.txt')     # bandes déjà terminées (reprise)
PREP_CACHE = os.path.join(HERE, 'results', 'strategy_gen-prep.pkl')


def _cross_up(x, thr):
    x = np.asarray(x, float); out = np.zeros(len(x), bool)
    out[1:] = (x[:-1] < thr) & (x[1:] >= thr); return out


def _rising(c, n):
    c = np.asarray(c, float); inc = np.zeros(len(c), bool); inc[1:] = c[1:] > c[:-1]
    run = np.zeros(len(c), int)
    for i in range(len(c)):
        run[i] = run[i - 1] + 1 if (i > 0 and inc[i]) else (1 if inc[i] else 0)
    return run >= n


# ~24 BRIQUES : nom -> fonction(ind) -> tableau booléen par bougie (CAUSAL)
PRIMS = {
    'rsi<30':    lambda d: d['rsi'] < 30,
    'rsi^20':    lambda d: _cross_up(d['rsi'], 20),
    'rsi^30':    lambda d: _cross_up(d['rsi'], 30),
    'rsi>50':    lambda d: d['rsi'] > 50,
    'stoch<20':  lambda d: d['stoch_k'] < 20,
    'stoch^20':  lambda d: _cross_up(d['stoch_k'], 20),
    'will<-80':  lambda d: d['wr'] < -80,
    'cci<-100':  lambda d: d['cci'] < -100,
    'cci>100':   lambda d: d['cci'] > 100,
    'c<bbLo':    lambda d: d['c'] < d['bb_lo'],
    'c>bbUp':    lambda d: d['c'] > d['bb_up'],
    'c>ema9':    lambda d: d['c'] > d['ema9'],
    'c>ema20':   lambda d: d['c'] > d['ema20'],
    'c>ema50':   lambda d: d['c'] > d['ema50'],
    'ema9>ema20': lambda d: d['ema9'] > d['ema20'],
    'c>sma20':   lambda d: d['c'] > d['sma20'],
    'roc>0':     lambda d: d['roc'] > 0,
    'macd>0':    lambda d: d['macd_hist'] > 0,
    'macd^0':    lambda d: _cross_up(d['macd_hist'], 0),
    'newHOD':    lambda d: d['h'] >= d['hod'],
    'c>prevH':   lambda d: np.concatenate(([False], d['c'][1:] > d['h'][:-1])),
    'hh2':       lambda d: _rising(d['c'], 2),
    'hh3':       lambda d: _rising(d['c'], 3),
    'green':     lambda d: d['green'],
}
NAMES = list(PRIMS)


def prep(groups):
    """Précalcule, par ticker-jour : arrays utiles + les 24 briques booléennes (une seule fois)."""
    P = []
    for g in groups:
        ind = E._ind(g)
        prims = np.stack([np.asarray(PRIMS[n](ind), bool) for n in NAMES])   # (24, nbars)
        P.append(dict(g=g, mins=np.asarray(ind['mins']), c=np.asarray(ind['c'], float),
                      gap=np.asarray(ind['gap'], float), act_30=ind['act_30'], dvol_30=ind['dvol_30'],
                      pm=sum(1 for mn, vv in zip(ind['mins'], ind['v']) if PM_LO <= mn < PM_HI and vv > 0) / (PM_HI - PM_LO),
                      prims=prims))
    return P


def _bars_key():
    """Clé de validité du cache = empreinte des bars-*.parquet (noms + tailles)."""
    files = sorted(glob.glob(os.path.join(bt.DATA, 'bars-*.parquet')))
    sig = ';'.join(f'{os.path.basename(f)}:{os.path.getsize(f)}' for f in files)
    return hashlib.md5(sig.encode()).hexdigest()


def prep_cached(groups):
    """prep() avec CACHE disque — invalidé si les bars changent. Évite de repayer ~15 min à chaque relance."""
    key = _bars_key()
    if os.path.exists(PREP_CACHE):
        try:
            blob = pickle.load(open(PREP_CACHE, 'rb'))
            if blob.get('key') == key:
                print(f"prep : chargé du cache ({len(blob['prepped'])} ticker-jours)", flush=True)
                return blob['prepped']
        except Exception:
            pass
    t0 = time.time(); prepped = prep(groups)
    pickle.dump({'key': key, 'prepped': prepped}, open(PREP_CACHE, 'wb'), protocol=4)
    print(f"prep : calculé en {time.time()-t0:.0f}s et mis en cache", flush=True)
    return prepped


def _done_bands():
    return set(open(DONE).read().split()) if os.path.exists(DONE) else set()


def _mark_done(band):
    with open(DONE, 'a') as f:
        f.write(band + '\n')


def entries(prepped, ci, cj, gmin, gmax, ws, we, liqkind, liqarg):
    """Liste (elem, i) : 1re bougie passant gap/prix/fenêtre/liquidité ET les briques ci(&cj)."""
    out = []
    for e in prepped:
        if liqkind == 'pm' and e['pm'] < liqarg:
            continue
        mask = e['prims'][ci] if cj is None else (e['prims'][ci] & e['prims'][cj])
        gate = ((e['mins'] >= ws) & (e['mins'] <= we) & (e['c'] >= 3.0) & (e['c'] <= 20.0) &
                (e['gap'] >= gmin) & (e['gap'] <= gmax) & mask)
        if liqkind == 'entry':
            gate = gate & (e[liqarg[0]] >= liqarg[1])
        idx = np.argmax(gate)
        if gate[idx]:
            out.append((e, int(idx)))
    return out


def eval_exits(ents, dates, split):
    """Pour un jeu d'entrées, balaie sorties×stops -> lignes de résultat robustes/non."""
    rows = []
    for exl, ex_ in EXITS.items():
        for stp in STOPS:
            Q = dict(E.DEFAULTS); Q.update(ex_); Q['stop_pct'] = stp
            recs = [dict(ticker=e['g']['tk'], date=e['g']['date'], entry_min=int(e['mins'][i]),
                         entry=round(float(e['c'][i]), 4), gap=round(float(e['gap'][i]), 1),
                         pnl=round(bt._pnl(e['g'], i, Q, True), 3)) for e, i in ents]
            df = pd.DataFrame(recs)
            if len(df) < N_MIN:
                continue
            r = E.evaluate(df, dates, split, stop_pct=stp)
            if not r:
                continue
            r['robust'] = bool(r['e_h1'] > 0 and r['e_h2'] > 0 and r['t'] >= 2 and r['cpte_oos'] > 0)
            pnl = df['pnl']; w = pnl[pnl > 0]; l = pnl[pnl <= 0]       # R:R réalisé
            gm = float(w.mean()) if len(w) else 0.0; pm_ = float(l.mean()) if len(l) else 0.0
            r['gain_moy'] = round(gm, 2); r['perte_moy'] = round(pm_, 2)
            r['rr'] = round(gm / abs(pm_), 2) if pm_ < 0 else 0.0     # gain moy / perte moy
            rows.append((exl, stp, r))
    return rows


def combos():
    singles = [(i, None) for i in range(len(NAMES))]
    pairs = [(i, j) for i, j in itertools.combinations(range(len(NAMES)), 2)]
    return singles + pairs


def run_band(prepped, dates, split, gl, gmin, gmax, cmb):
    """Teste TOUS les combos × fenêtre × liquidité × sortie × stop pour UNE bande de gap.
    -> liste de lignes de résultat. (Unité de checkpoint : on sauvegarde après chaque bande.)"""
    rows = []
    for ci, cj in cmb:
        nm = NAMES[ci] + ('' if cj is None else ' & ' + NAMES[cj])
        for wl, ws, we in WINS:
            for liql, lk, la in LIQ:
                ents = entries(prepped, ci, cj, gmin, gmax, ws, we, lk, la)
                for exl, stp, r in eval_exits(ents, dates, split):
                    rows.append(dict(regle=nm, gap=gl, heure=wl, liq=liql, exit=f'{exl}/s{int(stp*100)}',
                                     **{c: r[c] for c in ['n', 'trj', 'exp', 't', 'win', 'gain_moy', 'perte_moy', 'rr', 'cpte', 'cpte_oos', 'e_h1', 'e_h2', 'maxDD', 'robust']}))
    return rows


def main(mode, gap_filter=None):
    groups, dates = bt.load_groups()
    ex = E.excluded_set()
    groups = [g for g in groups if (g['tk'], g['date']) not in ex]
    split = bt.oos_split(dates)
    cmb = combos()
    bands = [b for b in GAPS if (gap_filter is None or b[0] in gap_filter)]
    print(f"univers {len(groups)} ticker-jours · {len(dates)} séances · OOS {split}", flush=True)
    print(f"briques {len(NAMES)} · combos {len(cmb)} · bandes {[b[0] for b in bands]}", flush=True)
    prepped = prep_cached(groups)

    if mode == 'validate':
        ci, cj = NAMES.index('rsi^20'), NAMES.index('green')
        ents = entries(prepped, ci, cj, 3, 10, 570, 720, None, None)
        arche = E.entries(groups, 'rsi_bounce', dict(gap_min=3, gap_max=10, entry_start=570, entry_end=720, rsi_lo=20))
        a = sorted((e['g']['tk'], e['g']['date'], i) for e, i in ents)
        b = sorted((g['tk'], g['date'], i) for g, ind, i in arche)
        print(f"(rsi^20 & green) gap3-10 : généré {len(a)} vs rsi_bounce {len(b)} -> "
              f"{'✅ IDENTIQUE' if a == b else '⚠️ DIFFÉRENT'}")
        return

    done_bands = _done_bands()
    for gl, gmin, gmax in bands:
        if gl in done_bands:
            print(f"[{gl}] déjà fait -> skip", flush=True); continue
        t0 = time.time()
        rows = run_band(prepped, dates, split, gl, gmin, gmax, cmb)
        # CHECKPOINT : append au CSV + marque la bande faite (crash-safe)
        pd.DataFrame(rows).to_csv(OUT, mode='a', header=not os.path.exists(OUT), index=False)
        _mark_done(gl)
        if mode == 'calib':
            dt = time.time() - t0; ncfg = len(cmb) * len(WINS) * len(LIQ) * len(EXITS) * len(STOPS)
            print(f"[{gl}] CALIB : {ncfg:,} configs en {dt/60:.1f} min ({len(rows)} gardées) "
                  f"-> ~{dt/60:.0f} min/bande", flush=True)
            return
        print(f"[{gl}] ✅ {len(rows)} lignes gardées en {(time.time()-t0)/60:.1f} min -> checkpoint", flush=True)
    print(f"\nTERMINÉ. Résultats -> {OUT}", flush=True)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--calib', action='store_true', help='mesure le temps sur la 1re bande puis stop')
    ap.add_argument('--validate', action='store_true', help='prouve générateur == archétype')
    ap.add_argument('--gaps', default=None, help='bandes à tester, ex: 3-5,5-7,7-10,10-14,14-20')
    a = ap.parse_args()
    gf = set(a.gaps.split(',')) if a.gaps else None
    main('calib' if a.calib else 'validate' if a.validate else 'full', gap_filter=gf)
