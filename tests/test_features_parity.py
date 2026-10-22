"""Parité train/serve : une ligne "match à venir" doit produire exactement les features d'entraînement."""
import numpy as np
import pandas as pd
import pytest

from nhl.core.features import FEATURES, FEATURES_G, FEATURES_V2, build_features
from nhl.data.gamelog_schema import GAMELOG_COLUMNS, enforce_schema

STAT_COLS = ["toi", "pp_toi", "g", "a1", "a2", "sog", "missed", "blocked_att", "pp_g", "pp_sog"]


def _synthetic_logs(n_games: int = 30, seed: int = 0) -> pd.DataFrame:
    """Deux équipes de 4 patineurs qui s'affrontent `n_games` fois (2 saisons)."""
    rng = np.random.default_rng(seed)
    rows = []
    players = {"AAA": [(1, "C"), (2, "L"), (3, "R"), (4, "D")], "BBB": [(5, "C"), (6, "L"), (7, "R"), (8, "D")]}
    for i in range(n_games):
        season = 2023 if i < n_games // 2 else 2024
        date = pd.Timestamp("2023-10-10") + pd.Timedelta(days=2 * i + (200 if season == 2024 else 0))
        home = "AAA" if i % 2 == 0 else "BBB"
        for team, roster in players.items():
            opp = "BBB" if team == "AAA" else "AAA"
            for pid, pos in roster:
                rows.append({
                    "playerId": pid, "name": f"P{pid}", "gameId": 1000 + i, "season": season, "game_type": 2,
                    "gameDate": date, "team": team, "opp": opp, "is_home": int(team == home), "position": pos,
                    "toi": float(rng.uniform(10, 22)), "pp_toi": float(rng.uniform(0, 3)),
                    "g": int(rng.random() < 0.15), "a1": int(rng.random() < 0.12), "a2": int(rng.random() < 0.1),
                    "sog": int(rng.integers(0, 5)), "missed": int(rng.integers(0, 3)),
                    "blocked_att": int(rng.integers(0, 3)), "pp_g": 0, "pp_sog": int(rng.integers(0, 2)),
                })
    return enforce_schema(pd.DataFrame(rows))


def test_upcoming_row_matches_training_row():
    logs = _synthetic_logs()
    full = build_features(logs)
    last_gid = logs["gameId"].max()
    # Même historique, mais le dernier match "n'est pas encore joué" (stats inconnues)
    up = logs.copy()
    up.loc[up["gameId"] == last_gid, STAT_COLS] = np.nan
    serve = build_features(up)
    cols = sorted(set().union(*FEATURES.values(), *FEATURES_V2.values(), *FEATURES_G.values()))
    a = full[full.gameId == last_gid].set_index("playerId")[cols].sort_index()
    b = serve[serve.gameId == last_gid].set_index("playerId")[cols].sort_index()
    pd.testing.assert_frame_equal(a, b, check_exact=False, rtol=1e-9)
    assert serve.loc[serve.gameId == last_gid, "target_but"].isna().all()


def test_no_future_leakage():
    """Modifier les stats d'un match ne change aucune feature de ce match ni des matchs antérieurs."""
    logs = _synthetic_logs()
    gid = logs["gameId"].unique()[10]
    alt = logs.copy()
    alt.loc[alt["gameId"] >= gid, ["g", "sog", "toi"]] = alt.loc[alt["gameId"] >= gid, ["g", "sog", "toi"]] + 3
    f1, f2 = build_features(logs), build_features(alt)
    cols = sorted(set().union(*FEATURES_V2.values(), *FEATURES_G.values()))
    a = f1[f1.gameId <= gid].sort_values(["playerId", "gameId"])[cols].reset_index(drop=True)
    b = f2[f2.gameId <= gid].sort_values(["playerId", "gameId"])[cols].reset_index(drop=True)
    pd.testing.assert_frame_equal(a, b)


def test_schema_rejects_missing_columns():
    with pytest.raises(ValueError):
        build_features(pd.DataFrame({"playerId": [1]}))
    assert len(GAMELOG_COLUMNS) == 20


# ── Features xG (moteur v2) ─────────────────────────────────────────────────
def _synthetic_xg(logs: pd.DataFrame, seed: int = 1) -> pd.DataFrame:
    """Table xG au schéma XG_COLUMNS pour chaque joueur-match des logs synthétiques."""
    from nhl.data.gamelog_schema import XG_COLUMNS
    rng = np.random.default_rng(seed)
    xg = logs[["playerId", "gameId"]].copy()
    for c in XG_COLUMNS:
        xg[c] = rng.uniform(0, 3, len(xg)) if c != "icetime" else rng.uniform(600, 1300, len(xg))
    return xg


def test_xg_features_match_between_training_and_serving():
    from nhl.core.features import XG_FEATURES
    logs = _synthetic_logs()
    xg = _synthetic_xg(logs)
    last_gid = logs["gameId"].max()
    full = build_features(logs, xg=xg)
    up = logs.copy()
    up.loc[up["gameId"] == last_gid, STAT_COLS] = np.nan
    serve = build_features(up, xg=xg[xg["gameId"] != last_gid])  # le match à venir n'a pas encore d'xG
    a = full[full.gameId == last_gid].set_index("playerId")[XG_FEATURES].sort_index()
    b = serve[serve.gameId == last_gid].set_index("playerId")[XG_FEATURES].sort_index()
    assert a.notna().all().all()
    pd.testing.assert_frame_equal(a, b, check_exact=False, rtol=1e-9)
    assert set(XG_FEATURES) <= set(FEATURES["but"]) and set(XG_FEATURES) <= set(FEATURES["ast"])
    assert build_features(logs)[XG_FEATURES].isna().all().all()  # sans table xG : NaN


def test_xg_features_have_no_future_leakage():
    from nhl.core.features import XG_FEATURES
    from nhl.data.gamelog_schema import XG_COLUMNS
    logs = _synthetic_logs()
    xg = _synthetic_xg(logs)
    gid = logs["gameId"].unique()[10]
    alt = xg.copy()
    alt.loc[alt["gameId"] >= gid, XG_COLUMNS] = alt.loc[alt["gameId"] >= gid, XG_COLUMNS] * 3 + 1
    f1, f2 = build_features(logs, xg=xg), build_features(logs, xg=alt)
    a = f1[f1.gameId <= gid].sort_values(["playerId", "gameId"])[XG_FEATURES].reset_index(drop=True)
    b = f2[f2.gameId <= gid].sort_values(["playerId", "gameId"])[XG_FEATURES].reset_index(drop=True)
    pd.testing.assert_frame_equal(a, b)
    c = f2[f2.gameId > gid].sort_values(["playerId", "gameId"])[XG_FEATURES].reset_index(drop=True)
    assert not np.allclose(c.to_numpy(), f1[f1.gameId > gid].sort_values(["playerId", "gameId"])[XG_FEATURES].to_numpy())
