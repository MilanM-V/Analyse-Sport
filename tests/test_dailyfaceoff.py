"""Journal Daily Faceoff (lignes, unités spéciales, blessés) : lecture du JSON et écriture en base."""
import sqlite3

# Slugs relevés sur dailyfaceoff.com le 2026-10-08 (pageProps.sortedTeams)
DFO_SLUGS = {
    "ANA": "anaheim-ducks", "BOS": "boston-bruins", "BUF": "buffalo-sabres", "CGY": "calgary-flames",
    "CAR": "carolina-hurricanes", "CHI": "chicago-blackhawks", "COL": "colorado-avalanche",
    "CBJ": "columbus-blue-jackets", "DAL": "dallas-stars", "DET": "detroit-red-wings", "EDM": "edmonton-oilers",
    "FLA": "florida-panthers", "LAK": "los-angeles-kings", "MIN": "minnesota-wild", "MTL": "montreal-canadiens",
    "NSH": "nashville-predators", "NJD": "new-jersey-devils", "NYI": "new-york-islanders",
    "NYR": "new-york-rangers", "OTT": "ottawa-senators", "PHI": "philadelphia-flyers",
    "PIT": "pittsburgh-penguins", "SJS": "san-jose-sharks", "SEA": "seattle-kraken", "STL": "st-louis-blues",
    "TBL": "tampa-bay-lightning", "TOR": "toronto-maple-leafs", "UTA": "utah-mammoth",
    "VAN": "vancouver-canucks", "VGK": "vegas-golden-knights", "WSH": "washington-capitals",
    "WPG": "winnipeg-jets",
}


def _player(name, pid, pos, cat, grp, injury=None, gtd=False):
    return {"name": name, "playerId": pid, "positionIdentifier": pos, "categoryIdentifier": cat,
            "groupIdentifier": grp, "injuryStatus": injury, "gameTimeDecision": gtd, "rating": None}


NEXT_DATA = {"props": {"pageProps": {"combinations": {
    "teamAbbreviation": "MON", "sourceName": "Line Combinations from last game",
    "source": "https://www.naturalstattrick.com/game.php?season=20262027&game=20045",
    "updatedAt": "2026-10-08T14:40:45.750Z",
    "players": [_player("Cole Caufield", 30424, "lw", "ev", "f1"), _player("Nick Suzuki", 2789, "c", "pp", "pp1"),
                _player("Kaiden Guhle", 3001, "ld", "oi", "ir", injury="out"),
                _player("Oliver Kapanen", 3002, "c", "ev", "f3", gtd=True)]}}}}


def test_slugs_match_daily_faceoff_for_all_32_teams():
    from nhl.config.constants import TEAM_ABBR_TO_FULL
    from nhl.core.dailyfaceoff import team_slug
    assert set(TEAM_ABBR_TO_FULL) == set(DFO_SLUGS)
    assert {a: team_slug(a) for a in DFO_SLUGS} == DFO_SLUGS


def test_parse_combinations_keeps_lines_injuries_and_gtd():
    from nhl.core.dailyfaceoff import parse_combinations
    d = parse_combinations(NEXT_DATA)
    assert d["source_name"] == "Line Combinations from last game" and d["updated_at"].startswith("2026-10-08")
    assert [(p["player"], p["category"], p["grp"], p["injury"], p["gtd"]) for p in d["players"]] == [
        ("Cole Caufield", "ev", "f1", None, 0), ("Nick Suzuki", "pp", "pp1", None, 0),
        ("Kaiden Guhle", "oi", "ir", "out", 0), ("Oliver Kapanen", "ev", "f3", None, 1)]


def test_log_team_lines_writes_rows_and_skips_unreadable_teams(tmp_path, monkeypatch):
    import nhl.core.database as db
    from nhl.core.dailyfaceoff import log_team_lines, parse_combinations
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "bot.db"))
    data = parse_combinations(NEXT_DATA)
    n = log_team_lines(["MTL", "TOR"], "2026-10-08", fetch=lambda t: data if t == "MTL" else None, pause_s=0)
    assert n == 4
    conn = sqlite3.connect(tmp_path / "bot.db")
    rows = conn.execute("SELECT date, team, player, grp, injury, gtd FROM dfo_lines ORDER BY id").fetchall()
    conn.close()
    assert rows[0] == ("2026-10-08", "MTL", "Cole Caufield", "f1", None, 0) and {r[1] for r in rows} == {"MTL"}
    assert log_team_lines(["TOR"], "2026-10-08", fetch=lambda t: None, pause_s=0) == 0


