"""
sim/version.py — Empreinte de « version du moteur » pour le simulateur.

La version change dès que l'un des éléments qui déterminent les paris change :
features (FEATURES_VERSION), stratégie (settings.toml [betting]), décote du prix
d'exécution simulé, ou modèles de prod (fichiers nhl/models/ml_model_*.pkl).

`export_simulator_data.py` l'écrit dans simulateur.html ; tests/test_simulator_version.py
échoue si le simulateur n'a pas été régénéré après un changement.
"""
import hashlib
import json
import os
import tomllib

NHL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SETTINGS = os.path.join(NHL_DIR, "config", "settings.toml")
MODELS = [os.path.join(NHL_DIR, "models", f"ml_model_{m}.pkl") for m in ("but", "ast")]


def _betting() -> dict:
    with open(SETTINGS, "rb") as f:
        return tomllib.load(f).get("betting", {})


# Décote médiane soft books → prix FR, lue dans settings.toml (partagée avec simulate_roi et le bot)
EXEC_HAIRCUT = float(_betting().get("exec_haircut", 0.94))


def current_version() -> str:
    """Empreinte courte (12 caractères hex) de la version du moteur."""
    from nhl.core.features import FEATURES_VERSION
    betting = _betting()
    h = hashlib.sha256()
    h.update(json.dumps({"features": FEATURES_VERSION, "betting": betting, "haircut": EXEC_HAIRCUT},
                        sort_keys=True).encode("utf-8"))
    for path in MODELS:
        with open(path, "rb") as f:
            h.update(hashlib.sha256(f.read()).digest())
    return h.hexdigest()[:12]
