# Démarrage dashboard + terminator

Depuis `/home/martin/dev/stock-journal-long`, dans **deux terminaux** (il faut lancer les
deux — le dashboard écrit le fichier signal que le terminator lit).

```bash
cd /home/martin/dev/stock-journal-long
source .venv/bin/activate
```

## 1. Dashboard (scanner)
Écrit le fichier signal `data/computed/redcandlecatch-eligible-YYYY-MM-DD.json`.

```bash
python -m bot.redcandlecatch_dashboard          # normal
python -m bot.redcandlecatch_dashboard --now    # ignore le check d'heure (test)
```

## 2. Terminator (exécuteur)
Lit le fichier signal écrit par le dashboard.

```bash
python -m bot.redcandlecatch_terminator            # PAPER (aucun ordre réel)
python -m bot.redcandlecatch_terminator --live     # LIVE (ordres IBKR RÉELS)
python -m bot.redcandlecatch_terminator --once     # un seul cycle (debug)
```

## Rappels
- Lancer **le dashboard d'abord**, puis le terminator (sinon pas de fichier signal à lire).
- `--live` passe des **ordres réels** sur le compte IBKR.
- Vérifier avant : IB Gateway up (`systemctl --user status ibgw.service`) et port 4001 ouvert.
