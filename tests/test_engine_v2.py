"""Moteur v2 (2026-10-08) : calibration Platt, membre réseau de neurones, garde-fous xG, phases du harnais."""
import numpy as np
import pandas as pd
import pytest


def _data(n=4000, seed=0):
    rng = np.random.default_rng(seed)
    X = rng.normal(size=(n, 6))
    X[rng.random(X.shape) < 0.05] = np.nan
    y = (rng.random(n) < 1 / (1 + np.exp(-(np.nan_to_num(X[:, 0]) - 1.2)))).astype(int)
    return X, y


SMALL = {"lgbm": {"n_estimators": 30}, "xgb": {"n_estimators": 30}}


@pytest.mark.parametrize("kw", [{"calibration": "platt"}, {"calibration": "platt", "mlp_nets": 2, "mlp_epochs": 2},
                                {"calibration": "isotonic", "mlp_nets": 1, "mlp_epochs": 2}])
def test_v2_options_produce_valid_calibrated_probabilities(kw):
    from nhl.core.ensemble_model import TemporalCalibratedGBM
    X, y = _data()
    m = TemporalCalibratedGBM(algos=("lgbm", "xgb"), params=SMALL, **kw).fit(X, y)
    p = m.predict_proba(X)[:, 1]
    assert p.shape == (len(y),) and p.min() >= 0.005 and p.max() <= 0.995
    assert abs(p.mean() - y.mean()) < 0.05
    assert (m.mlp_ is not None) == bool(kw.get("mlp_nets"))
    assert np.allclose(p, m.predict_proba(X)[:, 1])  # déterministe une fois entraîné


def test_platt_removes_isotonic_steps():
    from nhl.core.ensemble_model import TemporalCalibratedGBM
    X, y = _data()
    iso = TemporalCalibratedGBM(algos=("lgbm",), params=SMALL).fit(X, y).predict_proba(X)[:, 1]
    platt = TemporalCalibratedGBM(algos=("lgbm",), params=SMALL, calibration="platt").fit(X, y).predict_proba(X)[:, 1]
    assert len(np.unique(platt.round(6))) > 5 * len(np.unique(iso.round(6)))


def test_mlp_member_moves_the_trees_probability():
    from nhl.core.ensemble_model import TemporalCalibratedGBM
    X, y = _data()
    trees = TemporalCalibratedGBM(algos=("lgbm",), params=SMALL, calibration="platt").fit(X, y)
    both = TemporalCalibratedGBM(algos=("lgbm",), params=SMALL, calibration="platt", mlp_nets=1, mlp_epochs=2).fit(X, y)
    assert not np.allclose(trees.predict_proba(X), both.predict_proba(X))
    assert both.describe() == "temporal_calibrated_gbm[lgbm]+mlp1/platt"
    assert trees.describe() == "temporal_calibrated_gbm[lgbm]/platt"


def test_old_pickles_without_v2_attributes_still_predict():
    from nhl.core.ensemble_model import TemporalCalibratedGBM
    X, y = _data()
    m = TemporalCalibratedGBM(algos=("lgbm",), params=SMALL).fit(X, y)
    p = m.predict_proba(X)
    for a in ("cal_", "mlp_", "mlp_cal_", "calibration", "mlp_nets", "mlp_weight", "mlp_epochs"):
        m.__dict__.pop(a, None)  # objet tel que pické avant le 2026-10-08
    np.testing.assert_allclose(m.predict_proba(X), p)


def test_prod_model_follows_model_section():
    from nhl.config.settings import cfg
    from nhl.core.ensemble_model import prod_model
    m = prod_model()
    assert m.algos == tuple(cfg.model.algos) == ("lgbm", "xgb", "cat")
    assert (m.calibration, m.mlp_nets, m.mlp_weight) == ("platt", 3, 0.5)
    assert prod_model(("lgbm",)).algos == ("lgbm",)


# ── Garde-fous xG ───────────────────────────────────────────────────────────
def _logs():
    rows = [{"playerId": p, "gameId": 2024020000 + g, "season": 2024, "gameDate": pd.Timestamp("2024-10-10") + pd.Timedelta(days=g)}
            for p in (1, 2) for g in range(10)]
    rows += [{"playerId": p, "gameId": 2026020000 + g, "season": 2026, "gameDate": pd.Timestamp("2026-10-01") + pd.Timedelta(days=g)}
             for p in (1, 2) for g in range(5)]
    return pd.DataFrame(rows)


def test_xg_history_guard_and_lag():
    from nhl.core.inference import InsufficientHistoryError, check_xg_history, xg_lag_days
    logs = _logs()
    full = logs[["playerId", "gameId"]]
    check_xg_history(full, logs, 2026)  # saisons terminées couvertes
    with pytest.raises(InsufficientHistoryError):
        check_xg_history(full[full.gameId >= 2026020000], logs, 2026)  # historique absent
    assert xg_lag_days(full, logs, 2026) == 0
    late = full[~full.gameId.isin([2026020003, 2026020004])]  # deux derniers jours sans xG
    assert xg_lag_days(late, logs, 2026) == 2


