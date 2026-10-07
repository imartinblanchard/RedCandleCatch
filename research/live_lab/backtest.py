#!/usr/bin/env python3
"""LABO DE RECHERCHE sur les données IBKR captées EN DIRECT (data/collected_live/).

But (Martin, 24/09) : tester la stratégie LIVE (repli+capitulation, v3) sur nos propres
données, MAIS aussi balayer d'autres paramètres de la MÊME stratégie — et faire ressortir
des combinaisons gagnantes auxquelles on n'aurait pas pensé.

Données (produites par bot/fetch_universe_bars, à lancer après clôture) :
  data/collected_live/bars-YYYY-MM-DD.parquet   ticker,date,datetime(HH:MM),o,h,l,c,v  (v en actions)
  data/collected_live/meta-YYYY-MM-DD.json      {ticker: {prev_close, band, float_shares, inst_pct, market_cap, first_seen}}

FIDÉLITÉ AU BOT LIVE (bot/redcandlecatch_terminator._retrace_signal) : quand params == LIVE,
le backtest = le bot. Repli >=8% du HOD (one-shot causal), capit vol 2e/1re moitié >1.3, dvol
repli >=300K, gap 5-10, prix 3-20, séance seulement, HOLD-TO-EOD + STOP -10%. Aucun look-ahead.

STRUCTURE DU BALAYAGE (choix Martin 24/09) : CŒUR croisé (repli×capit×dvol×gap×sortie) +
MARGES 1-D (float, rvol, rotation, inst%, prix, heure, stop, vwap, green, max_drop) — chaque
marge fait varier UN axe, le reste = LIVE. Évite l'explosion combinatoire et les faux positifs.

Usage :
  python research/live_lab/backtest.py            # baseline + cœur + marges + découverte
  python research/live_lab/backtest.py --baseline # config live exacte seulement
  python research/live_lab/backtest.py --grid     # cœur croisé + marges 1-D seulement
  python research/live_lab/backtest.py --slices   # moteur de découverte seulement
  python research/live_lab/backtest.py --full      # cœur étendu (plus lent)
  python research/live_lab/backtest.py --no-slip   # P&L brut (sans slippage)
  python research/live_lab/backtest.py --min-n 30  # seuil de trades TEST pour "recommander"
"""
import os, sys, glob, json, argparse, itertools
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
DATA = os.path.join(ROOT, 'data', 'collected_live')

# ─────────────────────────── CONFIG LIVE EXACTE (référence) ───────────────────────────
LIVE = dict(
    gap_min=5.0, gap_max=10.0,
    price_min=3.0, price_max=20.0,
    float_min=None, float_max=None,        # float inconnu passe ; pas de plafond (comme le bot)
    retrace_pct=0.08,
    capit_min_bars=4,
    capit_ratio=1.3,                       # vol 2e moitié / 1re moitié du repli DOIT dépasser (-1 = off)
    pullback_dvol_min=300_000,
    bar_dvol_min=0,                        # $vol de la bougie d'ENTRÉE elle-même
    entry_start=570, entry_end=955,        # 09:30 -> 15:55
    one_shot=True,
    # ── LIQUIDITÉ LOCALE (causale, au moment de l'achat) — répond à "tradable maintenant ?" ──
    recent_window=10,                      # fenêtre (min) pour la liquidité récente
    recent_dvol_min=0,                     # $vol MOYEN/min sur les recent_window dernières minutes
    active_frac_min=0,                     # fraction min de minutes ACTIVES (v>0) depuis l'ouverture
    # ── filtres ADDITIONNELS (tous neutres par défaut => LIVE reste fidèle) ──
    rvol_min=0,                            # volume relatif intraday de la bougie d'entrée (v/moy. avant)
    float_rot_min=0,                       # rotation du float : actions cumulées / float (turnover)
    inst_max=None,                         # plafond % institutionnel
    ticker_len_min=None, ticker_len_max=None,  # longueur du symbole (4 = Nasdaq small-cap ; 1-3 = NYSE gros)
    max_drop=None,                         # anti-couteau : refuser si repli déjà > X%
    require_green=False,                   # n'entrer que sur une bougie verte (rebond confirmé)
    vwap_side=None,                        # 'above' / 'below' : position vs VWAP courant
    cat_min=0,                             # PROXY CATALYSEUR : rvol*(1+rotation float) ; activité anormale
    require_news=None,                     # None / 'day' (news le jour) / 'before' (news AVANT l'entrée)
    # ── sortie ──
    exit_mode='eod',                       # 'eod' (hold+stop), 'trail' (act+trail), 'tp' (take-profit)
    stop_pct=0.10, activate_pct=0.10, trail_pct=0.02, tp_pct=0.20,
    eod=955,
)

