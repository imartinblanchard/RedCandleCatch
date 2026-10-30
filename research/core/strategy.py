#!/usr/bin/env python3
"""Contrat COMMUN pour toute stratégie candidate, toutes familles confondues.

Une Strategy ne décrit QUE : son identité + comment produire ses trades. Le moteur et
l'univers lui appartiennent (cachés dans `sim`), et le leaderboard la mesure sans savoir
comment elle est calculée. Ajouter une famille future = fournir des Strategy qui respectent
ce contrat, rien d'autre à changer dans l'agrégateur.

Contrat de `sim` : sim(groups) -> DataFrame de trades avec AU MOINS les colonnes
    ticker, date, entry_min, pnl   (c'est tout ce dont leaderboard.portfolio a besoin).
`groups` reçus par sim sont DÉJÀ filtrés sur l'univers (l'agrégateur applique `universe`).
"""
from dataclasses import dataclass
from typing import Callable


@dataclass
class Strategy:
    name: str                       # libellé affiché (unique)
    family: str                     # 'repli' | 'indic' | … (famille/labo d'origine)
    sim: Callable                   # (groups_filtrés) -> trades_df (ticker,date,entry_min,pnl)
    stop: float = 0.10              # stop % (pour le sizing du portefeuille)
    universe: str = 'complet'       # nom d'univers, RÉSOLU par l'agrégateur (cf leaderboard_all)
    status: str = 'candidate'       # 'deployed' | 'candidate' | 'archived'
    notes: str = ''                 # mémo court (ex. lien vers une mémoire, caveat)