# ── Phases du harnais ───────────────────────────────────────────────────────
def test_engine_phases_m0_and_v2():
    from nhl.core.features import FEATURES, FEATURES_P1, XG_FEATURES
    from nhl.sim.phases import PHASES
    m0, v2 = PHASES["m0"](), PHASES["v2"]()
    assert m0.features == {k: list(FEATURES_P1[k]) for k in ("but", "ast")}
    assert v2.features == {k: list(FEATURES[k]) for k in ("but", "ast")}
    assert [len(v2.features[k]) - len(m0.features[k]) for k in ("but", "ast")] == [len(XG_FEATURES)] * 2
    assert m0.extra["all_eligible"] and v2.extra["all_eligible"] and "reuse_preds" not in v2.extra
    a, b = m0.model_factory("but"), v2.model_factory("but")
    assert (a.calibration, a.mlp_nets) == ("isotonic", 0) and (b.calibration, b.mlp_nets, b.mlp_weight) == ("platt", 3, 0.5)


def test_all_eligible_predicts_lines_without_odds():
    from nhl.scripts.simulate_roi import PhaseSpec, walk_forward_predictions

    class Const:
        def fit(self, X, y):
            return self

        def predict_proba(self, X):
            return np.column_stack([np.full(len(X), 0.7), np.full(len(X), 0.3)])

    dates = pd.date_range("2023-09-01", periods=60, freq="D")
    df = pd.DataFrame([{"date": d, "playerId": p, "gameId": i, "f": 1.0, "target_but": 1.0, "target_ast": 0.0, "elig": p != 3}
                       for p in (1, 2, 3) for i, d in enumerate(dates)])
    odds = pd.DataFrame([{"date": d, "playerId": 3, "market": "but", "pin_yes": 3.0} for d in dates[40:42]])
    spec = PhaseSpec(name="t", load=lambda: df, features={"but": ["f"], "ast": ["f"]}, model_factory=lambda m: Const(),
                     train_mask=lambda d, m: pd.Series(True, index=d.index),
                     eligible=lambda d, m: d["elig"].astype(bool), select_and_stake=lambda day: day,
                     extra={"all_eligible": True})
    out = walk_forward_predictions(spec, df, odds, [str(dates[30].date())])
    but = out[out.market == "but"]
    assert set(but.playerId) == {1, 2, 3}                              # joueurs 1 et 2 sans cote, joueur 3 coté
    assert len(but[but.playerId == 3]) == 2 and but.loc[but.playerId == 3, "pin_yes"].eq(3.0).all()
    assert not but.loc[but.playerId == 3, "eligible"].any() and but.loc[but.playerId != 3, "pin_yes"].isna().all()


# ── Suivi du paper trading (table players) ───────────────────────────────────
def test_paper_quality_reads_players_table(tmp_path, monkeypatch):
    import nhl.core.database as db
    from nhl.scripts.paper_quality import load_players, quality
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "bot.db"))
    db.init_db()
    rng = np.random.default_rng(0)
    for i in range(48):
        p_nv = float(rng.uniform(0.15, 0.4))
        row = {"date": f"2026-10-{10 + i % 4:02d}", "joueur": f"J{i}", "player_id": 1000 + i, "picked_but": 1,
               "picked_assist": 0, "score_but": p_nv + 0.02, "p_novig_but": p_nv, "p_final_but": p_nv + 0.013,
               "but": int(rng.random() < p_nv), "assist": 0}
        db.insert_player(row)
        if i == 0:  # vague relancée : même joueur, même soir -> une seule ligne gardée
            db.insert_player(row)
    df = load_players(str(tmp_path / "bot.db"))
    assert len(df) == 48
    q = quality(df)
    assert q["but"]["n"] == 48 and q["but"]["nights"] == 4 and q["ast"]["n"] == 0
    assert q["but"]["model_vs_pinnacle"]["n"] == 48 and "lo" in q["but"]["final_vs_pinnacle"]


# ── Rapport par saison (engine_report) ───────────────────────────────────────
def test_engine_report_delta_and_money():
    from nhl.scripts.engine_report import delta_ll, money, season_of
    y = np.array([1, 0, 0, 1, 0, 0, 0, 1] * 25)
    nights = np.repeat(np.arange(20), 10)
    good, bad = np.where(y == 1, 0.6, 0.2), np.full(len(y), 0.375)
    d = delta_ll(y, good, bad, nights)
    assert d["d_mnat"] < 0 and d["lo"] <= d["d_mnat"] <= d["hi"] and d["n"] == 200 and d["nights"] == 20
    assert delta_ll(y, bad, bad, nights)["d_mnat"] == 0
    bets = pd.DataFrame({"date": pd.to_datetime(["2024-01-01", "2024-01-01", "2024-01-02"]), "mise": [1.0, 1.0, 1.0],
                         "cote": [3.0, 3.0, 3.0], "won": [1, 0, 0], "p_novig": [1 / 3, 1 / 3, np.nan]})
    bets["profit"] = np.where(bets.won == 1, bets.mise * (bets.cote - 1), -bets.mise)
    m = money(bets)
    assert (m["n"], m["gain"], m["roi"]) == (3, 0.0, 0.0) and m["z"] == pytest.approx(0.0)
    s = season_of(pd.Series(pd.to_datetime(["2023-10-10", "2024-07-01", "2026-04-16", "2026-10-01"])))
    assert s.iloc[:3].tolist() == ["2023-24", "2024-25", "2025-26"] and pd.isna(s.iloc[3])
