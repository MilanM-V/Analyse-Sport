"""Mode découverte ([early_season]) : picks avant 10 matchs, mise réduite, suivi à part."""
import pytest

from nhl.config.settings import cfg
from nhl.core.betting import BetParams, select_bets
from nhl.core.market_filter import blend_season_rates, evaluate_early_season

FORM = {"ATOI": 17.0}
PREV = {"GP": 70, "G_GP": 0.40, "A_GP": 0.50}


@pytest.fixture
def early_on(monkeypatch):
    monkeypatch.setattr(cfg.early_season, "enabled", True)
    monkeypatch.setattr(cfg.early_season, "min_prev_gp", 20)


def test_blend_rates_moves_from_last_season_to_current():
    assert blend_season_rates(0, 0.0, 0.40, 10) == pytest.approx(0.40)
    assert blend_season_rates(10, 0.10, 0.40, 10) == pytest.approx(0.25)


def test_player_under_10_games_with_history_is_early(early_on):
    cb, ca, phase = evaluate_early_season("X", FORM, {"GP": 5, "G_GP": 0.2, "A_GP": 0.4, "Position": "C"},
                                          {}, True, PREV)
    assert (cb, ca, phase) == ("BUTEUR", "PASSEUR", "early")


def test_rookie_without_history_gets_nothing(early_on):
    v5 = {"GP": 3, "G_GP": 0.5, "A_GP": 0.5, "Position": "C"}
    assert evaluate_early_season("X", FORM, v5, {}, True, None) == (None, None, "normal")
    assert evaluate_early_season("X", FORM, v5, {}, True, {**PREV, "GP": 8}) == (None, None, "normal")


def test_switches_to_normal_at_10_games(early_on):
    cb, _, phase = evaluate_early_season("X", FORM, {"GP": 10, "G_GP": 0.3, "A_GP": 0.4, "Position": "L"},
                                         {}, True, PREV)
    assert cb == "BUTEUR" and phase == "normal"


def test_disabled_mode_keeps_the_10_game_rule(monkeypatch):
    monkeypatch.setattr(cfg.early_season, "enabled", False)
    assert evaluate_early_season("X", FORM, {"GP": 5, "Position": "C"}, {}, True, PREV) == (None, None, "normal")


def test_early_pick_needs_higher_ev_and_gets_half_stake():
    params = BetParams.from_config(early_ev_min=0.15, early_stake_mult=0.5, max_bets_per_game=0)
    base = {"market": "but", "p_model": 0.40, "p_novig": 0.40, "cote": 2.80}  # EV +12 %
    normal = select_bets([{**base, "game_id": 1}], 100.0, params)
    early = select_bets([{**base, "game_id": 2, "early": True}], 100.0, params)
    assert normal and not early  # 12 % < 15 % exigés en découverte
    strong = {"market": "but", "p_model": 0.45, "p_novig": 0.45, "cote": 3.0}  # EV +35 %
    n = select_bets([{**strong, "game_id": 1}], 100.0, params)[0]["mise"]
    e = select_bets([{**strong, "game_id": 2, "early": True}], 100.0, params)[0]["mise"]
    assert e == pytest.approx(round(n * 0.5 * 2) / 2)


def test_early_picks_excluded_from_go_live_count(tmp_path, monkeypatch):
    import nhl.core.database as db
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "bot.db"))
    db.init_db()
    db.insert_pick("picks", {"date": "2026-10-10", "joueur": "A", "cote": 3.0, "mise": 1.0,
                             "closing_p_novig": 0.4, "phase": "normal"})
    db.insert_pick("picks", {"date": "2026-10-10", "joueur": "B", "cote": 3.0, "mise": 0.5,
                             "closing_p_novig": 0.2, "phase": "early", "but": 1})
    assert db.closing_ev_summary()["n"] == 1
    assert db.closing_ev_summary(phase="early")["n"] == 1
    assert "1✅ / 1" in db.get_roi_stats("picks", "but", phase="early")
    assert db.get_roi_stats("picks", "but", phase="normal").startswith("Pas assez")


def test_telegram_shows_discovery_badge():
    from nhl.core.services import pick_card_text
    p = {"Joueur": "X", "IsHome": True, "CoteSeuil": 3.1, "Mise": "0.5 U", "Ref": "B1", "Phase": "early"}
    assert "🧪" in pick_card_text(p, "but")
