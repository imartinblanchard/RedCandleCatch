# research/intraday_gappers/ — gappers INTRADAY (post-ouverture)

Module **isolé** pour tester une extension de la stratégie RedCandleCatch : capter aussi les
titres qui entrent dans la bande **+10-20%** *après* l'ouverture 9:30 (pas seulement
au plus-haut du pré-marché).

## Pourquoi isolé
Le bot RedCandleCatch actuel mesure le gap sur le **plus-haut du pré-marché (04:00-09:30)**.
Un titre ~plat en PM qui court à +15% en séance ne devient jamais éligible. Ce module
cherche ces « runners post-ouverture ». Il **ne touche à AUCUNE donnée existante** :
- écrit uniquement dans `research/intraday_gappers/data/`
- ne modifie jamais `research/gappers.json`, `candles.parquet`, `bars_cache/`
- réutilise les clés Alpaca (`bot.config`) en lecture seule

## Étapes
| Étape | Script | Sortie |
|-------|--------|--------|
| 1. Screen | `screen_intraday.py` | `data/intraday_gappers.json` — ticker-jours avec gap MATINAL (09:30-12:00) 10-20%, prix 3-20, + flag PM vs post-open |
| 2. Bougies | `fetch_intraday.py` | `data/bars_1min.parquet` — 1-min du sous-ensemble |
| 3. Backtest | `backtest_intraday.py` | rejoue le dip −6% ; compare PM-gappers vs post-open runners |

## Définitions
- `pm_gap` = (plus-haut 04:00-08:59 − clôture veille) / clôture veille  (l'ancien critère)
- `morning_gap` = (plus-haut **09:00-11:59** − clôture veille) / clôture veille  (le nouveau)
- **post-open runner** = `pm_gap < 10%` MAIS `morning_gap ∈ [10,20]%` → le cas que le bot rate.

## ⚠️ Limites
- Screen sur bougies **1H** (comme l'ancien) → la frontière 9:30 est approximative (la
  bougie 9h couvre 09:00-10:00). Assez pour quantifier ; l'étape 2 (1-min) tranche précisément.
- Biais du survivant (Alpaca = actifs actuels), comme le projet RedCandleCatch. Borne supérieure.

## ✅ RÉSULTAT (2026-09-16) — edge validé OOS
Screen : 12 539 ticker-jours en bande 10-20% le matin, dont **10 433 post-open** (gap PM
<10%) = le cas raté par le bot (83%). Sous-ensemble liquide (vol matinal ≥500K) : 3147
ticker-jours → bougies 1-min récupérées (`bars_1min.parquet`, 2M bougies).

**Le dip −6% (calibré micro-caps) rate ces runners plus calmes** (29 trades, non signif.).
Sweep du dip → l'optimum est **−2%** :
| dip | n | exp/tr | pf | t |
|-----|---|--------|-----|---|
| −2% | 853 | +1,76% | 2,00 | 8,7 |
| −3% | 317 | +1,69% | 1,86 | 4,8 |
| −6% | 29 | +0,91% | 1,34 | 0,7 |

**Validation OOS** (train déc-avr / test mai-août), dip −2% :
TRAIN n=431 +1,56% pf1,87 t=5,7 | **TEST n=422 +1,97% pf2,13 t=6,7** → tient hors échantillon.

**Conclusion** : les runners post-ouverture (gap matinal 10-20%, liquides ≥500K) + **dip
−2%** = edge réel, pf ~2,0, ~5 trades/jour. Distinct du bot micro-cap (dip −6%). Le dip
doit s'adapter à la volatilité (leçon récurrente). Réserves : biais survivant (borne sup),
fills parfaits supposés, commissions à 1 action. Prochaine étape : intégrer un scan
post-ouverture (gap matinal) + dip adaptatif dans le bot, ou en faire une 2e stratégie.
