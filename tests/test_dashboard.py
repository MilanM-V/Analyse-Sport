"""Dashboard Streamlit : transformations des données NHL, lecture de la base du bot, pages sans réseau."""
import os
import sqlite3

import pandas as pd
import pytest

from nhl.dash import api, botdata

STANDINGS = {"standings": [
    {"leagueSequence": 2, "teamName": {"default": "Montréal Canadiens"}, "teamAbbrev": {"default": "MTL"},
     "conferenceName": "Eastern", "divisionName": "Atlantic", "gamesPlayed": 2, "wins": 1, "losses": 0, "otLosses": 1,
     "points": 3, "pointPctg": 0.75, "goalFor": 8, "goalAgainst": 8, "goalDifferential": 0, "streakCode": "OT",
     "streakCount": 1, "l10Wins": 1, "l10Losses": 0, "l10OtLosses": 1, "teamLogo": "https://assets.example/x.svg"},
    {"leagueSequence": 1, "teamName": {"default": "Edmonton Oilers"}, "teamAbbrev": {"default": "EDM"},
     "conferenceName": "Western", "divisionName": "Pacific", "gamesPlayed": 3, "wins": 2, "losses": 0, "otLosses": 1,
     "points": 5, "pointPctg": 0.833, "goalFor": 17, "goalAgainst": 14, "goalDifferential": 3, "teamLogo": "https://assets.example/y.svg"}]}
LEADERS = {"goals": [{"id": 8480803, "firstName": {"default": "Evan"}, "lastName": {"default": "Bouchard"},
                      "teamAbbrev": "EDM", "position": "D", "value": 4, "headshot": "https://assets.example/h.png", "teamLogo": "https://assets.example/l.svg"}],
           "assists": [], "points": []}
SCORES = {"games": [{"id": 1, "startTimeUTC": "2026-10-03T23:00:00Z", "gameState": "OFF",
                     "homeTeam": {"abbrev": "BUF", "score": 4, "sog": 28, "logo": "https://assets.example/b.svg"},
                     "awayTeam": {"abbrev": "CHI", "score": 3, "sog": 15, "logo": "https://assets.example/c.svg"},
                     "gameOutcome": {"lastPeriodType": "REG"},
                     "goals": [{"name": {"default": "T. Thompson"}, "teamAbbrev": "BUF"}]}]}
SCHEDULE = {"gameWeek": [{"date": "2026-10-05", "games": [
    {"id": 2, "startTimeUTC": "2026-10-05T23:00:00Z", "gameType": 2, "gameState": "FUT",
     "homeTeam": {"abbrev": "MTL"}, "awayTeam": {"abbrev": "TOR"}}]}]}
ROSTER = {"forwards": [{"id": 1, "sweaterNumber": 14, "firstName": {"default": "Nick"}, "lastName": {"default": "Suzuki"},
                        "positionCode": "C", "headshot": "https://assets.example/s.png"},
                       {"id": 2, "sweaterNumber": 20, "firstName": {"default": "Juraj"}, "lastName": {"default": "Slafkovsky"},
                        "positionCode": "L"}],
          "defensemen": [{"id": 3, "sweaterNumber": 48, "firstName": {"default": "Lane"}, "lastName": {"default": "Hutson"},
                          "positionCode": "D"}],
          "goalies": [{"id": 4, "sweaterNumber": 35, "firstName": {"default": "Sam"}, "lastName": {"default": "Montembeault"},
                       "positionCode": "G"}]}
CLUB_STATS = {"skaters": [{"playerId": 1, "firstName": {"default": "Nick"}, "lastName": {"default": "Suzuki"},
                           "positionCode": "C", "gamesPlayed": 2, "goals": 1, "assists": 2, "points": 3}],
              "goalies": [{"playerId": 4, "firstName": {"default": "Sam"}, "lastName": {"default": "Montembeault"},
                           "gamesPlayed": 2, "wins": 1, "savePercentage": 0.9}]}
TEAM_SCHEDULE = {"games": [
    {"gameType": 2, "gameDate": "2026-10-01", "gameState": "OFF", "homeTeam": {"abbrev": "MTL", "score": 3},
     "awayTeam": {"abbrev": "TOR", "score": 2}, "gameOutcome": {"lastPeriodType": "REG"}},
    {"gameType": 2, "gameDate": "2026-10-03", "gameState": "OFF", "homeTeam": {"abbrev": "PIT", "score": 6},
     "awayTeam": {"abbrev": "MTL", "score": 5}, "gameOutcome": {"lastPeriodType": "OT"}},
    {"gameType": 1, "gameDate": "2026-09-20", "gameState": "OFF", "homeTeam": {"abbrev": "MTL", "score": 1},
     "awayTeam": {"abbrev": "BOS", "score": 0}}]}