def hhmm(m): return f"{int(m)//60:02d}:{int(m)%60:02d}"

NEWS = {}   # {(ticker, date): [minutes ET des articles ce jour-là]} — rempli par load_news()


# ─────────────────────────────────── CHARGEMENT ───────────────────────────────────────
def load_groups():
    barfiles = sorted(glob.glob(os.path.join(DATA, 'bars-*.parquet')))
    if not barfiles:
        print(f"❌ aucun bars-*.parquet dans {DATA}\n"
              f"   Lance d'abord (après clôture) : python -m bot.fetch_universe_bars")
        sys.exit(1)
    meta_by_td = {}
    for mf in glob.glob(os.path.join(DATA, 'meta-*.json')):
        day = os.path.basename(mf)[5:-5]
        try:
            for tk, m in json.load(open(mf)).items():
                meta_by_td[(tk, day)] = m
        except Exception as e:
            print(f"  !! meta {mf}: {e}")
    df = pd.concat([pd.read_parquet(f) for f in barfiles], ignore_index=True)
    df = df.drop_duplicates(['ticker', 'date', 'datetime'])
    groups = []
    for (tk, date), g in df.groupby(['ticker', 'date'], sort=False):
        m = meta_by_td.get((tk, date), {})
        pc = m.get('prev_close')
        if not pc or pc <= 0:
            continue
        g = g.sort_values('datetime')
        mins = (g['datetime'].str.slice(0, 2).astype(int) * 60 +
                g['datetime'].str.slice(3, 5).astype(int)).to_numpy()
        o, h, l, c, v = (g[k].to_numpy(float) for k in ('o', 'h', 'l', 'c', 'v'))
        groups.append(dict(tk=tk, date=date, pc=float(pc), mins=mins, o=o, h=h, l=l, c=c, v=v,
                           float_shares=m.get('float_shares'), inst_pct=m.get('inst_pct'),
                           band=m.get('band'), first_seen=m.get('first_seen')))
    dates = sorted({g['date'] for g in groups})
    return groups, dates


def load_news():
    """Charge data/collected_live/news-*.json (collecté par bot/fetch_universe_news).
    Retourne {(ticker, date): [minutes ET des articles datés CE jour-là]}. Causal côté backtest."""
    from datetime import datetime
    from zoneinfo import ZoneInfo
    ET = ZoneInfo('America/New_York')
    out = {}
    for nf in glob.glob(os.path.join(DATA, 'news-*.json')):
        day = os.path.basename(nf)[5:-5]
        try:
            data = json.load(open(nf))
        except Exception:
            continue
        for tk, arts in data.items():
            mins = []
            for a in arts:
                ts = a.get('time_utc')
                if not ts:
                    continue
                try:
                    dtt = datetime.fromisoformat(ts.replace('Z', '+00:00')).astimezone(ET)
                except Exception:
                    continue
                if dtt.date().isoformat() == day:        # article réellement daté de ce jour
                    mins.append(dtt.hour * 60 + dtt.minute)
            if mins:
                out[(tk, day)] = sorted(mins)
    return out


# ─────────────────────────────────── SORTIE / P&L ─────────────────────────────────────
def slip_of(p):
    return max(0.0015, 0.015 / p)


def _exit_price(g, i, P):
    mins, h, l, c = g['mins'], g['h'], g['l'], g['c']
    e = float(c[i]); stop = e * (1 - P['stop_pct']); eod = P['eod']
    if P['exit_mode'] == 'eod':
        last = e
        for j in range(i + 1, len(c)):
            if mins[j] >= eod: break
            if l[j] <= stop: return stop
            last = c[j]
        return last
    if P['exit_mode'] == 'trail':
        act = e * (1 + P['activate_pct']); peak = e; activ = False; last = e
        for j in range(i + 1, len(c)):
            if mins[j] >= eod: break
            if not activ:
                if l[j] <= stop: return stop
                if h[j] > peak: peak = h[j]
                if h[j] >= act: activ = True
            else:
                ts = peak * (1 - P['trail_pct'])
                if l[j] <= ts: return ts
                if h[j] > peak: peak = h[j]
            last = c[j]
        return last
    if P['exit_mode'] == 'tp':
        tp = e * (1 + P['tp_pct']); last = e
        for j in range(i + 1, len(c)):
            if mins[j] >= eod: break
            if l[j] <= stop: return stop
            if h[j] >= tp: return tp
            last = c[j]
        return last
    raise ValueError(P['exit_mode'])


