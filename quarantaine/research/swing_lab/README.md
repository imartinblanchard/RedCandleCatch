# nvda_lab — recherche SWING daily sur un seul titre (NVDA)

Labo **autonome** pour une méga-cap, **distinct** de l'univers live des gappers (`live_lab`/
`indicator_lab` tournent sur `data/collected_live/`, des small-caps 3-20$ ; NVDA n'y est pas).

## Données
- Source : **Alpaca SIP historique**, bougies **daily**, **SPLIT-ADJUSTED** (NVDA = split 10:1 en
  juin 2024, sinon rupture de prix artificielle).
- Isolées dans `data/research/nvda/nvda_daily.parquet` (PAS `collected_live/`).
- Récupérer / rafraîchir : `python -m research.nvda_lab.fetch_nvda [--years 3] [--ticker NVDA]`.

## Fichiers
| Fichier | Rôle |
|---|---|
| `fetch_nvda.py` | Télécharge l'historique daily (Alpaca, split-adjusted) → `data/research/nvda/`. |
| `engine.py` | Backtest swing long/flat, causal (position au close j, exécutée j+1). Métriques + **buy & hold**. |
| `signals.py` | Stratégies swing (`REGISTRY`) : sma/ema cross, donchian, trend_pullback, rsi_meanrev, momentum. |
| `studies/swing_compare.py` | Compare toutes les stratégies **vs BUY & HOLD**, classé par CAGR. |
| `results/` | Sorties CSV. |

## Règle d'or (un seul titre)
Le benchmark EST le **buy & hold** — affiché d'office. Sur un titre en fort trend, le timing bat
rarement la détention ; un « ✅ bat le B&H » est le plus souvent du **sur-ajustement** (1 titre +
3 ans ≈ aucune indépendance statistique → hypothèses, jamais des vérités).

## État (30/10/2026)
757 séances (2023-10-25 → 2026-10-30). **Aucune** stratégie swing ne bat le B&H :
B&H +387% (CAGR 69%, maxDD −37%) ; meilleure swing = sma_cross 50/200 +193% (CAGR 43%, maxDD −28%).
Les stratégies réduisent un peu le drawdown mais abandonnent ~la moitié du gain. Résultat attendu.

## Usage
```bash
source .venv/bin/activate
python -m research.nvda_lab.fetch_nvda --years 3     # (ou --ticker XXX pour un autre nom)
python -m research.nvda_lab.studies.swing_compare
```
