# research/ — Backtests & données de recherche

Recherche sur la stratégie **micro-pullback momentum** (style Ross Cameron) et notre
stratégie **repli-VWAP**, backtestées sur données historiques Alpaca SIP.

## Contenu
| Chemin | Quoi |
|--------|------|
| `gappers.json` | Univers : **gap ≥10%** mesuré sur le **plus-haut du pré-marché (04:00–09:00) vs clôture veille**, prix 2–20$, déc 2025–août 2026 (voir `scripts/screener_gappers.py`, `MIN_GAP=0.10`) |
| ~~`gappers_premarket.json`~~ | ⚠️ **N'EXISTE PAS** (jamais construit). Le README l'annonçait ; en réalité `gappers.json` EST déjà l'univers PM-high. Construire cet univers dédié reste un TODO (cf FINDINGS.md). |
| `bars_cache/` | Bougies 1-min SIP par `TICKER_DATE.json` (~1400 fichiers). **Git-ignoré** (gros, re-téléchargeable) |
| `daily_cache/` | Volume quotidien moyen par ticker (pour le RVOL). Git-ignoré |
| `scripts/` | Screeners + backtests (voir ci-dessous) |

## Source des données
**Alpaca SIP** (flux consolidé tout-le-marché), historique. Fiable pour ce qu'il couvre.
Bougies 1-min via `/v2/stocks/{sym}/bars`, gappers via bougies journalières/horaires.

## Sélection de l'univers
1. Liste des actions US tradables (Alpaca `/v2/assets`, ~11 000).
2. Bougies journalières (ou horaires pour le pré-marché) sur la période.
3. Garder `(ticker, date)` si **gap ≥10%** (plus-haut PM 04:00–09:00 vs clôture veille) et **prix 2–20$**.

## ⚠️ LIMITES CONNUES (à garder en tête pour tout chiffre)
- **Biais du survivant (ASSUMÉ)** : la liste `/v2/assets` = tickers **actifs aujourd'hui**.
  Les délistés / faillites / reverse-splits entre jan et aujourd'hui sont **absents**.
  Les small-caps qui gappent meurent souvent → **on ne voit que les survivants → résultats
  optimistes**. On accepte cette limite (pas de source de tickers délistés).
- **Pas de filtre RVOL / float / news** dans l'univers de base (plus large que la vraie
  stratégie de Ross). Le float n'est pas dispo chez Alpaca ; RVOL calculable via `daily_cache`.
- **Gap mesuré sur bougies 1H** (04:00–09:00) pour `gappers.json` → le live utilise le
  1-min jusqu'à 09:30. Effet vérifié négligeable (93% des gaps identiques, cf FINDINGS
  `test_pm_window`). ✅ Bien du PM-high, PAS de l'open-gap (le PM-high est décisivement
  meilleur pour la sélection — cf FINDINGS `test_gap_def`).
- **Un seul setup par jour** backtesté (le premier de la fenêtre 7–10h).
- **Fills/slippage** non modélisés → réel serait pire, surtout sur small-caps illiquides.
- **Échantillon** : ~239 trades (micro-pullback) sur ~8 mois. L'OOS (train jan–avr / test
  mai–août) a montré que **l'edge dépend du régime** (négatif jan–avr, positif mai–août).

## Scripts principaux (`scripts/`)
| Script | Rôle |
|--------|------|
| `screener_gappers.py` | Trouve les gappers (gap à l'open) → `gappers.json` |
| `premarket_screener.py` | Gappers pré-marché (gap sur plus-haut PM) → `gappers_premarket.json` |
| `fetch_gappers_bars.py` | Télécharge les bougies 1-min des gappers → `bars_cache/` |
| `backtest_micropullback_full.py` | Micro-pullback (Ross) sur tous les gappers |
| `diag_micropullback.py` | Diagnostic : run après sortie (on sort trop tôt ?) |
| `backtest_runner.py` | Stop large + trailing runner (capture du MFE) |
| `backtest_lowerentry.py` | Entrées plus basses (dans le repli) |
| `backtest_oos.py` | Validation hors échantillon (train/test) |

Lancer : `source .venv/bin/activate && python research/scripts/<script>.py`

## Scripts de test/tuning (racine `research/`, tournent sur `candles.parquet`)
Ces scripts rejouent la **config live** (dip −5%, stop −10%, act +5%, trail 2%, gap
10-20) via le moteur `engine.py`. Chaque résultat validé est consigné dans
[../FINDINGS.md](../FINDINGS.md).

| Script | Question tranchée | Finding |
|--------|-------------------|---------|
| `test_gap_def.py` | **PM-high vs open-gap** pour la sélection | PM-high ≫ open (14/09) |
| `test_multi_entry.py` | **N trades/ticker/jour** (ré-entrées) | 2/jour = propre, 3e+ dilue (14/09) |
| `test_trail_order.py` | quelle construction d'ordre TRAIL IBKR passe | percent seul, PAS trailStopPrice (14/09) |
| `test_trail_covered.py` | confirme le TRAIL sur position détenue (compte réel) | PreSubmitted = accepté (14/09) |
| `test_pm_window.py` | fenêtre de mesure du gap 08:59 vs 09:29 | non-problème (11/09) |
| `test_gap1020_robust.py` | robustesse de la tranche gap 10-20 | 9/9 mois gagnants (11/09) |
| `test_dip_sweep.py` / `test_dip_deep.py` | profondeur du dip d'entrée | relation monotone |
| `test_trail_tight.py` / `test_exit_sweep.py` | réglage du trailing / des sorties | trail 2% dominant |
| `test_liquidite.py` / `test_regularite.py` | filtres volume PM / minutes actives | désactivés (nuisibles) |
| `test_gap_sous50.py` / `test_gap_at_open.py` / `test_gapopen_pnl.py` | variantes de gap | voir FINDINGS |
| `test_antipump.py` | filtre anti-pump (rel-vol) | désactivé (09/09) |
| `test_sizing.py` / `test_equity.py` | sizing / courbe d'équité | — |
| `test_bot_logic.py` | test unitaire de la machine à états two-phase (sans IBKR) | — |

⚠️ Les scripts qui posent de VRAIS ordres (`test_trail_order.py`, `test_trail_covered.py`)
tapent le compte **réel** (port 4001, 1 action, annulés/soldés aussitôt).
