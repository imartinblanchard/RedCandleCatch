# Résultats de recherche — live_lab

Index des études menées sur **nos données live uniquement** (`data/collected_live/`).
Règle : [valider sur le live seulement](../../..) — jamais pit_gappers/backtests historiques
(univers curé = edges artefacts). Toute comparaison inclut le **P&L compte** (sizing contraint
capital, fonction du nb de trades/jour et du risque).

> ⚠️ **~19 séances** au moment de ces études → des milliers de combos = **faux positifs garantis**.
> Tout ici = **hypothèses à surveiller/forward-tester**, pas des edges prouvés. Garde-fous appliqués :
> OOS train/test + exp>0 sur les 2 moitiés de la période + non-fragile (sans top-3) + n≥20.

## Organisation
```
live_lab/
  backtest.py          moteur (simulate + config LIVE)  ← ne pas déplacer
  leaderboard.py       suivi auto (cron 18:20)          ← ne pas déplacer
  render_leaderboard_html.py  visuel auto               ← ne pas déplacer
  studies/   scripts de recherche one-off (voir ci-dessous)
  results/   CSV complets (gitignorés) + runs/*.txt (tableaux lisibles, versionnés) + ce README
```
Lancer une étude : `python research/live_lab/studies/<script>.py` (depuis la racine du projet).

## Études (script → sortie lisible → conclusion → mémoire)

| Script (`studies/`) | Sortie `results/` | Conclusion | Mémoire |
|---|---|---|---|
| `strategy_search.py` | `runs/strategy_search.txt`, `strategy_search_results.csv` | 1440 combos (gap×heures×repli×capit×sortie), 126 robustes → 3 archétypes | `carnet-strategies-candidates` |
| `strategy_search_indicators.py` | `runs/strategy_search_indicators.txt`, `strategy_search_indic_results.csv` | 11520 combos + indicateurs (HOD/vert/VWAP), 1023 robustes, 213 équilibrées | `carnet-strategies-candidates` |
| `indicators_test.py` | `runs/indicators_test.txt` | **HOD-en-séance** = seul indicateur qui aide (toutes bases) ; VWAP-above/above-open tuent | `carnet-strategies-candidates` |
| `capit_test.py` | `runs/capit_test_grille.txt` | Capitulation : garder/durcir (pic ~1,5), pas enlever | `capit-filtre-valide-live` |
| `capit_minbars_test.py` | `runs/capit_minbars_test.txt` | `capit_min_bars` **inerte** (2-6 identiques) | `capit-filtre-valide-live` |
| `accel_alt_test.py` | `runs/accel_alt_test.txt` | Définitions alt. d'accélération : toutes pires que le ratio moitié/moitié | `capit-filtre-valide-live` |
| `diagnose_gap.py` | `runs/diagnose_gap.txt` | Écart backtest/réel = SÉLECTION (pas les ordres) ; cause racine = bug volume ×100 | `ecart-backtest-live-selection`, `bug-volume-100x-terminator` |
| `why_missed.py` | (stdout) | Les gagnants ratés : pb_dvol temps réel 100× trop petit (bug) | `bug-volume-100x-terminator` |
| `volume_realtime_vs_posthoc.py` | (stdout) | **Volume live = exactement 100× trop petit** → bug d'unités (lots IB) | `bug-volume-100x-terminator` |
| `deep_dive_candidates.py` | `runs/deep_dive_candidates.txt` | Approfondissement des pistes + P&L compte | `pistes-sweep-live-21-10` |
| `edge_nu_on_live.py` | (stdout) | L'« edge nu » de pit NE tient PAS sur le live | `edge-repli-nu-ouverture` |
| `exit_study.py`, `extend_exit.py`, `pm_opportunity.py` | — | études antérieures (sorties/after-hours/PM) | — |
| `build_liquid_universe.py` | `liquid_universe.csv` | Univers liquide RTH séance-entière (⚠️ look-ahead) ; moitié de l'univers trade <30% des min | `univers-liquide-prefiltre` |
| `strategy_search_liquid.py` | `strategy_search_liquid_results.csv` | Recherche sur univers liquide (look-ahead) : filtrer TRIPLE l'exp/tr (+0,96→+3,2%), 1 seule robuste | `univers-liquide-prefiltre` |
| `build_liquid_universe_pm.py` | `liquid_universe_pm.csv` | Fréquence PM CAUSALE (pm/latepm/near × frac) ; PM très clairsemé (médiane pm_frac 0,01) | `recherche-frequence-pm-causale` |
| `build_pm_consec_table.py` | `pm_consec_table.csv` | Minutes PM CONSÉCUTIVES (max_consec + reachK) ; K=30 atteint par 6% des ticker-jours ~07:22 | `recherche-frequence-pm-causale` |
| `strategy_search_liquid_pm.py` | `strategy_search_liquid_pm_results.csv`, `runs/search_liquid_pm.txt` | Recherche sur univers PM-causal : **15 robustes** (famille gap5-50/10:00/repli12/HOD), meilleure latepm02/EOD +29% CPTE | `recherche-frequence-pm-causale` |
| `rank_stability_pm.py` | `rank_stability_pm.csv` | Classe les 15 PM-robustes par stabilité (e_trim sans 3 meilleurs, maxDD, dHalf, win) | `recherche-frequence-pm-causale`, `preferer-stabilite-sur-rendement` |
| `strategy_search_pm_entry.py` | `strategy_search_pm_entry_results.csv` | Entrées PM dès 04:00 gatées par K min consécutives (recent_active=1.0/win=K), anti-couteau neutralisé | `recherche-frequence-pm-causale` |

## Enseignements transversaux (au 25/10, 19 séances)
- **`trail 10/2` bat `hold-to-EOD` sur le live** (151/213 candidates équilibrées en trail).
- **HOD-en-séance** (le plus-haut d'origine du repli fait en RTH, pas en pré-marché) = meilleur filtre trouvé.
- **repli 8%** dominant ; deux régimes de gap marchent (serré 5-10 sélectif ; large 5-50 fréquent).
- Top équilibré : **S1+HOD** `gap 5-10 · RTH · repli 8% · capit 2.0 · HOD-RTH · trail 10/2` (t=4,7, pf 33, moitiés ~+5% chacune).
- Candidates suivies automatiquement par `leaderboard.py` (variantes ⭐/⭐⭐/⭐⭐⭐).