def _pnl(g, i, P, slip):
    e = float(g['c'][i]); ex = _exit_price(g, i, P)
    if slip:
        s = slip_of(e); ef = e * (1 + s); xf = ex * (1 - s)
        return (xf - ef) / ef * 100
    return (ex - e) / e * 100


# ─────────────────────────── DÉTECTION D'ENTRÉE (causale) ─────────────────────────────
def _entry_index(g, P):
    mins, o, h, l, c, v, pc = g['mins'], g['o'], g['h'], g['l'], g['c'], g['v'], g['pc']
    fs = g.get('float_shares'); inst = g.get('inst_pct')
    # gates par ticker-jour (constantes)
    L = len(g['tk'])
    if P['ticker_len_min'] is not None and L < P['ticker_len_min']:
        return None
    if P['ticker_len_max'] is not None and L > P['ticker_len_max']:
        return None
    if P['float_min'] is not None and fs is not None and fs < P['float_min']:
        return None
    if P['float_max'] is not None and fs is not None and fs > P['float_max']:
        return None
    if P['inst_max'] is not None and inst is not None and inst > P['inst_max']:
        return None

    hod_run = np.maximum.accumulate(h)
    gap_run = (hod_run - pc) / pc * 100
    drop_run = np.where(hod_run > 0, (hod_run - c) / hod_run * 100, 0.0)
    cum_v = np.cumsum(v)
    tp = (h + l + c) / 3.0
    cum_pv = np.cumsum(tp * v)
    vwap = cum_pv / np.where(cum_v > 0, cum_v, 1.0)
    in_win = (mins >= P['entry_start']) & (mins <= P['entry_end'])
    price_ok = (c >= P['price_min']) & (c <= P['price_max'])
    gap_ok = (gap_run >= P['gap_min']) & (gap_run <= P['gap_max'])
    crossed = drop_run >= P['retrace_pct'] * 100

    idxs = np.where(in_win)[0]
    seen_cross = False
    for i in idxs:
        if not crossed[i]:
            continue
        if P['one_shot']:
            if seen_cross:
                return None
            seen_cross = True
        if not (price_ok[i] and gap_ok[i]):
            if P['one_shot']:
                return None
            continue
        # capitulation / liquidité du repli
        hidx = int(np.argmax(h[:i + 1]))
        n_pull = i - hidx
        if n_pull < P['capit_min_bars']:
            if P['one_shot']:
                return None
            continue
        dv = v[hidx + 1:i + 1] * c[hidx + 1:i + 1]
        pb_dvol = float(dv.sum())
        half = len(dv) // 2
        a1 = dv[:half].mean() if half else 0.0
        a2 = dv[half:].mean() if len(dv) - half else 0.0
        ratio = (a2 / a1) if a1 > 0 else 0.0
        # features additionnelles (causales)
        rvol = (v[i] / (cum_v[i - 1] / i)) if (i >= 1 and cum_v[i - 1] > 0) else 0.0
        float_rot = (cum_v[i] / fs) if fs else None
        above_vwap = bool(c[i] >= vwap[i])
        green = bool(c[i] >= o[i])
        # LIQUIDITÉ LOCALE (causale) : $vol moyen/min sur la fenêtre récente + fraction active depuis open
        w = P['recent_window']; lo = max(0, i - w + 1)
        recent_dvol = float((v[lo:i + 1] * c[lo:i + 1]).mean())
        sess = (mins >= P['entry_start']) & (mins <= mins[i])
        active_frac = float((v[sess] > 0).mean()) if sess.any() else 0.0
        # PROXY CATALYSEUR (données seules) : activité anormale = rvol amplifié par la rotation du float
        cat_score = rvol * (1 + (float_rot or 0.0))
        # filtres additionnels (neutres par défaut ; float_rot permissif si float inconnu)
        ok = (pb_dvol >= P['pullback_dvol_min']
              and ratio > P['capit_ratio']
              and v[i] * c[i] >= P['bar_dvol_min']
              and (P['recent_dvol_min'] <= 0 or recent_dvol >= P['recent_dvol_min'])
              and (P['active_frac_min'] <= 0 or active_frac >= P['active_frac_min'])
              and (P['rvol_min'] <= 0 or rvol >= P['rvol_min'])
              and (P['cat_min'] <= 0 or cat_score >= P['cat_min'])
              and (P['float_rot_min'] <= 0 or float_rot is None or float_rot >= P['float_rot_min'])
              and (P['max_drop'] is None or drop_run[i] <= P['max_drop'])
              and (not P['require_green'] or green)
              and (P['vwap_side'] is None
                   or (P['vwap_side'] == 'above' and above_vwap)
                   or (P['vwap_side'] == 'below' and not above_vwap)))
        if ok:
            return dict(i=i, entry=float(c[i]), gap=float(gap_run[i]), drop=float(drop_run[i]),
                        ratio=ratio, pb_dvol=pb_dvol, n_pull=n_pull, entry_min=int(mins[i]),
                        rvol=rvol, float_rot=float_rot, above_vwap=above_vwap, green=green,
                        recent_dvol=recent_dvol, active_frac=active_frac, cat_score=cat_score)
        if P['one_shot']:
            return None
    return None


