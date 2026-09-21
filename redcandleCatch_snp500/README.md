# redcandleCatch_snp500 — mean-reversion daily sur le S&P 500

Transposition de l'idée RedCandleCatch (acheter le repli, protéger, laisser courir) sur un
**univers et une échéance différents** : les ~500 titres du **S&P 500**, en **journalier**.
Module **isolé** — ne touche pas au bot RedCandleCatch (intraday microcaps).

## L'idée
Sur le S&P 500, acheter les **replis** (bougies journalières rouges / baisse sur 1-3
jours), protéger avec stop + trailing, sortir avec un backstop en jours. Les titres du
S&P 500 étant bien moins volatils que les microcaps qui gappent, le « dip » est petit
(−1 à −3%) et **probablement différent par titre** (un titre calme vs volatil).

## Structure
```
redcandleCatch_snp500/
├── README.md          # ce fichier
├── data/
│   ├── sp500.json     # constituants ACTUELS du S&P 500 (Wikipedia)
│   └── daily.parquet  # bougies daily (ticker,date,o,h,l,c,v)
├── fetch_data.py      # récupère la liste + ~1 an de bougies daily (Alpaca SIP, adjustment=all)
├── engine.py          # moteur backtest daily (buy dip, stop+trail intraday, hold max, peak après entrée)
├── strategies.py      # définitions du dip : dip_fixed(%) et dip_vol(σ), × nbars jours
└── sweep.py           # balaye les entrées ; ensuite stop/trail/hold
```

## Données (v1)
- **Source** : Alpaca SIP historique, bougies **1Day**, `adjustment=all` (pas de faux
  gaps de split/dividende). Clés dans `.env` (réutilisées du projet).
- **Univers** : constituants **actuels** du S&P 500 (503 titres, Wikipedia).
- **Période** : ~1 an (récupéré 2025-09 → 2026-09), 127 352 bougies.
- **Régénérer** : `python redcandleCatch_snp500/fetch_data.py`

## ⚠️ Limites connues
- **Biais du survivant** : constituants ACTUELS → les titres sortis du S&P 500 dans
  l'année (rachetés, dégradés) sont absents. Résultats optimistes. Corrigeable avec une
  composition point-in-time (TODO).
- **1 an seulement** : un seul régime de marché. À étendre pour de la robustesse.
- **In-sample** : tout sweep de paramètres = risque de sur-ajustement → valider en OOS
  (train/test) avant d'y croire.
- **Fills** : slippage 0,1% appliqué aux 2 côtés ; le S&P 500 est liquide donc réaliste,
  mais les stops supposent un fill au niveau (approximation).

## Le dip : deux définitions comparées
- **`dip_fixed(pct, nbars)`** : `close[i]/close[i-nbars]-1 <= -pct` — même seuil % pour tous.
- **`dip_vol(k, nbars)`** : `ret_N <= -k · σ_N` où σ = écart-type glissant des rendements
  du titre (point-in-time) × √nbars — **seuil propre à chaque titre** (répond à « un dip
  différent par titre »).

## Sortie (décidée)
Stop fixe % + trailing % (le plus haut des deux, touché en intraday sur le low) +
backstop après **HOLD** jours (sortie au close). Le `peak` du trailing ne compte que les
jours **après** l'entrée (leçon du bug RedCandleCatch 15/09).

## Statut
🚧 WIP. Data récupérée, moteur + stratégies + 1er sweep d'entrée en place. Prochaines
étapes : sweep stop/trail/hold sur la meilleure entrée, puis validation OOS.
