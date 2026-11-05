#!/usr/bin/env python3
"""LEADERBOARD UNIFIÉ — un SEUL tableau fiable, trié par robustesse réelle, nettoyé tout seul.

Rassemble toutes les stratégies (candidates curées + TOP des recherches nightly), les mesure
TOUTES avec la MÊME fonction (live_lab.leaderboard.portfolio, 2%, univers freq-filtré = ce qu'on
trade), calcule leur PERSISTANCE walk-forward (fréquence de présence dans le top au fil des séances
= le séparateur vrai-edge / bruit), ENLÈVE les obsolètes (non-robustes & non-persistantes), et trie
par un SCORE composite qui combine persistance + CPTE + win. 100% automatique (relancé au cron).

Score = 0.45·persistance + 0.35·CPTE + 0.20·win (normalisés). La persistance mène : on a vu
(04/11) qu'un beau win/CPTE in-sample — obv_divergence 84%, trail5/2 — s'effondre dans le temps
(6%/18% de persistance) alors que vwap_reclaim tient (100%). Le tri ne se laisse plus piéger.

Usage : python research/core/leaderboard_all.py [--top 100] [--status deployed|candidate]
         [--keep-obsolete] [--no-persist] (rapide, saute le walk-forward)
Sorties : leaderboard_all_latest.csv (tableau unifié) + leaderboard_all_history.csv (suivi curées).
⚠️ Données live courtes = BRUIT ; la persistance atténue, ne supprime pas. Lire n + OOS."""
import os, sys, argparse, datetime as dt
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)
from research.live_lab import backtest as bt
from research.live_lab.leaderboard import portfolio
from research.indicator_lab import engine as E
from research.indicator_lab.engine import liquid_groups, shape_groups
# rebuild des configs des lignes de recherche (source unique, partagée avec track_robust)
from research.live_lab.studies.track_robust import repli_P, indic_cfg

from research.live_lab.candidates import CANDIDATES as REPLI
from research.indicator_lab.candidates import CANDIDATES as INDIC
REGISTRIES = [REPLI, INDIC]

def _pm(x):                              # seuil PM de la ligne (CSV ancien sans la colonne -> 0.20)
    try: return float(x['pm_thr'])
    except (KeyError, ValueError, TypeError): return 0.20


def _let(x):                             # forme du symbole (CSV ancien sans la colonne -> 'all')
    try:
        v = str(x['letters'])
        return v if v in ('all', '4L') else 'all'
    except (KeyError, ValueError, TypeError): return 'all'


def _lsfx(let):                          # suffixe de nom pour la forme (vide si 'all')
    return f"/{let}" if let != 'all' else ''


SEARCHES = [('repli', os.path.join(ROOT, 'research/live_lab/results/strategy_search_full_results.csv'),
             lambda x: f"{x['gap']}/{x['heures']}/r{x['repli']}/cap{x['capit']}/{x['exit']}/{x['indic']}/pm{int(_pm(x)*100)}{_lsfx(_let(x))}",
             lambda x: (lambda P: (lambda u, P=P: bt.simulate(u, P, slip=True), P['stop_pct']))(repli_P(x))),
            ('indic', os.path.join(ROOT, 'research/indicator_lab/results/indicator_search_results.csv'),
             lambda x: f"{x['archetype']}/rv{x['rvol']}/{x['heure']}/{x['exit']}/pm{int(_pm(x)*100)}{_lsfx(_let(x))}",
             lambda x: (lambda c: (lambda u, c=c: E.simulate(u, c['archetype'], c['P']),
                                   c['P'].get('stop_pct', 0.10)))(indic_cfg(x)))]
TY = 252
PER_FAMILY = 48                         # top-N robustes de chaque recherche à injecter
MIN_DAYS, TOPK = 10, 8                  # persistance : fenêtres >= MIN_DAYS, top-K/jour = persistant
WEIGHTS = dict(persist=0.45, cpte=0.35, win=0.20)    # score composite (persistance en tête)


