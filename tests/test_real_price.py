"""Prix réaliste du simulateur (nhl/sim/real_price.py) : cote Winamax reconstituée."""
import math

import numpy as np
import pandas as pd

from nhl.sim.real_price import add_real_price, calibration_ratios, describe, load_ratios, save_ratios


def _calib() -> pd.DataFrame:
    """Calibration synthétique : Winamax = Pinnacle « Oui » sur les lignes couvertes, 1,10 × médiane US
    sur les buteurs sans Pinnacle (12 lignes dans la tranche 4,5-7), 0,85 × médiane US sur les passes."""
    rows = [dict(gameId=1, date="2026-10-01", market="but", winamax=5.5, soft_median=5.0, pin_yes=None, pin_no=None)] * 12
    rows += [dict(gameId=2, date="2026-10-02", market="but", winamax=3.0, soft_median=2.9, pin_yes=3.0, pin_no=1.36)] * 12
    rows += [dict(gameId=2, date="2026-10-02", market="ast", winamax=2.0, soft_median=2.2, pin_yes=2.0, pin_no=1.8),
             dict(gameId=3, date="2026-10-03", market="ast", winamax=1.7, soft_median=2.0, pin_yes=None, pin_no=None)]
    return pd.DataFrame(rows)


def test_ratios_survive_the_json_file(tmp_path):
    path = tmp_path / "sim_price.json"
    data = save_ratios(_calib(), str(path))
    assert data["games"] == 3 and data["dates"] == ["2026-10-01", "2026-10-03"]
    assert load_ratios(str(path)) == calibration_ratios(_calib())


def test_real_price_rules(tmp_path):
    path = tmp_path / "sim_price.json"
    save_ratios(_calib(), str(path))
    p = pd.DataFrame([
        # marché, médiane US, Pinnacle Oui, no-vig (Pinnacle des deux côtés)
        ("but", 2.9, 3.2, 0.30),        # Pinnacle cote : cote Pinnacle × 1,00
        ("but", 5.0, None, None),       # sans Pinnacle : médiane US × 1,10 (tranche 4,5-7)
        ("ast", 2.0, None, None),       # passes sans Pinnacle : 0,85 (tranche trop maigre -> segment)
        ("but", 5.0, 5.2, None),        # Pinnacle « Oui » seul : reste ancré sur Pinnacle
        ("but", None, None, None),      # aucune cote : pas de prix, donc pas de pari
    ], columns=["market", "soft_median", "pin_yes", "p_novig"]).astype({"soft_median": float, "pin_yes": float,
                                                                         "p_novig": float})
    out = add_real_price(p, load_ratios(str(path)))
    np.testing.assert_allclose(out["real_price"][:4], [3.2, 5.5, 1.7, 5.2])
    assert math.isnan(out["real_price"][4])
    assert "real_price" not in p  # copie, l'original n'est pas modifié


def test_committed_ratios_are_plausible():
    """Le fichier versionné (nhl/reports/sim_price.json) couvre les deux marchés avec des ratios crédibles."""
    soft, vs_pin = load_ratios()
    assert set(vs_pin) == {"but", "ast"} and all(0.9 <= r <= 1.1 for r in vs_pin.values())
    assert {mk for mk, _, _ in soft} == {"but", "ast"} and all(0.5 <= r <= 1.5 for r in soft.values())
    assert "vraies cotes Winamax" in describe()
