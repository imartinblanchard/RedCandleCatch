#!/usr/bin/env python3
"""ÉTUDE D'OPPORTUNITÉ — MOMENTUM PRÉ-MARCHÉ (bougies 15 s).

Question (Martin 25/09) : quand un gapper PM SPIKE (news/momentum), y a-t-il une SUITE
exploitable ? On NE construit PAS encore l'exécution — on MESURE d'abord, sur bougies 15 s,
si après un surge le titre CONTINUE (MFE) ou REND tout (MAE). Si pas de suite -> inutile de
bâtir un bot momentum PM.

Données : data/collected_live/pm15s-*.parquet (bot/fetch_pm15s) + meta-*.json (prev_close).
Tout est CAUSAL : surge détecté sur bougies CLÔTURÉES, mesure APRÈS le surge uniquement.

Définitions :
  - SURGE = 1er instant PM (< 09:30) où le rendement sur les K dernières barres >= X%,
    avec un $volume cumulé du surge >= liq (tradable). Un seul surge/ticker-jour (le 1er).
  - Réf = close de la barre de surge. Sur les H barres suivantes :
      MFE = max(high)/réf - 1   (continuation)      MAE = min(low)/réf - 1  (retour)
  - Win path : le +TP est-il touché AVANT le -SL (dépendant du chemin).
  - Coût spread PM assumé (demi-spread) déduit du réf d'entrée pour une vue "net".

Usage : python research/live_lab/pm_opportunity.py
        python research/live_lab/pm_opportunity.py --tp 5 --sl 5 --spread-bps 50
"""
import os, sys, glob, json, argparse
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(os.path.dirname(os.path.dirname(HERE)), 'data', 'collected_live')
OPEN = 9 * 3600 + 30 * 60          # 09:30 en secondes


def secs(s):                        # 'HH:MM:SS' -> secondes du jour
    h, m, sec = s.split(':'); return int(h) * 3600 + int(m) * 60 + int(sec)


def load():
    files = sorted(glob.glob(os.path.join(DATA, 'pm15s-*.parquet')))
    if not files:
        print(f"❌ aucun pm15s-*.parquet dans {DATA}\n   Lance : python -m bot.fetch_pm15s --date <jour> --sample 40")
        sys.exit(1)
    pc = {}
    for mf in glob.glob(os.path.join(DATA, 'meta-*.json')):
        day = os.path.basename(mf)[5:-5]
        for tk, m in json.load(open(mf)).items():
            if m.get('prev_close'):
                pc[(tk, day)] = float(m['prev_close'])
    df = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True).drop_duplicates(['ticker', 'date', 'datetime'])
    return df, pc


def surges(df, pc, X, K, liq, H):
    """Détecte le 1er surge PM par ticker-jour et mesure MFE/MAE/target sur H barres suivantes."""
    rows = []
    for (tk, date), g in df.groupby(['ticker', 'date'], sort=False):
        p = pc.get((tk, date))
        if not p or p <= 0:
            continue
        g = g.sort_values('datetime')
        sec = g['datetime'].map(secs).to_numpy()
        o, h, l, c, v = (g[k].to_numpy(float) for k in ('o', 'h', 'l', 'c', 'v'))
        n = len(c)
        pm = sec < OPEN
        for i in range(K, n):
            if not pm[i]:
                break                                   # surge doit démarrer en PM
            base = c[i - K]
            if base <= 0:
                continue
            ret = (c[i] - base) / base
            dvol = float((v[i - K + 1:i + 1] * c[i - K + 1:i + 1]).sum())
            if ret >= X and dvol >= liq:
                ref = c[i]
                fwd = slice(i + 1, min(i + 1 + H, n))
                if fwd.stop <= fwd.start:
                    break
                fh, fl = h[fwd], l[fwd]
                mfe = (fh.max() - ref) / ref
                mae = (fl.min() - ref) / ref
                # path : +TP avant -SL ?
                rows.append(dict(ticker=tk, date=date, t=g['datetime'].iloc[i],
                                 pm_gap=round((ref - p) / p * 100, 1), surge_ret=round(ret * 100, 1),
                                 dvol_surge=int(dvol), ref=round(ref, 3),
                                 mfe=round(mfe * 100, 2), mae=round(mae * 100, 2),
                                 fh=fh, fl=fl, ref_px=ref))
                break                                    # 1 surge/ticker-jour
    return pd.DataFrame(rows)


def path_win(row, tp, sl):
    ref = row['ref_px']; up = ref * (1 + tp); dn = ref * (1 - sl)
    for hh, ll in zip(row['fh'], row['fl']):
        if ll <= dn:  return 0        # stop touché en premier (pessimiste : SL avant TP si même barre)
        if hh >= up:  return 1
    return 0


def report(d, tp, sl, spread):
    if len(d) == 0:
        print("  (aucun surge détecté avec ces paramètres)"); return
    d = d.copy()
    d['win'] = d.apply(lambda r: path_win(r, tp, sl), axis=1)
    # net : on entre au ref + demi-spread -> MFE/MAE amputés du spread
    net_mfe = d['mfe'] - spread * 100
    print(f"  n={len(d):>4}  MFE méd={d.mfe.median():>+5.2f}%  MAE méd={d.mae.median():>+5.2f}%  "
          f"MFE/|MAE|={d.mfe.median()/(abs(d.mae.median()) or 1e-9):>4.2f}  "
          f"win(+{tp*100:.0f}av-{sl*100:.0f})={d.win.mean()*100:>3.0f}%  "
          f"net MFE méd={net_mfe.median():>+5.2f}%")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--tp', type=float, default=5.0, help='cible %% (défaut 5)')
    ap.add_argument('--sl', type=float, default=5.0, help='stop %% (défaut 5)')
    ap.add_argument('--spread-bps', type=float, default=50.0, help='demi-spread PM assumé en bps (défaut 50=0.5%%)')
    ap.add_argument('--liq', type=float, default=30_000, help='$vol cumulé min du surge (défaut 30K)')
    a = ap.parse_args()
    tp, sl, spread = a.tp / 100, a.sl / 100, a.spread_bps / 1e4
    df, pc = load()
    ndays = df['date'].nunique(); ntk = df.groupby(['ticker', 'date']).ngroups
    print(f"Données PM 15s : {ntk} ticker-jours, {ndays} séance(s). "
          f"TP+{a.tp:.0f}%/SL-{a.sl:.0f}%, spread assumé {a.spread_bps:.0f}bps.\n")
    print("SURGE = rendement >= X%% sur K barres (15s), $vol cumulé >= liq ; mesure sur H barres après.\n")
    grid = [(0.03, 2), (0.03, 4), (0.05, 2), (0.05, 4), (0.08, 4)]   # (X, K)
    for H in (20, 40):                                               # 5 min, 10 min
        print(f"===== horizon H={H} barres (~{H*15//60} min) =====")
        print(f"  {'surge':>12}   stats")
        for X, K in grid:
            d = surges(df, pc, X, K, liq=a.liq, H=H)
            lab = f">={X*100:.0f}% en {K*15}s"
            print(f"  {lab:>12} : ", end="")
            report(d, tp, sl, spread)
        print()
    # dump du plus permissif pour coupes manuelles
    d = surges(df, pc, 0.03, 2, liq=a.liq, H=40)
    if len(d):
        out = os.path.join(HERE, 'pm_surges.csv')
        d.drop(columns=['fh', 'fl', 'ref_px']).to_csv(out, index=False)
        print(f"surges (3%/30s, H=40) -> {out}")


if __name__ == '__main__':
    main()
