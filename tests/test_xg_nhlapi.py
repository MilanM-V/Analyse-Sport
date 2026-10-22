"""Reconstruction de l'xG match par match (tirs MoneyPuck + présences et mises en jeu API NHL)."""
import pandas as pd
import pytest


def _shift(pid, team, start, end, type_code=517):
    return {"playerId": pid, "teamAbbrev": team, "period": 1, "startTime": start, "endTime": end, "typeCode": type_code}


SHIFTS = {"data": [
    _shift(11, "MTL", "00:00", "01:00"), _shift(11, "MTL", "05:00", "06:00"), _shift(12, "MTL", "00:00", "02:00"),
    _shift(21, "TOR", "00:00", "01:00"), _shift(21, "TOR", "05:00", "05:30"), _shift(22, "TOR", "01:00", "03:00"),
    _shift(11, "MTL", "00:30", "00:30", type_code=505),  # but : pas une présence
]}
PBP = {"homeTeam": {"id": 1, "abbrev": "MTL"}, "awayTeam": {"id": 2, "abbrev": "TOR"}, "plays": [
    {"typeDescKey": "faceoff", "periodDescriptor": {"number": 1}, "timeInPeriod": "00:00",
     "details": {"eventOwnerTeamId": 1, "zoneCode": "N"}},
    {"typeDescKey": "faceoff", "periodDescriptor": {"number": 1}, "timeInPeriod": "05:00",
     "details": {"eventOwnerTeamId": 1, "zoneCode": "O"}},
]}


def _shot(time, team, home, shooter, xg, home_sk=5, away_sk=5, away_empty=0):
    return {"game_id": 20001, "isPlayoffGame": 0, "period": 1, "time": time, "teamCode": team, "isHomeTeam": home,
            "shooterPlayerId": shooter, "xGoal": xg, "homeSkatersOnIce": home_sk, "awaySkatersOnIce": away_sk,
            "homeEmptyNet": 0, "awayEmptyNet": away_empty, "gameId": 2025020001}


SHOTS = pd.DataFrame([
    _shot(30, "MTL", 1, 11, 0.25),                          # 5 c. 5, haut danger
    _shot(60, "TOR", 0, 21, 0.10, home_sk=4, away_sk=5),    # TOR à 5 c. 4 ; t = fin de présence de 11, 12, 21
    _shot(310, "MTL", 1, 11, 0.50, away_empty=1),           # filet vide : ni 5 c. 5 ni haut danger exclu
])


def test_game_rows_match_moneypuck_definitions():
    from nhl.data.xg_nhlapi import game_rows
    rows = {r["playerId"]: r for r in game_rows(2025020001, SHOTS, SHIFTS, PBP)}
    assert set(rows) == {11, 12, 21, 22}
    p11, p12, p21, p22 = rows[11], rows[12], rows[21], rows[22]
    assert p11["I_F_xGoals"] == pytest.approx(0.75) and p11["I_F_highDangerShots"] == 2
    assert p11["I_F_highDangerxGoals"] == pytest.approx(0.75) and p11["pp_ixg"] == 0
    assert p11["OnIce_F_xGoals"] == pytest.approx(0.75) and p11["OnIce_A_xGoals"] == pytest.approx(0.10)
    assert p11["ev_onice_xgf"] == pytest.approx(0.25) and p11["ev_onice_xga"] == 0
    assert (p11["I_F_oZoneShiftStarts"], p11["I_F_dZoneShiftStarts"], p11["icetime"]) == (1, 0, 120)
    assert p12["OnIce_F_xGoals"] == pytest.approx(0.25) and p12["icetime"] == 120
    assert p21["I_F_xGoals"] == pytest.approx(0.10) and p21["pp_ixg"] == pytest.approx(0.10)
    assert p21["OnIce_A_xGoals"] == pytest.approx(0.75) and p21["ev_onice_xga"] == pytest.approx(0.25)
    assert (p21["I_F_oZoneShiftStarts"], p21["I_F_dZoneShiftStarts"], p21["icetime"]) == (0, 1, 90)
    assert p22["OnIce_F_xGoals"] == 0 and p22["OnIce_A_xGoals"] == 0 and p22["icetime"] == 120


def test_game_rows_skip_incomplete_games():
    from nhl.data.xg_nhlapi import game_rows
    assert game_rows(2025020001, SHOTS, None, PBP) == []
    assert game_rows(2025020001, SHOTS, {"data": []}, PBP) == []


def test_collect_only_rebuilds_finished_new_games(tmp_path, monkeypatch):
    from nhl.data import xg_nhlapi as xa
    monkeypatch.setattr(xa, "GAMELOG_DIR", str(tmp_path))
    shots = pd.concat([SHOTS, SHOTS.assign(game_id=20002, gameId=2025020002)], ignore_index=True)
    shots.drop(columns="gameId").to_parquet(tmp_path / "mp_shots_2025.parquet", index=False)
    asked = []
    monkeypatch.setattr(xa, "_fetch", lambda gids: _fake_fetch(gids, asked))
    first = xa.collect(2025, finished={2025020001})
    assert asked == [[2025020001]] and set(first["gameId"]) == {2025020001}
    second = xa.collect(2025, finished={2025020001, 2025020002})
    assert asked[-1] == [2025020002] and set(second["gameId"]) == {2025020001, 2025020002}
    assert xa.collect(2025, finished={2025020001, 2025020002}).equals(second) and len(asked) == 2


async def _fake_fetch_coro(gids):
    return [SHIFTS] * len(gids), [PBP] * len(gids)


def _fake_fetch(gids, asked):
    asked.append(list(gids))
    return _fake_fetch_coro(gids)