def _substat(a):
    a = np.asarray(a, float); n = len(a)
    if n < 2: return (n, a.mean() if n else 0.0, 0.0)
    e, sd = a.mean(), a.std(ddof=1)
    return (n, e, e / (sd / np.sqrt(n)) if sd > 0 else 0.0)


def collect_strats(status_filter):
    """Toutes les stratégies à classer : curées (Strategy) + top des recherches (configs rebuildées).
    Chacune -> dict{name, family, status, sim(universe)->trades, stop, notes}. Univers = freq-filtré."""
    S = []
    for reg in REGISTRIES:
        for s in reg:
            if status_filter and s.status != status_filter:
                continue
            # univers curé = 'freq-filtré' -> seuil PM 0.20, toutes formes (celui du filtre déployé)
            S.append(dict(name=s.name, family=s.family, status=s.status, sim=s.sim, stop=s.stop,
                          pm_thr=0.20, letters='all', notes=s.notes))
    if status_filter:
        return S
    for fam, path, namer, builder in SEARCHES:
        if not os.path.exists(path):
            continue
        d = pd.read_csv(path)
        d = d[d.robust].sort_values('cpte', ascending=False).head(PER_FAMILY)
        for _, x in d.iterrows():
            sim, stop = builder(x)
            S.append(dict(name=str(namer(x))[:56], family=fam, status='search', sim=sim, stop=stop,
                          pm_thr=_pm(x), letters=_let(x), notes='top recherche'))
    # dédup par nom (garde la 1re occurrence — une curée l'emporte sur une ligne search homonyme)
    seen, out = set(), []
    for s in S:
        if s['name'] in seen:
            continue
        seen.add(s['name']); out.append(s)
    return out


def persistence(strats, UNIV, dates):
    """Walk-forward : à chaque séance passée (fenêtre expansive), classe TOUTES les stratégies par
    CPTE sur l'univers connu à ce jour (CHACUNE sur son propre seuil PM) ; %persist = fréquence de
    présence dans le top-K. Séparateur vrai-edge / artefact-de-récence (indépendant de la data finale)."""
    ctrl = list(range(MIN_DAYS - 1, len(dates)))
    hits = {s['name']: 0 for s in strats}
    for i in ctrl:
        upto = dates[i]
        lsub = {key: [g for g in gl if g['date'] <= upto] for key, gl in UNIV.items()}   # univers/(seuil,forme) à ce jour
        day = []
        for s in strats:
            t = s['sim'](lsub[(s['pm_thr'], s['letters'])])
            if t is None or not len(t):
                continue
            cp, _ = portfolio(t, 0.02, s['stop'])
            day.append((s['name'], cp))
        day.sort(key=lambda x: -x[1])
        for name, _ in day[:TOPK]:
            hits[name] += 1
    n = max(len(ctrl), 1)
    return {k: round(v / n * 100) for k, v in hits.items()}


