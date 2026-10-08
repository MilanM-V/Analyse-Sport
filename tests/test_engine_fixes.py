"""Bugs trouvés par les études du 07 et du 08/10/2026 (lot 1 du plan « moteur v2 »)."""
import json
import sqlite3

import numpy as np
import pandas as pd

from nhl.data.gamelog_schema import enforce_schema

STAT_COLS = ["toi", "pp_toi", "g", "a1", "a2", "sog", "missed", "blocked_att", "pp_g", "pp_sog"]


# ── 1. Retrain hebdomadaire : l'ensemble de [model], pas un LightGBM seul ──────
def test_weekly_retrain_trains_the_prod_ensemble():
    from nhl.config.settings import cfg
    from nhl.scripts import train_models
    assert train_models.DEFAULT_ALGOS == tuple(cfg.model.algos) == ("lgbm", "xgb", "cat")


# ── 3. Un modèle live d'une ancienne version de features n'est pas servi ───────
def test_live_model_of_another_features_version_is_ignored(tmp_path, monkeypatch):
    import joblib

    from nhl.core import inference
    from nhl.core.features import FEATURES_VERSION
    monkeypatch.setattr(inference, "MODELS_DIR", str(tmp_path))
    (tmp_path / "live").mkdir()
    live, git = tmp_path / "live" / "ml_model_but.pkl", tmp_path / "ml_model_but.pkl"
    joblib.dump({"features_version": "ancienne", "algo": "live"}, live)
    joblib.dump({"features_version": FEATURES_VERSION, "algo": "git"}, git)
    assert inference.load_model_bundle("but") == (str(git), {"features_version": FEATURES_VERSION, "algo": "git"})
    assert inference.load_models()["but"]["algo"] == "git"
    # Un retrain live de la bonne version reste prioritaire
    joblib.dump({"features_version": FEATURES_VERSION, "algo": "live2"}, live)
    assert inference.load_model_bundle("but")[1]["algo"] == "live2"
    # Aucun modèle compatible : le premier trouvé est rendu, bot_logic signale l'incompatibilité
    joblib.dump({"features_version": "ancienne", "algo": "live"}, live)
    joblib.dump({"features_version": "ancienne", "algo": "git"}, git)
    assert inference.load_model_bundle("but")[1]["algo"] == "live"
    assert inference.load_model_bundle("ast") == (None, None)


# ── 4. Table players : no-vig, proba finale et playerId journalisés ────────────
def test_players_log_keeps_novig_final_and_player_id(tmp_path, monkeypatch):
    import nhl.core.database as db
    import nhl.core.updater as upd
    from nhl.core.logger_csv import log_picks_to_db
    from shared.portfolio import Portfolio
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "bot.db"))
    db.init_db()
    monkeypatch.setattr(upd, "portfolio", Portfolio(str(tmp_path / "pf.db")))
    player = {"Joueur": "Nick Suzuki", "Equipe": "MTL", "Adversaire": "TOR", "IsHome": True,
              "Score_But": 0.21, "Score_Assist": 0.33, "Picked_But": True, "Picked_Assist": True,
              "Backup": False, "B2B": False, "p_form": {}, "p_v5": {}, "adv_stats": {},
              "Cote": 4.1, "CoteAst": 2.6, "PlayerId": 8480018,
              "PNovig_but": 0.2, "PNovig_ast": 0.31, "PFinal_but": 0.2065, "PFinal_ast": 0.328}
    log_picks_to_db([], [], [], [player], "V1", "2026-10-10", ds=None)
    # Le nom du boxscore diffère : la résolution passe par le playerId
    box = {"MTL": {"by_id": {8480018: {"goals": 0, "assists": 2, "points": 2, "shots": 1}},
                   "by_name": {"N. Suzuki-X": {"goals": 0, "assists": 2, "points": 2, "shots": 1}}}}
    upd._resolve_date("2026-10-10", box)
    conn = db.get_connection()
    row = conn.execute("SELECT player_id, p_novig_but, p_novig_ast, p_final_but, p_final_ast, cote, cote_ast, "
                       "but, assist FROM players").fetchone()
    conn.close()
    assert row == (8480018, 0.2, 0.31, 0.2065, 0.328, 4.1, 2.6, 0, 2)


