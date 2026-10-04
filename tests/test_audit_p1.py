"""Audit du 2026-10-04, phase P1 : dévig, EV de clôture, profil PSI."""
import numpy as np
import pandas as pd
import pytest

from shared.devig import METHODS, devig_yes


# ── Dévig ───────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("method", METHODS)
def test_devig_probabilities_sum_to_one(method):
    yes, no = np.array([4.0, 2.1, 1.4, 9.0]), np.array([1.25, 1.75, 2.9, 1.06])
    py, pn = devig_yes(yes, no, method), devig_yes(no, yes, method)
    np.testing.assert_allclose(py + pn, 1.0, atol=1e-6)


@pytest.mark.parametrize("method", METHODS)
def test_devig_without_margin_is_identity(method):
    assert devig_yes(4.0, 4.0 / 3.0, method) == pytest.approx(0.25, abs=1e-6)


def test_shin_shifts_margin_to_longshot():
    # Multiplicatif : surestime le longshot ; Shin le corrige vers le bas
    assert devig_yes(4.0, 1.25, "shin") < devig_yes(4.0, 1.25, "multiplicative")


def test_devig_propagates_missing_side():
    assert np.isnan(devig_yes(np.array([3.0]), np.array([np.nan]), "shin"))[0]


def test_prod_uses_configured_devig():
    from nhl.config.settings import cfg
    assert cfg.betting.devig_method == "shin"


# ── EV de clôture et critère de passage en réel ─────────────────────────────
def test_closing_ev_summary_and_verdict(tmp_path, monkeypatch):
    import nhl.core.database as db
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "bot.db"))
    db.init_db()
    rows = [("A", 3.0, 0.40, None, None), ("B", 2.0, 0.45, 2.2, 1), ("C", 4.0, 0.20, None, 0),  # C : skip
            ("D", 3.0, 0.30, None, None)]
    for j, cote, pnv, reelle, pris in rows:
        db.insert_pick("picks", {"date": "2026-10-10", "joueur": j, "cote": cote, "mise": 1.0,
                                 "closing_p_novig": pnv, "cote_reelle": reelle, "pris": pris})
    db.insert_pick("picks", {"date": "2026-10-10", "joueur": "V", "cote": 3.0, "mise": 1.0,
                             "closing_p_novig": 0.9, "statut": "void"})
    s = db.closing_ev_summary()
    assert s["n"] == 3 and s["n_real"] == 1
    # (0.40×3 − 1) + (0.45×2.2 − 1) + (0.30×3 − 1) = 0.2 − 0.01 − 0.1
    assert s["ev_mean"] == pytest.approx((0.2 - 0.01 - 0.1) / 3)
    assert db.go_live_verdict(s, 300).startswith("⛔")
    assert db.go_live_verdict({"n": 400, "ev_mean": 0.03, "ci_lo": 0.01, "ci_hi": 0.05}, 300).startswith("✅")


# ── Profil PSI sur la population servie ─────────────────────────────────────
def test_psi_profile_matches_served_population():
    from nhl.core.monitoring import psi, reference_profile
    from nhl.scripts.train_models import profile_population
    rng = np.random.default_rng(0)
    n = 20000
    df = pd.DataFrame({"toi_l10": rng.uniform(5, 24, n), "std_gp": rng.integers(0, 60, n),
                       "position": rng.choice(["C", "L", "R", "D"], n)})
    served = profile_population(df, "but")  # ce que la prod sert : attaquants, ATOI ≥ 13, GP ≥ 10
    sample = served.sample(500, random_state=1)["toi_l10"].to_numpy()
    good = psi(reference_profile(served, ["toi_l10"])["toi_l10"], sample)
    bad = psi(reference_profile(df, ["toi_l10"])["toi_l10"], sample)
    assert good < 0.1 < 0.2 < bad
