# indicator_lab — stratégies d'entrée par INDICATEURS (labo frère de live_lab)

Explore des entrées **complètement différentes du repli-depuis-HOD** de `live_lab` :
des **combinaisons d'indicateurs** (VWAP, EMA, RSI, MACD, Bollinger, ORB, stochastique…).

**Principe DRY** : on réutilise `research/live_lab` pour tout ce qui n'est pas l'entrée —
chargement des données (`bt.load_groups`, mêmes `data/collected_live/bars-*.parquet`),
mécanique de **sortie/P&L** (`bt._pnl` : stop / trail / eod), split **OOS** (`bt.oos_split`),
et **sizing portefeuille** (`leaderboard.portfolio`, CPTE %). Seul le DÉCLENCHEUR d'entrée change.

## Règles (identiques au reste du projet)
- **Validation LIVE uniquement** (`collected_live`) — jamais pit_gappers/historique.
- **Causal** : un indicateur à la barre `i` n'utilise que les barres `<= i` (pas de look-ahead).
- **CPTE toujours affiché** (full + OOS + annualisé pommes-avec-pommes).
- **Stabilité > rendement** : on classe sur la robustesse (OOS, e_trim, DD), pas le CPTE brut.
- Petit n (~23 séances) ⇒ tout résultat = **hypothèse**, pas un déploiement.

## Fichiers
| Fichier | Rôle |
|---|---|
| `indicators.py` | Indicateurs vectorisés causaux sur OHLCV 1-min (`compute(g)` → dict d'arrays). |
| `signals.py` | Archétypes d'entrée = combinaisons d'indicateurs. `REGISTRY` = {nom: fn}. |
| `engine.py` | Moteur : `simulate(groups, nom, P)` → trades ; `evaluate(df, …)` → stats+CPTE. Réutilise `bt._pnl`. |
| `search.py` | Grille archétype × gap × fenêtre × rvol × sortie, avec robustesse. → `results/`. |
| `studies/` | Analyses ponctuelles. |
| `results/` | Sorties CSV. |

## Indicateurs disponibles (données = OHLCV 1-min SEULEMENT)
EMA 9/20/50, VWAP + bandes σ, MACD, RSI, stochastique, ROC, OBV, Bollinger (+largeur),
ATR, RVOL, ORB (range d'ouverture), HOD/gap.
**Impossible** (pas la donnée) : bid/ask, spread, carnet L2, flux d'ordres, tick, options.

## Archétypes (`signals.py`, 10)
- `vwap_reclaim` — reprise au-dessus du VWAP sur volume.
- `ema9_pullback` — tendance 9>20>VWAP, repli sur la 9 EMA, rebond vert.
- `orb_breakout` — cassure fraîche du plus-haut du range d'ouverture, sur volume, > VWAP.
- `rsi_bounce` — RSI ressort du survendu, > VWAP.
- `macd_cross` — croisement MACD haussier filtré RSI, > VWAP.
- `bb_breakout` — compression de Bollinger puis cassure de la bande haute.
- `keltner_breakout` — cassure du canal de Keltner (EMA20 + mult·ATR), sur volume.
- `atr_breakout` — cassure de volatilité (clôture > clôture préc. + k·ATR), > VWAP.
- `obv_divergence` — divergence haussière prix/OBV (nouveau plus-bas prix NON confirmé par l'OBV).
- `bullish_engulfing` — avalement haussier (corps vert englobe la rouge précédente), > VWAP.

## Usage
```bash
source .venv/bin/activate
python -u -m research.indicator_lab.engine     # smoke-test : les 6 archétypes, réglages par défaut
python -u -m research.indicator_lab.search      # grille complète (lancer en background)
```

## Univers de test (RÈGLE)
L'univers = **tous les titres (tous gaps, 0 à +2600%) qui passent le FILTRE DE FRÉQUENCE
pré-marché** (`engine.liquid_groups`, `latepm_frac>=0.20` = actif ≥20% des min 8:00-9:30 = le
filtre déployé live), **sans bande de gap**. On reste dans les titres tradables live. `price 3-20$`
conservé (zone exécutable). Univers = **2559 ticker-jours** (sur 15556 collectés).

## État
Fondation posée le 30/10/2026.
- **Ancien univers** (gap 5-50, NON freq-filtré) : les 10 archétypes TOUS négatifs, 0 robuste.
- **Univers freq-filtré (tous gaps)** : les 10 passent TOUS positifs en naïf (bb_breakout
  +1,64%/t7,7/OOS+1,69, vwap_reclaim +1,45%/CPTE+12,6%). **Driver = l'univers liquide, pas
  l'indicateur** (même leçon que le repli).
⚠️ Naïf = 47-58 tr/j (non-exécutable) + in-sample 23 j. `search.py` cherche la version SÉLECTIVE
robuste. `e_trim` retiré du garde dur (pas révélateur à petit n).