def simulate(groups, P, slip=True, news_map=None):
    rows = []
    for g in groups:
        e = _entry_index(g, P)
        if e is None:
            continue
        # NEWS (overlay recherche, causal) : minutes ET des articles Yahoo pour ce ticker-jour
        nm = news_map if news_map is not None else NEWS
        nmins = nm.get((g['tk'], g['date']), [])
        n_news = len(nmins)
        news_before = any(m <= e['entry_min'] for m in nmins)
        has_news = n_news > 0
        req = P.get('require_news')
        if req == 'day' and not has_news:
            continue
        if req == 'before' and not news_before:
            continue
        pnl = _pnl(g, e['i'], P, slip)
        fs = g.get('float_shares')
        rows.append(dict(
            ticker=g['tk'], date=g['date'], entry_time=hhmm(e['entry_min']), entry_min=e['entry_min'],
            entry=round(e['entry'], 4), gap=round(e['gap'], 1), drop=round(e['drop'], 1),
            ratio=round(e['ratio'], 2), pb_dvol=int(e['pb_dvol']), n_pull=e['n_pull'],
            rvol=round(e['rvol'], 2), float_rot=round(e['float_rot'], 3) if e['float_rot'] else None,
            above_vwap=e['above_vwap'], green=e['green'], cat_score=round(e['cat_score'], 2),
            recent_dvol=int(e['recent_dvol']), active_frac=round(e['active_frac'], 2),
            has_news=has_news, news_before=news_before, n_news=n_news,
            float_m=round(fs / 1e6, 2) if fs else None, inst_pct=g.get('inst_pct'),
            hour=e['entry_min'] // 60, pnl=round(pnl, 3)))
    df = pd.DataFrame(rows)
    if len(df):
        df['dow'] = pd.to_datetime(df['date']).dt.day_name().str[:3]
    return df


# ─────────────────────────────────── STATISTIQUES ─────────────────────────────────────
def stat(a):
    a = np.asarray(a, float); n = len(a)
    if n == 0:
        return dict(n=0, exp=0, win=0, pf=0, t=0)
    exp = a.mean(); sd = a.std(ddof=1) if n > 1 else 0.0
    t = exp / (sd / np.sqrt(n)) if sd > 0 else 0.0
    pf = a[a > 0].sum() / (-a[a < 0].sum() or 1e-9)
    return dict(n=n, exp=exp, win=(a > 0).mean() * 100, pf=pf, t=t)


def fmt(s):
    return f"n={s['n']:>4} exp={s['exp']:>+6.2f}% win={s['win']:>3.0f}% pf={s['pf']:>5.2f} t={s['t']:>+5.2f}"


def oos_split(dates):
    if len(dates) < 2:
        return None
    k = min(max(1, int(round(len(dates) * 0.7))), len(dates) - 1)
    return dates[k]


def _row_stats(t, split):
    if not len(t) or 'pnl' not in t.columns:   # filtre sans aucun trade (fréquent sur peu de jours)
        z = dict(n=0, exp=0, win=0, pf=0, t=0)
        return dict(z), dict(z), dict(z)
    s = stat(t['pnl'])
    if split:
        tr = stat(t[t.date < split]['pnl']); te = stat(t[t.date >= split]['pnl'])
    else:
        tr = te = dict(n=0, exp=0, win=0, pf=0, t=0)
    return s, tr, te


def report(label, trades, split):
    print(f"===== {label} =====")
    print(f"  ALL   {fmt(stat(trades['pnl']))}")
    if split:
        print(f"  TRAIN {fmt(stat(trades[trades.date <  split]['pnl']))}  (< {split})")
        print(f"  TEST  {fmt(stat(trades[trades.date >= split]['pnl']))}  (>= {split})")
    if len(trades):
        print(f"  trades/jour: {len(trades)/trades['date'].nunique():.2f}  |  jours: {trades['date'].nunique()}")
    print()


# ──────────────────────────────── CŒUR CROISÉ ────────────────────────────────────────
def exit_variants(full):
    v = [('eod', {}),
         ('trail10/2', dict(exit_mode='trail', activate_pct=0.10, trail_pct=0.02)),
         ('tp20', dict(exit_mode='tp', tp_pct=0.20))]
    if full:
        v += [('trail5/2', dict(exit_mode='trail', activate_pct=0.05, trail_pct=0.02)),
              ('trail10/3', dict(exit_mode='trail', activate_pct=0.10, trail_pct=0.03)),
              ('tp15', dict(exit_mode='tp', tp_pct=0.15))]
    return v


def core_axes(full):
    if full:
        return dict(retrace_pct=[0.04, 0.05, 0.06, 0.08, 0.10, 0.12, 0.15, 0.20],
                    capit_ratio=[-1, 1.0, 1.3, 1.6, 2.0],
                    pullback_dvol_min=[0, 150_000, 300_000, 600_000],
                    gap_band=[(5, 10), (10, 20), (5, 20), (5, 50), (20, 50)])
    return dict(retrace_pct=[0.05, 0.08, 0.10, 0.12, 0.15],
                capit_ratio=[-1, 1.3, 1.6],
                pullback_dvol_min=[0, 300_000, 600_000],
                gap_band=[(5, 10), (10, 20), (5, 20)])


def run_core(groups, dates, slip, min_n, full, top=25):
    axes = core_axes(full); exits = exit_variants(full)
    keys = list(axes)
    combos = list(itertools.product(*[axes[k] for k in keys], exits))
    split = oos_split(dates)
    print(f"\n########## CŒUR CROISÉ — {len(combos)} combinaisons "
          f"(repli×capit×dvol×gap×sortie, {'full' if full else 'std'}) ##########")
    print(f"(classé par t-stat TEST OOS ; TEST n>={min_n} & exp TRAIN+TEST>0 pour 'recommandable')\n")
    res = []
    for *vals, (exlabel, exupd) in combos:
        P = dict(LIVE)
        for k, val in zip(keys, vals):
            if k == 'gap_band':
                P['gap_min'], P['gap_max'] = val
            else:
                P[k] = val
        P.update(exupd)
        t = simulate(groups, P, slip)
        if len(t) == 0:
            continue
        s, tr, te = _row_stats(t, split)
        res.append(dict(repli=P['retrace_pct'], capit=P['capit_ratio'], dvol=P['pullback_dvol_min'],
                        gap=f"{P['gap_min']:.0f}-{P['gap_max']:.0f}", exit=exlabel,
                        n=s['n'], exp=round(s['exp'], 2), win=round(s['win']), pf=round(s['pf'], 2),
                        t=round(s['t'], 2), n_te=te['n'], exp_te=round(te['exp'], 2),
                        t_te=round(te['t'], 2), exp_tr=round(tr['exp'], 2)))
    rd = pd.DataFrame(res)
    if rd.empty:
        print("  (aucune combinaison ne produit de trade — dataset trop court ?)\n"); return rd
    rank = 't_te' if split else 't'
    reco = rd[(rd.n_te >= min_n) & (rd.exp_te > 0) & (rd.exp_tr > 0)].sort_values(rank, ascending=False)
    print(f"--- TOP edge OOS robuste (TEST n>={min_n}, exp TRAIN & TEST > 0) ---")
    if reco.empty:
        print("  (aucune ne franchit le seuil — NORMAL tant que le dataset est court)\n")
    else:
        print(reco.head(top).to_string(index=False), "\n")
    print("--- TOP espérance ALL (indicatif, NON validé OOS) ---")
    print(rd[rd.n >= max(5, min_n // 3)].sort_values('exp', ascending=False).head(top).to_string(index=False))
    out = os.path.join(HERE, 'core_results.csv')
    rd.sort_values('exp', ascending=False).to_csv(out, index=False)
    print(f"\n  cœur complet -> {out}")
    return rd


# ──────────────────────────── MARGES 1-D (1 axe varié) ────────────────────────────────
def marginals():
    """Chaque marge : (nom, [(label, {maj de params})]). Le reste des params = LIVE."""
    return [
        ('LIQUIDITÉ récente $/min (fenêtre 10m)', [('off', dict(recent_dvol_min=0)),
                                                   ('>=50K', dict(recent_dvol_min=50e3)),
                                                   ('>=100K', dict(recent_dvol_min=100e3)),
                                                   ('>=200K', dict(recent_dvol_min=200e3)),
                                                   ('>=500K', dict(recent_dvol_min=500e3))]),
        ('minutes actives (frac depuis open)', [('off', dict(active_frac_min=0)),
                                                ('>=30%', dict(active_frac_min=0.30)),
                                                ('>=50%', dict(active_frac_min=0.50)),
                                                ('>=70%', dict(active_frac_min=0.70)),
                                                ('>=90%', dict(active_frac_min=0.90))]),
        ('$vol bougie d\'entrée', [('off', dict(bar_dvol_min=0)), ('>=100K', dict(bar_dvol_min=100e3)),
                                   ('>=200K', dict(bar_dvol_min=200e3)), ('>=500K', dict(bar_dvol_min=500e3))]),
        ('float (actions)', [('tous', dict(float_min=None, float_max=None)),
                             ('<500K', dict(float_max=0.5e6)),
                             ('500K-1M', dict(float_min=0.5e6, float_max=1e6)),
                             ('1-5M', dict(float_min=1e6, float_max=5e6)),
                             ('5-10M', dict(float_min=5e6, float_max=10e6)),
                             ('10-20M', dict(float_min=10e6, float_max=20e6)),
                             ('20-50M', dict(float_min=20e6, float_max=50e6)),
                             ('50M+', dict(float_min=50e6))]),
        ('rvol bougie (intraday)', [('off', dict(rvol_min=0)), ('>=1.5', dict(rvol_min=1.5)),
                                    ('>=2', dict(rvol_min=2)), ('>=3', dict(rvol_min=3)),
                                    ('>=5', dict(rvol_min=5))]),
        ('rotation float (turnover)', [('off', dict(float_rot_min=0)), ('>=10%', dict(float_rot_min=0.10)),
                                       ('>=25%', dict(float_rot_min=0.25)), ('>=50%', dict(float_rot_min=0.50)),
                                       ('>=100%', dict(float_rot_min=1.0)), ('>=200%', dict(float_rot_min=2.0))]),
        ('longueur ticker', [('toutes', dict(ticker_len_min=None, ticker_len_max=None)),
                             ('1-3 (NYSE gros)', dict(ticker_len_max=3)),
                             ('4 (Nasdaq small)', dict(ticker_len_min=4, ticker_len_max=4)),
                             ('4+ (>=4)', dict(ticker_len_min=4)),
                             ('5+ (units/warrants)', dict(ticker_len_min=5))]),
        ('inst %', [('off', dict(inst_max=None)), ('<=10%', dict(inst_max=10)),
                    ('<=30%', dict(inst_max=30)), ('<=60%', dict(inst_max=60))]),
        ('prix', [('3-20', dict(price_min=3, price_max=20)), ('1-3', dict(price_min=1, price_max=3)),
                  ('3-10', dict(price_min=3, price_max=10)), ('10-20', dict(price_min=10, price_max=20))]),
        ('fenêtre horaire', [('tout 09:30-15:55', dict(entry_start=570, entry_end=955)),
                             ('1re h 09:30-10:30', dict(entry_start=570, entry_end=630)),
                             ('skip 15m 09:45+', dict(entry_start=585, entry_end=955)),
                             ('après 11:00', dict(entry_start=660, entry_end=955)),
                             ('power hour 15:00+', dict(entry_start=900, entry_end=955))]),
        ('stop', [('6%', dict(stop_pct=0.06)), ('8%', dict(stop_pct=0.08)), ('10%', dict(stop_pct=0.10)),
                  ('12%', dict(stop_pct=0.12)), ('15%', dict(stop_pct=0.15)), ('20%', dict(stop_pct=0.20))]),
        ('anti-couteau max_drop', [('off', dict(max_drop=None)), ('<=15%', dict(max_drop=15)),
                                   ('<=20%', dict(max_drop=20)), ('<=25%', dict(max_drop=25)),
                                   ('<=30%', dict(max_drop=30))]),
        ('bougie verte', [('off', dict(require_green=False)), ('verte only', dict(require_green=True))]),
        ('vwap', [('off', dict(vwap_side=None)), ('above', dict(vwap_side='above')),
                  ('below', dict(vwap_side='below'))]),
        ('proxy catalyseur (rvol×rotation)', [('off', dict(cat_min=0)), ('>=5', dict(cat_min=5)),
                                              ('>=10', dict(cat_min=10)), ('>=25', dict(cat_min=25)),
                                              ('>=50', dict(cat_min=50)), ('>=100', dict(cat_min=100))]),
        ('news Yahoo', [('off', dict(require_news=None)), ('le jour', dict(require_news='day')),
                        ('avant entrée', dict(require_news='before'))]),
    ]


def run_marginals(groups, dates, slip):
    split = oos_split(dates)
    print(f"\n########## MARGES 1-D (1 axe varié, reste = LIVE) ##########")
    print(f"  baseline LIVE : {fmt(stat(simulate(groups, LIVE, slip)['pnl']))}\n")
    for name, variants in marginals():
        print(f"  ── {name} ──")
        for label, upd in variants:
            P = dict(LIVE); P.update(upd)
            t = simulate(groups, P, slip)
            s, tr, te = _row_stats(t, split)
            extra = f"  [test n={te['n']:>3} exp={te['exp']:>+6.2f}% t={te['t']:>+4.1f}]" if split else ""
            print(f"    {label:<18} {fmt(s)}{extra}")
        print()


# ─────────────────────── MOTEUR DE DÉCOUVERTE (tranches de features) ──────────────────
def run_slices(groups, dates, slip):
    P = dict(LIVE, gap_min=5.0, gap_max=20.0, capit_ratio=-1, pullback_dvol_min=0,
             capit_min_bars=2, one_shot=True)
    t = simulate(groups, P, slip)
    split = oos_split(dates)
    print(f"\n########## MOTEUR DE DÉCOUVERTE — {len(t)} candidats "
          f"(repli 8% one-shot, gap 5-20, SANS filtre capit/dvol) ##########")
    if len(t) == 0:
        print("  (aucun candidat — dataset trop court)\n"); return t
    print(f"  base : {fmt(stat(t['pnl']))}\n")

    def slice_by(col, bins, labels):
        cats = pd.cut(t[col], bins=bins, labels=labels, right=False)
        print(f"  ── par {col} ──")
        for cat, grp in t.groupby(cats, observed=True):
            s = stat(grp['pnl'])
            if s['n'] == 0:
                continue
            te = stat(grp[grp.date >= split]['pnl']) if split else s
            print(f"    {str(cat):>14}  {fmt(s)}   [test n={te['n']:>3} exp={te['exp']:>+6.2f}%]")
        print()

    def slice_flag(col):
        print(f"  ── par {col} ──")
        for cat, grp in t.groupby(col, observed=True):
            s = stat(grp['pnl'])
            if s['n']:
                print(f"    {str(cat):>14}  {fmt(s)}")
        print()

    slice_by('hour', [9, 10, 11, 12, 13, 14, 15, 16], ['09-10', '10-11', '11-12', '12-13', '13-14', '14-15', '15-16'])
    slice_by('gap', [5, 7, 8, 10, 14, 20, 100], ['5-7', '7-8', '8-10', '10-14', '14-20', '20+'])
    slice_by('drop', [8, 10, 12, 15, 20, 100], ['8-10', '10-12', '12-15', '15-20', '20+'])
    slice_by('ratio', [0, 1, 1.3, 1.6, 2, 100], ['<1', '1-1.3', '1.3-1.6', '1.6-2', '2+'])
    slice_by('pb_dvol', [0, 150e3, 300e3, 600e3, 1e6, 1e12], ['<150K', '150-300K', '300-600K', '600K-1M', '1M+'])
    slice_by('rvol', [0, 1, 1.5, 2, 3, 5, 1e6], ['<1', '1-1.5', '1.5-2', '2-3', '3-5', '5+'])
    slice_by('recent_dvol', [0, 50e3, 100e3, 200e3, 500e3, 1e6, 1e12],
             ['<50K', '50-100K', '100-200K', '200-500K', '500K-1M', '1M+'])
    slice_by('active_frac', [0, .3, .5, .7, .9, 1.01], ['<30%', '30-50%', '50-70%', '70-90%', '90%+'])
    slice_by('n_pull', [2, 4, 6, 10, 20, 999], ['2-3', '4-5', '6-9', '10-19', '20+'])
    fr = t.dropna(subset=['float_rot'])
    if len(fr) > 10:
        print(f"  ── par float_rot (turnover) ──")
        for cat, grp in fr.groupby(pd.cut(fr['float_rot'], [0, .1, .25, .5, 1, 2, 1e6],
                                          labels=['<10%', '10-25%', '25-50%', '50-100%', '100-200%', '200%+']),
                                   observed=True):
            s = stat(grp['pnl'])
            if s['n']:
                print(f"    {str(cat):>14}  {fmt(s)}")
        print()
    fm = t.dropna(subset=['float_m'])
    if len(fm) > 10:
        print(f"  ── par float (M actions) ──")
        for cat, grp in fm.groupby(pd.cut(fm['float_m'], [0, 0.5, 1, 5, 10, 20, 50, 1e6],
                                          labels=['<0.5M', '0.5-1M', '1-5M', '5-10M', '10-20M', '20-50M', '50M+']), observed=True):
            s = stat(grp['pnl'])
            if s['n']:
                print(f"    {str(cat):>14}  {fmt(s)}")
        print()
    slice_by('cat_score', [0, 5, 10, 25, 50, 100, 1e9], ['<5', '5-10', '10-25', '25-50', '50-100', '100+'])
    t['tklen'] = t['ticker'].str.len()
    slice_flag('tklen')
    slice_flag('above_vwap')
    slice_flag('green')
    slice_flag('has_news')
    slice_flag('news_before')
    slice_flag('dow')
    out = os.path.join(HERE, 'candidates.csv')
    t.to_csv(out, index=False)
    print(f"  candidats (features + pnl) -> {out}  (charge-le pour tes propres coupes croisées)")
    return t


# ─────────────────────────────────────── MAIN ─────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--baseline', action='store_true')
    ap.add_argument('--grid', action='store_true')
    ap.add_argument('--slices', action='store_true')
    ap.add_argument('--full', action='store_true')
    ap.add_argument('--no-slip', action='store_true')
    ap.add_argument('--min-n', type=int, default=25)
    a = ap.parse_args()
    slip = not a.no_slip
    do_all = not (a.baseline or a.grid or a.slices)

    groups, dates = load_groups()
    NEWS.update(load_news())
    print(f"Dataset : {len(groups)} ticker-jours, {len(dates)} séance(s) : {dates[0]}..{dates[-1]}")
    print(f"News Yahoo chargées : {len(NEWS)} ticker-jours avec >=1 article daté du jour")
    print(f"Slippage : {'ON (max 0.15%, 1.5c/prix par côté)' if slip else 'OFF (brut)'}")
    split = oos_split(dates)
    if split is None:
        print("⚠️  1 seule séance -> pas de split OOS ; stats INDICATIVES (bruit). Accumule des semaines.")

    if a.baseline or do_all:
        print("\n########## CONFIG LIVE EXACTE (repli 8% + capit 1.3 + dvol 300K, gap 5-10, hold-EOD) ##########")
        t = simulate(groups, LIVE, slip)
        report('LIVE (redcandlecatch v3)', t, split)
        if len(t):
            cols = ['date', 'ticker', 'entry_time', 'entry', 'gap', 'drop', 'ratio', 'pb_dvol', 'n_pull', 'pnl']
            print("  Tickers qui AURAIENT tradé (config live) :")
            print(t[cols].to_string(index=False), "\n")

    if a.grid or do_all:
        run_core(groups, dates, slip, a.min_n, full=a.full)
        run_marginals(groups, dates, slip)

    if a.slices or do_all:
        run_slices(groups, dates, slip)


if __name__ == '__main__':
    main()
