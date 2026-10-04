"""Audit du 2026-10-04, phase P2 : options du modèle et journalisation du marché."""
import asyncio

import numpy as np
import pytest


# ── Modèle : refit sur 100 %, calibration en deux moitiés, params pour tous les algos ──
def _data(n=3000, seed=0):
    rng = np.random.default_rng(seed)
    X = rng.normal(size=(n, 5))
    y = (rng.random(n) < 1 / (1 + np.exp(-(X[:, 0] - 1.2)))).astype(int)
    return X, y


@pytest.mark.parametrize("kw", [{}, {"refit_full": True}, {"refit_full": True, "split_calib": True}])
def test_temporal_gbm_options_produce_valid_probabilities(kw):
    from nhl.core.ensemble_model import TemporalCalibratedGBM
    X, y = _data()
    m = TemporalCalibratedGBM(algos=("lgbm",), params={"lgbm": {"n_estimators": 30}}, **kw).fit(X, y)
    p = m.predict_proba(X)[:, 1]
    assert p.shape == (len(y),) and p.min() >= 0.005 and p.max() <= 0.995
    assert abs(p.mean() - y.mean()) < 0.05  # calibrée (bloc d'isotonique petit : tolérance large)


def test_refit_full_trains_on_all_rows():
    from nhl.core.ensemble_model import TemporalCalibratedGBM
    X, y = _data()
    kw = dict(algos=("lgbm",), params={"lgbm": {"n_estimators": 20}})
    base = TemporalCalibratedGBM(**kw).fit(X, y)
    refit = TemporalCalibratedGBM(refit_full=True, **kw).fit(X, y)
    # Même isotonique, arbres différents (appris avec le bloc de calibration en plus)
    np.testing.assert_allclose(base.iso_.X_thresholds_, refit.iso_.X_thresholds_)
    assert not np.allclose(base.models_["lgbm"].predict_proba(X), refit.models_["lgbm"].predict_proba(X))


def test_params_override_applies_to_xgb_and_catboost():
    from nhl.core.ensemble_model import TemporalCalibratedGBM
    t = TemporalCalibratedGBM(params={"xgb": {"n_estimators": 7}, "cat": {"iterations": 9}})
    assert t._make("xgb").get_params()["n_estimators"] == 7
    cat = t._make("cat")
    assert cat.get_params()["iterations"] == 9 and cat.get_params()["allow_writing_files"] is False


# ── Journalisation du marché (futures features) ─────────────────────────────
def _rows(book, market, outcomes, home="Boston Bruins", away="Toronto Maple Leafs"):
    return [{"event_id": "e", "commence_time": "2026-10-10T23:00:00Z", "home": home, "away": away, "book": book,
             "market": market, "name": n, "description": None, "point": pt, "price": pr} for n, pt, pr in outcomes]


def test_summarize_match_lines_picks_main_total_and_pinnacle():
    from nhl.core.odds_logging import summarize_match_lines
    rows = (_rows("pinnacle", "totals", [("Over", 5.5, 1.80), ("Under", 5.5, 2.05), ("Over", 6.5, 2.60),
                                         ("Under", 6.5, 1.50), ("Over", 6.0, 2.00), ("Under", 6.0, 1.86)])
            + _rows("draftkings", "totals", [("Over", 6.5, 2.2), ("Under", 6.5, 1.7)])
            + _rows("pinnacle", "h2h", [("Boston Bruins", None, 1.80), ("Toronto Maple Leafs", None, 2.10)]))
    s = summarize_match_lines(rows, "Boston Bruins", "Toronto Maple Leafs")
    assert s["total_book"] == "pinnacle" and s["total_line"] == 6.0
    assert s["h2h_book"] == "pinnacle" and 0.5 < s["p_home"] < 0.56


def test_extra_props_disabled_makes_no_api_call(monkeypatch):
    import shared.odds_api as oa
    from nhl.config.settings import cfg
    from nhl.core.odds_logging import log_extra_props

    async def boom(*a, **k):
        raise AssertionError("aucun appel API ne doit partir quand log_extra_markets = false")
    monkeypatch.setattr(oa, "fetch_event_odds_raw", boom)
    assert cfg.betting.log_extra_markets is False
    assert asyncio.run(log_extra_props([("Boston Bruins", "Toronto Maple Leafs")], "2026-10-10")) == 0


def test_log_match_context_writes_rows(tmp_path, monkeypatch):
    import nhl.core.database as db
    import nhl.core.odds_logging as ol
    import shared.odds_api as oa
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "bot.db"))
    db.init_db()

    async def fake(*a, **k):
        return (_rows("pinnacle", "totals", [("Over", 6.0, 1.95), ("Under", 6.0, 1.9)], away="Montréal Canadiens")
                + _rows("pinnacle", "h2h", [("Boston Bruins", None, 1.7), ("Montréal Canadiens", None, 2.2)],
                        away="Montréal Canadiens"))
    monkeypatch.setattr(oa, "fetch_event_odds_raw", fake)
    games = [("Boston Bruins", "Montreal Canadiens")]
    n = asyncio.run(ol.log_match_context(games, {games[0]: ("J. Swayman", "S. Montembeault")}, "2026-10-10"))
    assert n == 1
    conn = db.get_connection()
    row = conn.execute("SELECT total_line, p_home, goalie_home, goalie_away FROM match_context").fetchone()
    conn.close()
    assert row[0] == 6.0 and 0.5 < row[1] < 0.6 and row[2:] == ("J. Swayman", "S. Montembeault")