LANDING = {"playerId": 1, "firstName": {"default": "Nick"}, "lastName": {"default": "Suzuki"}, "position": "C",
           "currentTeamAbbrev": "MTL", "fullTeamName": {"default": "Canadiens de Montréal"}, "sweaterNumber": 14,
           "birthDate": "1999-08-10", "birthCity": {"default": "London"}, "birthCountry": "CAN",
           "careerTotals": {"regularSeason": {"gamesPlayed": 500, "goals": 150, "assists": 250, "points": 400}},
           "seasonTotals": [
               {"season": 20242025, "leagueAbbrev": "NHL", "gameTypeId": 2, "teamName": {"default": "Canadiens"},
                "gamesPlayed": 82, "goals": 30, "assists": 59, "points": 89},
               {"season": 20242025, "leagueAbbrev": "NHL", "gameTypeId": 3, "teamName": {"default": "Canadiens"},
                "gamesPlayed": 5, "goals": 1, "assists": 1, "points": 2},
               {"season": 20182019, "leagueAbbrev": "OHL", "gameTypeId": 2, "teamName": {"default": "Guelph"},
                "gamesPlayed": 59, "goals": 34, "assists": 59, "points": 93},
               {"season": 20232024, "leagueAbbrev": "NHL", "gameTypeId": 2, "teamName": {"default": "Canadiens"},
                "gamesPlayed": 40, "goals": 10, "assists": 20, "points": 30},
               {"season": 20232024, "leagueAbbrev": "NHL", "gameTypeId": 2, "teamName": {"default": "Kings"},
                "gamesPlayed": 42, "goals": 23, "assists": 24, "points": 47}]}
GAMELOG = {"gameLog": [{"gameDate": "2026-10-03", "opponentAbbrev": "PIT", "homeRoadFlag": "R", "goals": 1, "assists": 1,
                        "points": 2}, {"gameDate": "2026-10-01", "opponentAbbrev": "TOR", "homeRoadFlag": "H",
                                       "goals": 0, "assists": 1, "points": 1}]}


def test_standings_sorted_by_league_rank():
    df = api.standings(STANDINGS)
    assert df["abbrev"].tolist() == ["EDM", "MTL"] and df.loc[1, "10 derniers"] == "1-0-1"


def test_leaders_and_scores():
    lead = api.leaders(LEADERS, "goals")
    assert lead.loc[0, "Joueur"] == "Evan Bouchard" and lead.loc[0, "Poste"] == "Défenseur"
    sc = api.scores(SCORES)
    assert sc.loc[0, ["Extérieur", "Score ext.", "Score dom.", "Domicile"]].tolist() == ["CHI", 3, 4, "BUF"]
    assert "T. Thompson (BUF)" in sc.loc[0, "Buteurs"]
    assert api.schedule_week(SCHEDULE).loc[0, "Domicile"] == "MTL"


def test_roster_grouped_by_position():
    r = api.roster(ROSTER)
    assert r["Poste"].tolist() == ["Centre", "Ailier gauche", "Défenseur", "Gardien"]


def test_club_stats_formats_time_and_percent():
    data = {"skaters": [{"playerId": 1, "firstName": {"default": "A"}, "lastName": {"default": "B"}, "points": 1,
                         "shootingPctg": 0.16667, "avgTimeOnIcePerGame": 1243.0}], "goalies": []}
    r = api.club_stats(data)["skaters"].iloc[0]
    assert r["TG moy."] == "20:43" and r["% tir"] == 16.7


def test_team_schedule_results_regular_season_only():
    s = api.team_schedule(TEAM_SCHEDULE, "MTL")
    assert len(s) == 2  # présaison exclue
    assert s["Résultat"].tolist() == ["V", "DP"] and s["Lieu"].tolist() == ["Domicile", "Extérieur"]


def test_player_profile_history_merges_teams_and_keeps_nhl_regular_season():
    pr = api.player_profile(LANDING)
    h = pr["historique"].set_index("Saison")
    assert list(h.index) == ["2023-24", "2024-25"]          # OHL et séries exclues
    assert h.loc["2023-24", "Pts"] == 77 and h.loc["2023-24", "Équipe"] == "Canadiens / Kings"
    assert h.loc["2024-25", "Pts / match"] == round(89 / 82, 2)
    assert pr["carriere"]["points"] == 400
    g = api.player_gamelog(GAMELOG)
    assert g["Date"].tolist() == ["2026-10-01", "2026-10-03"]


