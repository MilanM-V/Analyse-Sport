"""Parsing API NHL -> schéma unique (mêmes définitions que MoneyPuck)."""
from nhl.data.gamelog_nhlapi import parse_game


def _box():
    def sk(pid, pos, sog, toi="15:00"):
        return {"playerId": pid, "name": {"default": f"P. {pid}"}, "position": pos, "sog": sog, "toi": toi}
    return {
        "id": 2024020001, "season": 20242025, "gameType": 2, "gameDate": "2024-10-10",
        "homeTeam": {"id": 1, "abbrev": "AAA"}, "awayTeam": {"id": 2, "abbrev": "BBB"},
        "playerByGameStats": {
            "homeTeam": {"forwards": [sk(10, "C", 3), sk(11, "L", 1)], "defense": [sk(12, "D", 0)]},
            "awayTeam": {"forwards": [sk(20, "R", 2), sk(21, "C", 0, toi="0:00")], "defense": []},
        },
    }


def _pbp():
    reg = {"periodType": "REG"}
    return {
        "rosterSpots": [{"playerId": 10, "firstName": {"default": "Ann"}, "lastName": {"default": "Ten"}}],
        "plays": [
            # But dom. en 5c4 (dom 5 patineurs, ext 4) : situationCode = 1 4 5 1
            {"typeDescKey": "goal", "situationCode": "1451", "periodDescriptor": reg,
             "details": {"eventOwnerTeamId": 1, "scoringPlayerId": 10, "assist1PlayerId": 11, "assist2PlayerId": 12}},
            {"typeDescKey": "missed-shot", "situationCode": "1551", "periodDescriptor": reg,
             "details": {"eventOwnerTeamId": 2, "shootingPlayerId": 20}},
            {"typeDescKey": "blocked-shot", "situationCode": "1551", "periodDescriptor": reg,
             "details": {"eventOwnerTeamId": 1, "shootingPlayerId": 11}},
            # Tir au but : ignoré
            {"typeDescKey": "goal", "situationCode": "1010", "periodDescriptor": {"periodType": "SO"},
             "details": {"eventOwnerTeamId": 2, "scoringPlayerId": 20}},
        ],
    }


def test_parse_game_counts():
    rows = {r["playerId"]: r for r in parse_game(_box(), _pbp())}
    assert 21 not in rows                      # TOI nul : pas aligné
    assert rows[10]["name"] == "Ann Ten"
    assert (rows[10]["g"], rows[10]["pp_g"], rows[10]["pp_sog"]) == (1, 1, 1)
    assert (rows[11]["a1"], rows[12]["a2"]) == (1, 1)
    assert rows[11]["blocked_att"] == 1 and rows[20]["missed"] == 1
    assert rows[20]["g"] == 0                  # but en fusillade exclu
    assert rows[10]["season"] == 2024 and rows[20]["is_home"] == 0
