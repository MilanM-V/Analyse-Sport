"""Configuration pytest : rend importables `nhl.*`, `shared.*` et l'import historique `config.*`."""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in (ROOT, os.path.join(ROOT, "nhl")):
    if p not in sys.path:
        sys.path.insert(0, p)


@pytest.fixture(autouse=True)
def _no_live_fr_books(monkeypatch):
    """Aucun test ne lit les vrais sites de paris ni n'envoie d'alerte Telegram.

    La lecture des books français ([fr_odds] enabled = true dans settings.toml) est désactivée
    par défaut ; un test qui en a besoin la réactive en remplaçant le réseau par des faux.
    """
    from nhl.core import fr_odds
    monkeypatch.setattr(fr_odds, "settings", lambda: fr_odds.FrConfig(enabled=False))
    monkeypatch.setattr(fr_odds, "_alert", lambda book, reason: None)