def test_season_id():
    from datetime import date
    assert api.season_id(date(2026, 10, 4)) == "20262027" and api.season_id(date(2027, 3, 1)) == "20262027"


# ── Base du bot ─────────────────────────────────────────────────────────────
@pytest.fixture
def bot_db(tmp_path):
    import nhl.core.database as db
    old = db.DB_PATH
    db.DB_PATH = str(tmp_path / "bot.db")
    try:
        db.init_db()
        rows = [("picks", {"date": "2026-10-20", "joueur": "A", "equipe": "MTL", "cote": 4.0, "mise": 1.0, "but": 1,
                           "closing_p_novig": 0.3}),
                ("picks", {"date": "2026-10-20", "joueur": "B", "equipe": "MTL", "cote": 3.0, "mise": 1.0, "but": 0}),
                ("picks", {"date": "2026-10-21", "joueur": "C", "equipe": "TOR", "cote": 3.0, "mise": 1.0,
                           "cote_reelle": 3.2, "pris": 1}),
                ("picks_assists", {"date": "2026-10-21", "joueur": "D", "equipe": "TOR", "cote": 2.5, "mise": 2.0,
                                   "statut": "void"}),
                ("picks_assists", {"date": "2026-10-21", "joueur": "E", "equipe": "TOR", "cote": 2.5, "mise": 2.0,
                                   "pris": 0, "assist": 1})]
        for t, r in rows:
            db.insert_pick(t, r)
        yield db.DB_PATH
    finally:
        db.DB_PATH = old


def test_bot_picks_statuses_and_profit(bot_db):
    p = botdata.picks(bot_db).set_index("joueur")
    assert p.loc[["A", "B", "C", "D", "E"], "statut"].tolist() == ["gagné", "perdu", "en attente", "annulé", "non pris"]
    assert p.loc["A", "profit"] == 3.0 and p.loc["B", "profit"] == -1.0
    assert pd.isna(p.loc["E", "profit"])           # non pris : exclu du gain
    assert p.loc["C", "cote"] == 3.2                # cote réellement prise prioritaire
    assert p.loc["A", "ev_cloture"] == pytest.approx(0.3 * 4.0 - 1)
    s = botdata.summary(botdata.picks(bot_db))
    assert (s["n_joues"], s["gain"], s["en_attente"]) == (2, 2.0, 1) and s["roi"] == 1.0


def test_list_and_read_tables_read_only(bot_db):
    t = botdata.list_tables(bot_db)
    assert t["picks"] == 3 and t["picks_assists"] == 2
    assert len(botdata.read_table("picks", bot_db)) == 3
    with pytest.raises(sqlite3.OperationalError):
        conn = botdata._connect(bot_db)
        conn.execute("DELETE FROM picks")
    assert botdata.read_table("absente", bot_db).empty


# ── Pages Streamlit, sans réseau ────────────────────────────────────────────
FIXTURES = {"standings/now": STANDINGS, "score/": SCORES, "schedule/": SCHEDULE, "roster/": ROSTER,
            "club-stats/": CLUB_STATS, "club-schedule-season/": TEAM_SCHEDULE, "player/1/landing": LANDING,
            "player/1/game-log": GAMELOG, "skater-stats-leaders": LEADERS}

APP = """
import sys
sys.path.insert(0, {root!r})
import streamlit as st
from nhl.dash import api, pages
from tests_fixtures import FIXTURES
api.get_json = lambda path, timeout=20: next(v for k, v in FIXTURES.items() if path.startswith(k))
pages.PAGES.update(team=None, player=None)
st.session_state.setdefault("player_id", 1)
st.session_state.setdefault("team", "MTL")
pages.{page}()
"""


def test_img_skips_missing_url():
    from nhl.dash import ui

    class Col:
        called = False

        def image(self, *a, **k):
            Col.called = True
    ui.img(Col(), None, 40)
    ui.img(Col(), "", 40)
    assert not Col.called
    ui.img(Col(), "https://x/y.png", 40)
    assert Col.called


@pytest.mark.parametrize("page", ["page_bot", "page_db", "page_standings", "page_leaders", "page_results",
                                  "page_calendar", "page_team", "page_player", "page_about"])
def test_dashboard_pages_render_offline(page, tmp_path, monkeypatch):
    from streamlit.testing.v1 import AppTest
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    (tmp_path / "tests_fixtures.py").write_text(f"FIXTURES = {FIXTURES!r}\n", encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    at = AppTest.from_string(APP.format(root=root, page=page), default_timeout=60).run()
    assert not at.exception, [e.value for e in at.exception]