def test_wave_logs_both_teams_of_each_match(monkeypatch):
    from types import SimpleNamespace

    from nhl.config.settings import cfg
    from nhl.core import dailyfaceoff
    from nhl.core.bot_logic import NhlBot
    seen = {}
    monkeypatch.setattr(dailyfaceoff, "log_team_lines", lambda teams, date: seen.update(teams=set(teams), date=date))
    monkeypatch.setattr(cfg.journal, "dailyfaceoff", True)
    bot = SimpleNamespace(compos_en_memoire={"g1": {"match_info": {"home": "MTL", "away": "L.A"}},
                                             "g2": {"match_info": {"home": "TOR", "away": "BOS"}}},
                          get_nhl_session_date=lambda: "2026-10-08")
    NhlBot._log_dailyfaceoff(bot, ["g1", "g2"])
    assert seen == {"teams": {"MTL", "LAK", "TOR", "BOS"}, "date": "2026-10-08"}
    monkeypatch.setattr(cfg.journal, "dailyfaceoff", False)
    seen.clear()
    NhlBot._log_dailyfaceoff(bot, ["g1"])
    assert seen == {}


def test_wave_without_any_line_alerts_once_a_day(monkeypatch):
    """Journal vide sans aucun signal du 09 au 19/10/2026 : alerte Telegram, une fois par soirée."""
    from types import SimpleNamespace

    from nhl.config.settings import cfg
    from nhl.core import dailyfaceoff
    from nhl.core.bot_logic import NhlBot
    sent = []
    monkeypatch.setattr(cfg.journal, "dailyfaceoff", True)
    monkeypatch.setattr(dailyfaceoff, "log_team_lines", lambda teams, date: 0)  # toutes les pages illisibles
    monkeypatch.setattr(dailyfaceoff, "FAILURES", {"MTL": "HTTP 403", "TOR": "HTTP 403"})
    bot = SimpleNamespace(compos_en_memoire={"g1": {"match_info": {"home": "MTL", "away": "TOR"}}},
                          get_nhl_session_date=lambda: "2026-10-19", telegram=SimpleNamespace(send_message=sent.append))
    NhlBot._log_dailyfaceoff(bot, ["g1"])
    NhlBot._log_dailyfaceoff(bot, ["g1"])  # 2e vague du même soir : pas de 2e alerte
    assert len(sent) == 1 and "Daily Faceoff" in sent[0]
    assert "HTTP 403 (2 équipes) : le site refuse les requêtes du serveur" in sent[0]  # la cause, en clair
    assert "picks ne sont pas touchés" in sent[0]
    monkeypatch.setattr(dailyfaceoff, "log_team_lines", lambda teams, date: 42)
    bot.get_nhl_session_date = lambda: "2026-10-20"
    NhlBot._log_dailyfaceoff(bot, ["g1"])  # lignes écrites : aucune alerte
    assert len(sent) == 1

    def boom(teams, date):
        raise RuntimeError("réseau")

    monkeypatch.setattr(dailyfaceoff, "log_team_lines", boom)
    bot.get_nhl_session_date = lambda: "2026-10-21"
    NhlBot._log_dailyfaceoff(bot, ["g1"])  # exception : la vague continue, alerte envoyée
    assert len(sent) == 2 and "erreur du bot (RuntimeError)" in sent[1]


def test_fetch_tries_a_second_browser_and_keeps_the_reason(monkeypatch):
    from nhl.core import dailyfaceoff
    monkeypatch.setattr(dailyfaceoff, "FAILURES", {})
    lines = {"source_name": "x", "source": "x", "updated_at": "x", "players": []}
    tried = []

    def page(url, imp, timeout):
        tried.append(imp)
        return (None, "HTTP 403") if imp == "chrome" else (lines, None)

    monkeypatch.setattr(dailyfaceoff, "_read_page", page)
    assert dailyfaceoff.fetch_team_lines("MTL") == lines  # 1re empreinte refusée, 2e acceptée
    assert tried == ["chrome", "safari"] and dailyfaceoff.FAILURES == {}
    monkeypatch.setattr(dailyfaceoff, "_read_page", lambda url, imp, timeout: (None, "HTTP 403"))
    assert dailyfaceoff.fetch_team_lines("TOR") is None
    assert dailyfaceoff.FAILURES == {"TOR": "HTTP 403"}
    assert dailyfaceoff.failure_summary() == "HTTP 403 (1 équipe)"
    # Lecteur injecté qui échoue sans raison : « illisible » ; remise à zéro à chaque vague
    assert dailyfaceoff.log_team_lines(["BOS"], "2026-10-22", fetch=lambda t: None, pause_s=0) == 0
    assert dailyfaceoff.FAILURES == {"BOS": "illisible"}
