"""Fichier de signaux partagé entre le SCANNER (dashboard) et l'EXÉCUTEUR (terminator).

Le dashboard scanne en continu et écrit les titres éligibles ici ; l'exécuteur lit
ce fichier à chaque cycle, surveille les prix et déclenche lui-même les entrées.

STICKY : une fois un titre ajouté, il reste dans la liste toute la journée (on ne
réécrase pas son snapshot d'origine, on ne le retire pas) — évite le flapping si son
gap oscille autour de 50%.  Un fichier par jour : redcandlecatch-eligible-YYYY-MM-DD.json.
"""
from __future__ import annotations
import json
from datetime import date
from pathlib import Path
from typing import Dict, Optional

COMPUTED = Path(__file__).resolve().parent.parent / 'data' / 'computed'


def path(day: Optional[str] = None) -> Path:
    d = day or date.today().isoformat()
    return COMPUTED / f'redcandlecatch-eligible-{d}.json'


def load(day: Optional[str] = None) -> Dict[str, dict]:
    p = path(day)
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:
            return {}
    return {}


def upsert(ticker: str, info: dict, day: Optional[str] = None) -> bool:
    """Ajoute le titre s'il est absent (STICKY : ne réécrase jamais un snapshot
    existant). Retourne True si c'est un NOUVEAU titre ajouté, False sinon."""
    ticker = ticker.upper()
    d = load(day)
    if ticker in d:
        return False
    d[ticker] = info
    p = path(day)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(d, indent=2))
    return True


def write_all(elig: Dict[str, dict], day: Optional[str] = None) -> None:
    """Écrit tout le dict (merge sticky : conserve les titres déjà présents)."""
    d = load(day)
    added = False
    for tk, info in elig.items():
        tk = tk.upper()
        if tk not in d:
            d[tk] = info; added = True
    if added or not path(day).exists():
        p = path(day)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(d, indent=2))