# ── 5. build_odds_table : « Montréal Canadiens » (accent) reconnu ──────────────
def test_odds_table_keeps_montreal_with_accent(tmp_path, monkeypatch):
    import nhl.scripts.build_odds_table as bot
    path = tmp_path / "odds.db"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE api_cache (snapshot_time TEXT, event_id TEXT, json_response TEXT)")
    event = {"data": {"commence_time": "2025-10-08T23:00:00Z", "home_team": "Montréal Canadiens",
                      "away_team": "Toronto Maple Leafs", "bookmakers": [{"key": "pinnacle", "markets": [
                          {"key": "player_goal_scorer_anytime", "outcomes": [
                              {"name": "Yes", "description": "Nick Suzuki", "price": 3.1},
                              {"name": "No", "description": "Nick Suzuki", "price": 1.35}]}]}]}}
    conn.execute("INSERT INTO api_cache VALUES (?, ?, ?)", ("2025-10-08T22:50:00Z", "e1", json.dumps(event)))
    conn.commit()
    conn.close()
    monkeypatch.setattr(bot, "DB_PATH", str(path))
    long = bot.parse_long()
    assert set(long["home"]) == {"MTL"} and set(long["away"]) == {"TOR"} and len(long) == 2
    assert bot.team_abbr("Arizona Coyotes") == "ARI" and bot.team_abbr("Équipe inconnue") is None


# ── 6. Simulation : stats saison des lignes 2025-26 (std_gp n'est plus 0) ───────
def test_season_stats_cover_nhl_api_seasons(monkeypatch):
    from nhl.core import features
    from nhl.sim import phases
    logs = _league_logs()
    monkeypatch.setattr(features, "load_all_gamelogs", lambda gamelog_dir=None: logs)
    std = phases._std_stats().merge(logs[["playerId", "gameId", "season", "gameDate"]], on=["playerId", "gameId"])
    last = std[std.season == 2025].sort_values("gameDate").groupby("playerId").tail(1)
    assert (last["std_gp"] > 0).all() and (last["ATOI_L10"] > 0).all()


# ── 7. H17 : le harnais entraîne sur des lignes triées par date ────────────────
def test_walk_forward_trains_on_date_sorted_rows():
    from nhl.scripts.simulate_roi import PhaseSpec, walk_forward_predictions
    rng = np.random.default_rng(0)
    dates = pd.date_range("2023-10-01", periods=60, freq="D")
    rows = [{"date": d, "playerId": pid, "gameId": 1000 + i, "f": float(d.toordinal()),
             "target_but": float(rng.random() < 0.3), "target_ast": float(rng.random() < 0.3)}
            for pid in (3, 1, 2) for i, d in enumerate(dates)]
    df = pd.DataFrame(rows)  # trié par joueur, comme build_features
    seen = []

    class Spy:
        def fit(self, X, y):
            seen.append(X[:, 0].copy())
            return self

        def predict_proba(self, X):
            return np.column_stack([np.full(len(X), 0.7), np.full(len(X), 0.3)])

    every = lambda d, m: pd.Series(True, index=d.index)  # noqa: E731
    spec = PhaseSpec(name="t", load=lambda: df, features={"but": ["f"], "ast": ["f"]}, model_factory=lambda m: Spy(),
                     train_mask=every, eligible=every, select_and_stake=lambda day: day)
    odds = pd.DataFrame([{"date": d, "playerId": pid, "market": m} for d in dates[50:]
                         for pid in (1, 2, 3) for m in ("but", "ast")])
    walk_forward_predictions(spec, df, odds, [str(dates[50].date())])
    assert len(seen) == 2 and all((np.diff(x) >= 0).all() and len(x) == 150 for x in seen)