def main(top, status_filter, keep_obsolete, do_persist, open_max=40):
    groups, dates = bt.load_groups()
    split = bt.oos_split(dates); tdays = [d for d in dates if split and d >= split]; mid = dates[len(dates) // 2]
    nd, ndo = len(dates), max(len(tdays), 1)
    strats = collect_strats(status_filter)
    keys = {(s['pm_thr'], s['letters']) for s in strats}
    base = {thr: liquid_groups(groups, thr=thr) for thr in {k[0] for k in keys}}
    UNIV = {(thr, let): shape_groups(base[thr], let) for (thr, let) in keys}    # univers par (seuil PM × forme)

    # ── 1) MÉTRIQUES de chaque stratégie (sans persistance pour l'instant) ──
    rows = []
    for s in strats:
        t = s['sim'](UNIV[(s['pm_thr'], s['letters'])])   # CHAQUE stratégie sur son univers (seuil PM × forme)
        if t is None or not len(t):
            continue
        pnl = t.pnl.to_numpy(); n = len(pnl)
        _, exp, tstat = _substat(pnl)
        _, e_h1, _ = _substat(t[t.date < mid].pnl.to_numpy())
        _, e_h2, _ = _substat(t[t.date >= mid].pnl.to_numpy())
        te = t[t.date >= split].pnl if split else pd.Series(dtype=float)
        e_trim = np.sort(pnl)[:-3].mean() if n > 3 else pnl.mean()
        cp, dd = portfolio(t, 0.02, s['stop']); cpo, _ = portfolio(t, 0.02, s['stop'], days=tdays)
        # REPRODUCTIBILITÉ : % d'entrées à l'ouverture (<=9:35 = données temps réel incomplètes ->
        # non reproductible en live, cf vwap) + heure médiane d'entrée. Plus tard = plus fiable.
        em = t['entry_min'] if 'entry_min' in t else pd.Series([570] * n)
        open_pct = round((em <= 575).mean() * 100)
        entry_med = bt.hhmm(int(em.median()))
        robust = bool(e_h1 > 0 and e_h2 > 0 and (not len(te) or te.mean() > 0) and e_trim > 0 and tstat >= 2.0)
        rows.append(dict(famille=s['family'], statut=s['status'], strategie=s['name'],
                         univers=f"PM{int(s['pm_thr']*100)}%" + ('/4L' if s['letters'] == '4L' else ''),
                         n=n, tr_day=round(n / t.date.nunique(), 1), exp=round(exp, 2), t=round(tstat, 1),
                         e_trim=round(e_trim, 2), exp_oos=round(te.mean(), 2) if len(te) else np.nan,
                         win=round((pnl > 0).mean() * 100), persist=np.nan, open_pct=open_pct,
                         entry_med=entry_med, cpte=round(cp, 1), cpte_oos=round(cpo, 1),
                         an=round(cp * TY / nd), an_oos=round(cpo * TY / ndo), maxDD=round(dd, 1),
                         robust=robust, notes=s['notes']))
    r = pd.DataFrame(rows)
    if len(r):
        r['reproductible'] = r['open_pct'] <= open_max

    # ── 2) GATE REPRODUCTIBILITÉ (avant tout le reste) : seules les stratégies refaisables en live
    #    entrent au classement (pas trop d'entrées à l'ouverture). Déployé toujours gardé. ──
    r_full = r.copy()                                 # CSV complet = tout, avec le flag reproductible
    n_open = 0
    if not keep_obsolete and len(r):
        n_open = int((~r['reproductible'] & (r.statut != 'deployed')).sum())
        r = r[(r.statut == 'deployed') | r['reproductible']].copy()

    # ── 3) PERSISTANCE walk-forward PARMI les reproductibles seulement (sinon faussée par les buy-the-open) ──
    kept = set(r['strategie']) if len(r) else set()
    if do_persist:
        persist = persistence([s for s in strats if s['name'] in kept], UNIV, dates)
    else:                                # aperçu rapide : reprend la persistance du dernier run COMPLET
        prev = os.path.join(HERE, 'leaderboard_all_latest.csv'); persist = {}
        if os.path.exists(prev):
            p = pd.read_csv(prev)
            if 'persist' in p and 'strategie' in p:
                persist = {k: v for k, v in zip(p.strategie, p.persist) if pd.notna(v)}
    if len(r):
        r['persist'] = r['strategie'].map(lambda nm_: persist.get(nm_, np.nan))

    # ── 4) NETTOYAGE obsolètes (ni robustes ni persistantes), déployé toujours gardé ──
    if not keep_obsolete and len(r):
        pz = r['persist'].fillna(0)
        keep = (r.statut == 'deployed') | r.robust | (pz >= 20)
        n_drop = n_open + int((~keep).sum())
        r = r[keep].copy()
    else:
        n_drop = n_open

    # ── SCORE composite : persistance (tête) + CPTE + win, normalisés sur l'ensemble gardé ──
    def nm(c):
        x = r[c].astype(float)
        x = x.fillna(x.min() if x.notna().any() else 0.0)     # colonne tout-NaN (ex. --no-persist) -> 0, terme neutre
        return (x - x.min()) / (x.max() - x.min() + 1e-9)
    if len(r):
        r['score'] = (WEIGHTS['persist'] * nm('persist') + WEIGHTS['cpte'] * nm('cpte')
                      + WEIGHTS['win'] * nm('win')).round(3)
        r = r.sort_values('score', ascending=False).reset_index(drop=True)

    print(f"\nDonnées : {nd} séances live ({dates[0]}..{dates[-1]}) | sizing 2%, slip ON, univers freq-filtré")
    print(f"SCORE = {WEIGHTS['persist']}·persist + {WEIGHTS['cpte']}·CPTE + {WEIGHTS['win']}·win (normalisés). "
          f"persist = % du temps dans le top {TOPK} au fil des séances (vrai-edge vs bruit).")
    print(f"GATE REPRODUCTIBILITÉ : {n_open} stratégies EXCLUES car trop d'entrées à l'ouverture "
          f"(open% > {open_max}% = non refaisable en live). + {n_drop - n_open} obsolètes. "
          f"{len(r)} stratégies classées (toutes reproductibles en live).")
    print(f"SCORE = {WEIGHTS['persist']}·persist + {WEIGHTS['cpte']}·CPTE + {WEIGHTS['win']}·win. "
          f"open% = entrées à l'ouverture (<=9:35) ; entrée = heure médiane. C_OOS/persist = SUIVI.\n")
    h = (f"#  {'FAM':<6}{'STATUT':<9}{'STRATÉGIE':<38}{'n':>4}{'t/j':>5}{'exp':>7}"
         f"{'win':>5}{'entrée':>7}{'open%':>6}{'persist':>8}{'CPTE':>8}{'C_OOS':>7}{'score':>6}")
    print(h); print("─" * len(h))
    for i, x in r.head(top).iterrows():
        pz = '—' if pd.isna(x.persist) else f"{x.persist:.0f}%"
        print(f"{i+1:<2} {x.famille:<6}{x.statut:<9}{str(x.strategie)[:36]:<38}{x.n:>4}{x.tr_day:>5.1f}"
              f"{x.exp:>+6.2f}%{x.win:>4.0f}%{x.entry_med:>7}{x.open_pct:>5.0f}%{pz:>8}{x.cpte:>+7.1f}%"
              f"{x.cpte_oos:>+6.1f}%{x.score:>6.2f}")

    r.to_csv(os.path.join(HERE, 'leaderboard_all_latest.csv'), index=False)      # classement = reproductibles
    r_full.to_csv(os.path.join(HERE, 'leaderboard_all_full.csv'), index=False)   # tout (incl. non-reproductibles, flag)
    hist = os.path.join(HERE, 'leaderboard_all_history.csv')
    run_id = dt.datetime.now().isoformat(timespec='seconds')
    h2 = r[r.statut != 'search'][['famille', 'statut', 'strategie', 'n', 'tr_day', 'exp', 'exp_oos',
            'win', 'persist', 'cpte', 'cpte_oos', 'maxDD', 'score']].copy()   # suivi longitudinal = curées
    h2.insert(0, 'couvre', f"{dates[0]}..{dates[-1]}"); h2.insert(0, 'n_days', nd); h2.insert(0, 'run', run_id)
    h2.to_csv(hist, mode='a', header=not os.path.exists(hist), index=False)
    print(f"\n→ leaderboard_all_latest.csv (classement REPRODUCTIBLE) | leaderboard_all_full.csv (tout) "
          f"| leaderboard_all_history.csv (suivi curées)")


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--top', type=int, default=100)
    ap.add_argument('--status', default=None, help='filtrer : deployed | candidate | archived')
    ap.add_argument('--keep-obsolete', action='store_true', help='ne pas retirer les obsolètes/non-reproductibles')
    ap.add_argument('--no-persist', action='store_true', help='saute le walk-forward (rapide)')
    ap.add_argument('--open-max', type=int, default=40, help="max %% d'entrées à l'ouverture (reproductibilité live)")
    a = ap.parse_args(); main(a.top, a.status, a.keep_obsolete, not a.no_persist, a.open_max)
