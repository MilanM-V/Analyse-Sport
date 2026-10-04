"""Le simulateur doit refléter la version actuelle du moteur (features, [betting], modèles)."""
import json
import os
import re

from nhl.sim.version import current_version

HTML = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "simulateur.html")


def test_simulator_matches_engine_version():
    html = open(HTML, encoding="utf-8").read()
    m = re.search(r"/\*DATA_START\*/(.*?)/\*DATA_END\*/", html, flags=re.S)
    assert m, "marqueurs de données absents de simulateur.html"
    assert json.loads(m.group(1)).get("version") == current_version(), (
        "simulateur.html est périmé : lancer `python nhl/scripts/export_simulator_data.py`")
