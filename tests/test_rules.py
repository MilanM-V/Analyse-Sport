"""Règles de production : éligibilité, stratégie de mise, rapprochement des cotes, dédoublonnage."""
import importlib

import pytest

from nhl.core.betting import BetParams, blend_probability, ev_threshold, kelly_units, select_bets
from nhl.core.market_filter import evaluate_player_markets
from shared.odds_api import match_player


# ── Éligibilité (audit P0-2) ────────────────────────────────────────────────
@pytest.mark.parametrize("pos,expected", [("C", True), ("L", True), ("R", True), ("LW", True), ("D", False)])
def test_wingers_eligible_for_goalscorer(pos, expected):
    p_form = {"ATOI": 18.0, "L10_SOG_G": 2.5, "L10_iHDCF_G": 1.0, "L10_A_G": 0.4}
    v5 = {"G_GP": 0.35, "A_GP": 0.4, "GP": 30, "Position": pos}
    cat_but, _ = evaluate_player_markets("X", p_form, v5, {}, True)
    assert bool(cat_but) is expected


# ── Stratégie de mise (audit P2) ────────────────────────────────────────────
def _params(**kw):
    base = dict(blend_w={"but": 0.5, "ast": 0.5}, cote_min={"but": 1.5, "ast": 1.5},
                cote_max={"but": 20.0, "ast": 20.0}, ev_low=0.05, ev_mid=0.05, ev_high=0.05,
                low_cut=2.0, mid_cut=3.5, no_pinnacle_extra_ev=0.05, kelly_fraction=0.125,
                min_stake=0.5, max_stake={"but": 1.5, "ast": 2.0}, max_game_exposure=3.0,
                max_daily_exposure=15.0)
    base.update(kw)
    return BetParams(**base)


def test_blend_falls_back_without_pinnacle():
    assert blend_probability(0.3, None, 0.5) == 0.3
    assert blend_probability(0.3, float("nan"), 0.5) == 0.3
    assert blend_probability(0.3, 0.2, 0.5) == pytest.approx(0.25)


def test_no_minimum_stake_floor():
    # Kelly minuscule : l'ancien code misait quand même 0,5 U
    assert kelly_units(0.21, 5.0, 100.0, _params(), "but") == 0.0


def test_ev_threshold_penalises_missing_pinnacle():
    p = _params()
    assert ev_threshold(3.0, p, has_pinnacle=False) == pytest.approx(ev_threshold(3.0, p) + 0.05)


def test_per_game_exposure_cap():
    cands = [{"market": "ast", "p_model": 0.6, "p_novig": 0.6, "cote": 2.5, "game_id": 1} for _ in range(5)]
    bets = select_bets(cands, 100.0, _params())
    assert sum(b["mise"] for b in bets) <= 3.0


def test_rejects_out_of_range_odds():
    cands = [{"market": "but", "p_model": 0.5, "p_novig": 0.5, "cote": 30.0, "game_id": 1}]
    assert select_bets(cands, 100.0, _params()) == []


# ── Rapprochement des noms (cotes) ──────────────────────────────────────────
def test_match_player_handles_accents_and_initials():
    cands = ["Alexis Lafrenière", "Sebastian Aho", "Jack Hughes", "Quinn Hughes"]
    assert match_player("Alexis Lafreniere", cands) == "Alexis Lafrenière"
    assert match_player("S. Aho", cands) == "Sebastian Aho"
    assert match_player("Hughes", cands) is None  # ambigu : refusé


# ── Dédoublonnage des picks (audit P0) ──────────────────────────────────────
def test_duplicate_pick_is_ignored(tmp_path, monkeypatch):
    import nhl.core.database as db
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "t.db"))
    db.init_db()
    first = db.insert_pick("picks", {"date": "2026-10-01", "joueur": "A B", "cote": 4.0})
    second = db.insert_pick("picks", {"date": "2026-10-01", "joueur": "A B", "cote": 4.2})
    assert first is not None and second is None


# ── Démarrage (audit P0-3) ──────────────────────────────────────────────────
def test_services_module_imports_datetime_alias():
    services = importlib.import_module("nhl.core.services")
    assert hasattr(services, "dt") and hasattr(services.dt, "time")
