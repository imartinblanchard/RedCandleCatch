# Unités des colonnes (légende) — pour lever toute confusion $ vs %

⚠️ Les colonnes ne peuvent PAS être renommées : le bot live + ~30 scripts les lisent par leur
nom exact. Cette légende sert de référence quand tu ouvres les fichiers (VisiData, tableur…).
Les valeurs sont des **nombres bruts** (aucun signe $/% affiché) — c'est ici que tu vois l'unité.

## `data/collected/bars/YYYY-MM-DD.parquet` (bougies 1-min du dataset de recherche)
| Colonne | Unité |
|---------|-------|
| `ticker` | texte |
| `date` | date |
| `datetime` | heure ET (HH:MM) |
| `o` `h` `l` `c` | **$ (dollars)** — open / high / low / close, prix ABSOLUS |
| `v` | volume (nombre d'actions) |

➡️ **PAS de % ici.** Le `o,h,l,c` sont des **prix en dollars**. (Le bot calcule lui-même le
dip `(c−o)/o` à la volée ; il n'est pas stocké.)

## `data/collected/eligibles.csv` (table maître temps réel)
| Colonne | Unité |
|---------|-------|
| `is_premarket` | booléen (True = gapper PM) |
| `added` | heure ET (HH:MM) |
| `gap` | **% (pourcent)** |
| `price` | **$ (dollars)** |
| `pm_vol` | volume | 
| `pm_minutes` | nombre de minutes |
| `chart_rating` `volume_rating` `float_rating` | note 1–5 |
| `float_shares` | nombre d'actions |
| `inst_pct` | **% (pourcent)** |
| `dollar_vol` | **$ (dollars)** — volume × prix |
| `ssr` | booléen |

## `data/computed/redcandlecatch-journal.csv` (trades)
| Colonne | Unité |
|---------|-------|
| `gap` | **%** |
| `entry` `exit` | **$ (dollars)** — prix d'entrée / sortie |
| `pnl_pct` `mfe_pct` | **%** |
| `shares` | nombre d'actions |
| `dollars` | **$ (dollars)** — taille de la position |
| `float_m` | millions d'actions |
| `inst_pct` | **%** |

## `research/candles.parquet` (historique 8 mois, enrichi) — LE PLUS AMBIGU
| Colonne | Unité |
|---------|-------|
| `o` `h` `l` `c` | **$ (dollars)** — prix ABSOLUS |
| `vwap` `vwap_up` `vwap_dn` `ema9` `ema20` `ema200` | **$** |
| `prev_close` `dayopen` `hod` `lod` `atr14` | **$** |
| `macd` `macd_sig` `macd_hist` | $ (dérivés de prix) |
| `v` `cumvol` `vol_sma5` | volume |
| `rvol` `mom80` | ratio (sans unité) |
| **`perf_open_pct`** | **% vs `dayopen`** (open du jour, 04:00) |
| **`perf_close_pct`** | **% vs `prev_close`** (clôture de la veille = le gap) |
| **`range_pct`** | **%** — (high−low)/close |
| **`body_pct`** | **%** — \|close−open\|/close |
| **`upwick_pct`** | **%** — mèche haute / close |

➡️ **RÈGLE COHÉRENTE (19/09)** : toute colonne en **%** finit par **`_pct`**. Tout le reste
sans suffixe (`o,h,l,c,vwap,ema*,prev_close`…) est un **prix en $**. Renommage `perf_open`→
`perf_open_pct` et `perf_close`→`perf_close_pct` fait partout (fichier + `build_table.py`,
`strategies.py`, `engine.py`) — testé, rien de cassé.