# ── 8. Inférence en début de saison : mêmes features qu'à l'entraînement ───────
TEAMS = {"AAA": [(1, "C"), (2, "L"), (3, "D")], "BBB": [(4, "C"), (5, "R"), (6, "D")],
         "CCC": [(7, "C"), (8, "L"), (9, "D")], "DDD": [(10, "C"), (11, "R"), (12, "D")]}
ROUNDS = [(("AAA", "BBB"), ("CCC", "DDD")), (("AAA", "CCC"), ("BBB", "DDD")), (("AAA", "DDD"), ("BBB", "CCC"))]


def _league_logs(seed: int = 0) -> pd.DataFrame:
    """4 équipes : 12 journées en 2023 et en 2024, 2 en 2025, puis un dernier match AAA-BBB seul (le « soir »).

    La saison 2023 vérifie que l'historique servi (saison précédente pour tous) suffit : les
    lignes 2023 des équipes qui ne jouent pas le soir n'en font pas partie.
    """
    rng = np.random.default_rng(seed)
    schedule = [(2023, pd.Timestamp("2023-10-10") + pd.Timedelta(days=2 * r), ROUNDS[r % 3]) for r in range(12)]
    schedule += [(2024, pd.Timestamp("2024-10-10") + pd.Timedelta(days=2 * r), ROUNDS[r % 3]) for r in range(12)]
    schedule += [(2025, pd.Timestamp("2025-10-08") + pd.Timedelta(days=2 * r), ROUNDS[r % 3]) for r in range(2)]
    schedule.append((2025, pd.Timestamp("2025-10-14"), (("AAA", "BBB"),)))
    rows, gid = [], 2024020001
    for season, date, games in schedule:
        for home, away in games:
            for team, opp in ((home, away), (away, home)):
                for pid, pos in TEAMS[team]:
                    rows.append({
                        "playerId": pid, "name": f"P{pid}", "gameId": gid, "season": season, "game_type": 2,
                        "gameDate": date, "team": team, "opp": opp, "is_home": int(team == home), "position": pos,
                        "toi": float(rng.uniform(10, 22)), "pp_toi": float(rng.uniform(0, 3)),
                        "g": int(rng.random() < 0.2), "a1": int(rng.random() < 0.15), "a2": int(rng.random() < 0.1),
                        "sog": int(rng.integers(0, 5)), "missed": int(rng.integers(0, 3)),
                        "blocked_att": int(rng.integers(0, 3)), "pp_g": 0, "pp_sog": int(rng.integers(0, 2))})
            gid += 1
    return enforce_schema(pd.DataFrame(rows))


def test_early_season_serving_features_match_training():
    from nhl.core.features import FEATURES, build_features
    from nhl.core.inference import serving_history
    logs = _league_logs()
    today = logs["gameDate"].max()
    tonight = logs[logs["gameDate"] == today].copy()
    tonight[STAT_COLS] = np.nan
    # Entraînement : tout l'historique, le match du soir sans stats
    full = build_features(pd.concat([logs[logs["gameDate"] < today], tonight], ignore_index=True))
    # Service : historique réduit de FeatureEngine.predict + lignes à venir
    hist = serving_history(logs, 2025, tonight["playerId"], today)
    serve = build_features(pd.concat([hist, tonight], ignore_index=True))
    cols = sorted(set().union(*FEATURES.values()))
    a = full[full["gameDate"] == today].set_index("playerId")[cols].sort_index()
    b = serve[serve["gameDate"] == today].set_index("playerId")[cols].sort_index()
    # dtype ignoré : les vieilles lignes non servies peuvent passer en float (adversaires absents)
    pd.testing.assert_frame_equal(a, b, check_exact=False, rtol=1e-9, check_dtype=False)
