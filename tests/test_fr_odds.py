"""Cotes des books français (nhl/core/fr_odds.py) : parseurs, noms, rapprochement, intégration au moteur.

Aucun accès réseau : les pages sont des états JSON synthétiques reproduisant la structure
relevée le 2026-10-04 sur Winamax, Unibet.fr et Betclic.
"""
import asyncio
import json
import sqlite3

import pytest

from nhl.core import fr_odds as F
from nhl.core.fr_odds import _alert as real_alert  # avant le remplacement par la fixture de conftest


# ── Pages synthétiques ──────────────────────────────────────────────────────
WM_STATE = {
    "matches": {
        "1": {"tournamentId": 142, "title": "New York Rangers - Utah Mammoth", "matchStart": 2000},
        "2": {"tournamentId": 142, "title": "Boston Bruins - Toronto Maple Leafs", "matchStart": 1000},
        "3": {"tournamentId": 142, "title": "Vainqueur de la Coupe Stanley"},
        "4": {"tournamentId": 115, "title": "Djurgardens - Orebro HK", "matchStart": 500},
    },
    "bets": {
        "10": {"matchId": 1, "betTitle": "Buteur", "outcomes": [100, 101, 102]},
        "11": {"matchId": 1, "betTitle": "Passes décisives du joueur : 1 ou plus", "outcomes": [110]},
        "12": {"matchId": 1, "betTitle": "Passes décisives du joueur : 2 ou plus", "outcomes": [120]},
        "13": {"matchId": 2, "betTitle": "Buteur", "outcomes": [130]},
        "14": {"matchId": 1, "betTitle": "Points du joueur : 1 ou plus", "outcomes": [140]},
    },
    "outcomes": {"100": {"label": "Pavel Dorofeyev", "available": True},
                 "101": {"label": "Pettersson, Elias (1998)", "available": True},
                 "102": {"label": "Joueur Suspendu", "available": False},
                 "110": {"label": "Adam Fox", "available": True},
                 "120": {"label": "Adam Fox", "available": True},
                 "130": {"label": "David Pastrnak", "available": True},
                 "140": {"label": "Adam Fox", "available": True}},
    "odds": {"100": 2.8, "101": 3.5, "102": 4.0, "110": 1.8, "120": 5.0, "130": 2.1, "140": 1.45},
}
WM_PAGE = f"<script>var PRELOADED_STATE = {json.dumps(WM_STATE)};var BETTING_CONFIGURATION = {{}};</script>"
WM_GEO_PAGE = ('<script>var PRELOADED_STATE = {"cc": {}, "notifications": [], "terms": false, "events": {}, '
               '"browser": {"mobile": false}};var BETTING_CONFIGURATION = {};</script>')

UB_LIST = """
<a class="psel-event__link" title="Voir plus de paris pour le match : NY Rangers vs UTA HockeyClub | NHL"
   href="/paris-hockey-sur-glace/etats-unis/nhl/3383063/ny-rangers-vs-uta-hockeyclub">
<a title="Voir plus de paris pour le match : VEG GKnights vs CAL Flames | NHL"
   href="/paris-hockey-sur-glace/etats-unis/nhl/3383064/veg-gknights-vs-cal-flames">
<a title="Voir plus de paris pour le match : Lulea vs Malmo | SHL" href="/paris-hockey-sur-glace/suede/shl/1/lulea-vs-malmo">
"""
UB_STATE = {"EventsDetail": {"events": [{"groupedMarkets": [
    {"description": "Nombre de Buts - Joueur - Match (Hors TAB)", "markets": [
        {"description": "Nombre de Buts - Pavel Dorofeyev", "outcomes": [
            {"description": "Pavel Dorofeyev 2+", "price": "9,80"},
            {"description": "Pavel Dorofeyev 1+", "price": "2,75"}]},
        {"description": "Nombre de Buts - J.T. Miller", "outcomes": [{"description": "Miller, J.T. 1+", "price": "3,70"}]},
        {"description": "Nombre de Buts - Caché", "outcomes": [{"description": "Joueur Cache 1+", "price": "5,00", "hidden": True}]}]},
    {"description": "Nombre de Passes décisives - Joueur - Match", "markets": [
        {"description": "Nombre de Passes décisives - Gabriel Perreault",
         "outcomes": [{"description": "Gabe Perreault 1+", "price": "3,40"}]}]},
    {"description": "Nombre de Points - Joueur - Match (Hors TAB)", "markets": [
        {"description": "Nombre de Points - Adam Fox", "outcomes": [
            {"description": "Adam Fox 1+", "price": "1,50"}, {"description": "Adam Fox 2+", "price": "3,60"}]}]},
    {"description": "1 N 2 - Temps Réglementaire", "markets": [{"outcomes": [{"description": "NY Rangers", "price": "2,15"}]}]},
]}]}}
UB_PAGE = f'<script id="serverApp-state" type="application/json">{json.dumps(UB_STATE)}</script>'

BC_LIST = """
<a href="/hockey-sur-glace-sice_hockey/nhl-c83/new-york-rangers-utah-mammoth-m1231964559392768">
<a href="/hockey-sur-glace-sice_hockey/nhl-c83/vegas-golden-knights-st-louis-blues-m42">
<a href="/hockey-sur-glace-sice_hockey/ahl-c2128/hershey-bears-charlotte-checkers-m7">
"""
BC_STATE = {"hash1": {"match": {"subCategories": [{"markets": [
    {"name": "Buteur (prol. inc.)", "selectionMatrix": [], "splitCardGroups": [{"selections": [
        {"name": "Pavel Dorofeyev", "odds": 3.02, "status": 1}, {"name": "Mika Zibanejad", "odds": 3.12, "status": 1}]}]},
    {"name": "Double Chance Buteur", "splitCardGroups": [], "selectionMatrix": [{"selections": [
        {"selectionOneof": {"oneofKind": "selection", "selection": {"name": "A / B", "odds": 1.7}}}]}]},
    {"name": "Nombre de passes décisives du joueur", "splitCardGroups": [], "selectionMatrix": [], "groupMarkets": [
        {"name": "1 ou +", "selectionMatrix": [], "splitCardGroups": [{"selections": [{"name": "Adam Fox", "odds": 1.79, "status": 1}]}]},
        {"name": "2 ou +", "selectionMatrix": [], "splitCardGroups": [{"selections": [{"name": "Adam Fox", "odds": 4.9, "status": 1}]}]}]},
    {"name": "Nombre de points du joueur (buts + passes décisives)", "splitCardGroups": [], "selectionMatrix": [],
     "groupMarkets": [{"name": "1 ou +", "selectionMatrix": [], "splitCardGroups": [{"selections": [
         {"name": "Adam Fox", "odds": 1.48, "status": 1}]}]}]},
    {"name": "Buteur (prol. inc.)", "selectionMatrix": [], "splitCardGroups": [{"selections": [{"name": "Doublon", "odds": 9.0}]}]},
]}]}}}
BC_PAGE = f'<script id="ng-state" type="application/json">{json.dumps(BC_STATE)}</script>'


def _rows(rows):
    return sorted((r.market, r.player, r.price) for r in rows)


# ── Noms d'équipes et de joueurs ────────────────────────────────────────────
@pytest.mark.parametrize("label,abbr", [
    ("NY Rangers", "NYR"), ("UTA HockeyClub", "UTA"), ("VEG GKnights", "VGK"), ("CAL Flames", "CGY"), ("TOR MapleLeafs", "TOR"),
    ("MON Canadiens", "MTL"), ("WAS Capitals", "WSH"), ("WIN Jets", "WPG"), ("FLO Panthers", "FLA"),
    ("LA Kings", "LAK"), ("SJ Sharks", "SJS"), ("TB Lightning", "TBL"), ("Montréal Canadiens", "MTL"),
    ("St. Louis Blues", "STL"), ("Utah Mammoth", "UTA"), ("Vegas Golden Knights", "VGK"),
    ("New York Islanders", "NYI"), ("NYR", "NYR"), ("Toronto Maple Leafs", "TOR"), ("Inconnu FC", None),
])
def test_team_abbr(label, abbr):
    assert F.team_abbr(label) == abbr


@pytest.mark.parametrize("slug,teams", [
    ("new-york-rangers-utah-mammoth", ["NYR", "UTA"]),
    ("vegas-golden-knights-st-louis-blues", ["VGK", "STL"]),
    ("columbus-blue-jackets-detroit-red-wings", ["CBJ", "DET"]),
    ("toronto-maple-leafs-minnesota-wild", ["TOR", "MIN"]),
    ("utah-hockey-club-los-angeles-kings", ["UTA", "LAK"]),
])
def test_teams_in_betclic_slug(slug, teams):
    assert F.teams_in(slug) == teams


def test_clean_player_is_shared_with_saved_pages_parser():
    from nhl.scripts.parse_winamax_pages import clean_player
    assert clean_player is F.clean_player
    assert F.clean_player("Miller, J.T.") == "J.T. Miller"
    assert F.clean_player("Elias Pettersson (1998)") == "Elias Pettersson"


# ── Parseurs ────────────────────────────────────────────────────────────────
def test_winamax_listing_keeps_nhl_games_soonest_first():
    games = F.parse_winamax_listing(F.winamax_state(WM_PAGE))
    assert [(g.home, g.away, g.ref) for g in games] == [
        ("Boston Bruins", "Toronto Maple Leafs", "2"), ("New York Rangers", "Utah Mammoth", "1")]
    assert games[1].pair == frozenset({"NYR", "UTA"})


def test_winamax_match_reads_goals_assists_and_points_one_or_more():
    rows = F.parse_winamax_match(F.winamax_state(WM_PAGE), "1")
    assert _rows(rows) == [("ast", "Adam Fox", 1.8), ("but", "Elias Pettersson", 3.5), ("but", "Pavel Dorofeyev", 2.8),
                           ("pts", "Adam Fox", 1.45)]


def test_winamax_page_without_sports_data_is_unavailable():
    """Cas du VPS hors de France : la page arrive, mais sans `matches`."""
    with pytest.raises(F.BookUnavailable, match="IP hors de France"):
        F.winamax_state(WM_GEO_PAGE)
    with pytest.raises(F.BookUnavailable):
        F.winamax_state("<html>rien</html>")


def test_unibet_listing_and_match():
    games = F.parse_unibet_listing(UB_LIST)
    assert [g.pair for g in games] == [frozenset({"NYR", "UTA"}), frozenset({"VGK", "CGY"})]
    assert games[0].ref == "/paris-hockey-sur-glace/etats-unis/nhl/3383063/ny-rangers-vs-uta-hockeyclub"
    assert _rows(F.parse_unibet_match(UB_PAGE)) == [
        ("ast", "Gabe Perreault", 3.4), ("but", "J.T. Miller", 3.7), ("but", "Pavel Dorofeyev", 2.75),
        ("pts", "Adam Fox", 1.5)]


def test_betclic_listing_and_match():
    games = F.parse_betclic_listing(BC_LIST)
    assert [(g.home, g.away) for g in games] == [("NYR", "UTA"), ("VGK", "STL")]
    assert _rows(F.parse_betclic_match(BC_PAGE)) == [
        ("ast", "Adam Fox", 1.79), ("but", "Mika Zibanejad", 3.12), ("but", "Pavel Dorofeyev", 3.02),
        ("pts", "Adam Fox", 1.48)]


@pytest.mark.parametrize("parser", [F.parse_unibet_match, F.parse_betclic_match])
def test_match_page_without_state_is_unavailable(parser):
    with pytest.raises(F.BookUnavailable):
        parser("<html>maintenance</html>")


# ── Lecture des books (réseau remplacé) ─────────────────────────────────────
class _FakeClient:
    def __init__(self, *a, **k):
        pass


def _fake_adapters(monkeypatch, adapters):
    monkeypatch.setattr(F, "_Client", _FakeClient)
    monkeypatch.setattr(F, "_ADAPTERS", adapters)


PLAYERS = {"Pavel Dorofeyev": "NYR", "Gabriel Perreault": "NYR", "Clayton Keller": "UTA", "David Pastrnak": "BOS"}
CONF = F.FrConfig(enabled=True, books=("winamax", "unibet", "betclic"))


def test_fetch_fr_odds_matches_players_and_isolates_a_failing_book(monkeypatch):
    alerts = []
    monkeypatch.setattr(F, "_alert", lambda book, reason: alerts.append((book, reason)))

    def winamax(client, conf):
        raise F.BookUnavailable("winamax : page sans données sportives (IP hors de France ?)")

    def unibet(client, conf):
        return [F.BookGame("unibet", "NY Rangers", "UTA HockeyClub", "/u")], lambda g: [
            F.PropRow("but", "Pavel Dorofeyev", 2.75), F.PropRow("ast", "Gabe Perreault", 3.4),
            F.PropRow("but", "Joueur Inconnu", 9.0)]

    def betclic(client, conf):
        games = [F.BookGame("betclic", "BOS", "TOR", "/b2"), F.BookGame("betclic", "NYR", "UTA", "/b1")]
        return games, lambda g: [F.PropRow("but", "Pavel Dorofeyev", 3.02)]

    _fake_adapters(monkeypatch, {"winamax": winamax, "unibet": unibet, "betclic": betclic})
    res = F.fetch_fr_odds([("New York Rangers", "Utah Mammoth")], PLAYERS, conf=CONF)

    assert res.prices["Pavel Dorofeyev"]["BUTS"] == {"unibet": 2.75, "betclic": 3.02}
    assert res.prices["Gabriel Perreault"]["ASSISTS"] == {"unibet": 3.4}  # « Gabe » rapproché par initiale + nom
    assert "Joueur Inconnu" not in res.prices
    assert {"book": "unibet", "home": "NYR", "away": "UTA", "market": "but", "joueur": "Joueur Inconnu",
            "matched": False, "price": 9.0} in res.rows
    assert res.status["betclic"]["games"] == 1  # BOS-TOR listé mais pas demandé
    assert res.status["unibet"]["matched"] == 2 and res.status["unibet"]["rows"] == 3
    assert "IP hors de France" in res.status["winamax"]["error"]
    assert alerts == [("winamax", "winamax : page sans données sportives (IP hors de France ?)")]


def test_listed_game_without_any_player_odds_makes_the_book_unavailable(monkeypatch):
    alerts = []
    monkeypatch.setattr(F, "_alert", lambda book, reason: alerts.append(book))
    _fake_adapters(monkeypatch, {"unibet": lambda c, conf: ([F.BookGame("unibet", "NYR", "UTA", "/u")], lambda g: [])})
    res = F.fetch_fr_odds([("NYR", "UTA")], PLAYERS, books=["unibet"], conf=CONF)
    assert res.prices == {} and "aucune cote joueur" in res.status["unibet"]["error"]
    assert alerts == ["unibet"]


def test_unexpected_format_error_never_escapes(monkeypatch):
    def broken(client, conf):
        raise KeyError("EventsDetail")
    _fake_adapters(monkeypatch, {"unibet": broken})
    res = F.fetch_fr_odds([("NYR", "UTA")], PLAYERS, books=["unibet"], conf=CONF)
    assert res.status["unibet"]["error"].startswith("KeyError")


def test_page_cache_drops_expired_pages(monkeypatch):
    import time
    monkeypatch.setattr(F, "_CACHE", {"ancienne": (time.monotonic() - F.LIST_TTL - 1, "x" * 10),
                                      "recente": (time.monotonic(), "y")})
    F._cache_put("nouvelle", "z")
    assert set(F._CACHE) == {"recente", "nouvelle"}


def test_alert_is_sent_once_per_day_and_book(monkeypatch):
    import shared.telegram_hub as hub
    sent = []
    monkeypatch.setattr(hub, "send_telegram", lambda msg, recipient="channel": sent.append((recipient, msg)))
    monkeypatch.setattr(F, "_ALERTED", {})
    real_alert("betclic", "betclic : HTTP 403")
    real_alert("betclic", "betclic : HTTP 403")
    real_alert("unibet", "unibet : HTTP 500")
    assert [r for r, _ in sent] == ["admin", "admin"] and "Betclic" in sent[0][1]


# ── Cote d'exécution ────────────────────────────────────────────────────────
def _fr(prices):
    return F.FrOdds(prices=prices)


def test_apply_fr_prices_uses_best_playable_book_and_keeps_the_estimate():
    d = {"price": 2.9, "price_source": "soft", "bookmaker": "Proxy US", "p_novig": 0.3}
    results = {"Pavel Dorofeyev": {"BUTS": d, "BUTEUR": d}, "Gabriel Perreault": {}}
    fr = _fr({"Pavel Dorofeyev": {"BUTS": {"unibet": 2.75, "betclic": 3.02, "winamax": 3.10}},
              "Gabriel Perreault": {"ASSISTS": {"unibet": 3.4}}})
    conf = F.FrConfig(enabled=True, use_as_exec=True, exec_books=("unibet", "betclic"))
    assert F.apply_fr_prices(results, fr, conf) == 2
    assert d["price"] == 3.02 and d["bookmaker"] == "Betclic" and d["price_source"] == "fr"
    assert d["proxy_price"] == 2.9 and d["p_novig"] == 0.3
    assert d["fr_prices"]["winamax"] == 3.10  # journalisé, mais pas jouable (aucun compte)
    gp = results["Gabriel Perreault"]
    assert gp["ASSISTS"] is gp["PASSEUR"] and gp["ASSISTS"]["price"] == 3.4


def test_apply_fr_prices_without_exec_only_adds_the_reference():
    d = {"price": 2.9, "price_source": "soft"}
    results = {"Pavel Dorofeyev": {"BUTS": d, "BUTEUR": d}}
    F.apply_fr_prices(results, _fr({"Pavel Dorofeyev": {"BUTS": {"betclic": 3.02}}}),
                      F.FrConfig(enabled=True, use_as_exec=False))
    assert d["price"] == 2.9 and d["price_source"] == "soft" and d["fr_prices"] == {"betclic": 3.02}


def test_points_are_logged_but_never_become_the_execution_price():
    results = {}
    fr = _fr({"Adam Fox": {"POINTS": {"winamax": 1.45, "betclic": 1.48}}})
    conf = F.FrConfig(enabled=True, use_as_exec=True, exec_books=F.BOOKS)
    assert F.apply_fr_prices(results, fr, conf) == 0
    d = results["Adam Fox"]["POINTS"]
    assert d is results["Adam Fox"]["POINTEUR"] and d == {"fr_prices": {"winamax": 1.45, "betclic": 1.48}}


# ── Intégration : fetch_nhl_odds + journalisation book_odds ─────────────────
def test_fetch_nhl_odds_uses_fr_price_and_logs_every_quote(tmp_path, monkeypatch):
    import nhl.core.database as db
    import nhl.core.odds as odds
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "bot.db"))
    db.init_db()

    async def fake_odds_api(sport, market, players_map, **kw):
        if market == "player_goal_scorer_anytime":
            return {"Pavel Dorofeyev": {"GOAL_SCORER_ANYTIME": {
                "price": 2.9, "price_source": "soft", "soft_median": 2.69, "pin_yes": 3.1, "pin_no": 1.38,
                "p_novig": 0.29}}}
        return {}
    monkeypatch.setattr(odds.OddsAPIClient, "fetch_odds", staticmethod(fake_odds_api))
    conf = F.FrConfig(enabled=True, use_as_exec=True, exec_books=("unibet", "betclic"))
    monkeypatch.setattr(F, "settings", lambda: conf)
    monkeypatch.setattr(F, "fetch_fr_odds", lambda games, players_map, books=None, conf=None: _fr(
        {"Pavel Dorofeyev": {"BUTS": {"betclic": 3.02, "unibet": 2.75}}}))

    res = asyncio.run(odds.fetch_nhl_odds({"Pavel Dorofeyev": "NYR"}, games=[("NYR", "UTA")],
                                          log_moment="vague", session_date="2026-10-05"))
    d = res["Pavel Dorofeyev"]["BUTS"]
    assert (d["price"], d["bookmaker"], d["price_source"], d["proxy_price"]) == (3.02, "Betclic", "fr", 2.9)

    conn = sqlite3.connect(tmp_path / "bot.db")
    rows = conn.execute("SELECT moment, home, away, market, joueur, book, cote, cote_non FROM book_odds "
                        "ORDER BY book").fetchall()
    conn.close()
    assert rows == [
        ("vague", "NYR", "UTA", "but", "Pavel Dorofeyev", "betclic", 3.02, None),
        ("vague", "NYR", "UTA", "but", "Pavel Dorofeyev", "pinnacle", 3.1, 1.38),
        ("vague", "NYR", "UTA", "but", "Pavel Dorofeyev", "unibet", 2.75, None),
        ("vague", "NYR", "UTA", "but", "Pavel Dorofeyev", "us_median", 2.69, None),
    ]


def test_fr_failure_keeps_the_estimate(monkeypatch):
    import nhl.core.odds as odds

    async def fake_odds_api(sport, market, players_map, **kw):
        return {"A B": {"GOAL_SCORER_ANYTIME": {"price": 2.9, "price_source": "soft"}}} \
            if market == "player_goal_scorer_anytime" else {}

    def boom(*a, **k):
        raise RuntimeError("réseau coupé")
    monkeypatch.setattr(odds.OddsAPIClient, "fetch_odds", staticmethod(fake_odds_api))
    monkeypatch.setattr(F, "settings", lambda: F.FrConfig(enabled=True, use_as_exec=True))
    monkeypatch.setattr(F, "fetch_fr_odds", boom)
    res = asyncio.run(odds.fetch_nhl_odds({"A B": "BOS"}, games=[("BOS", "TOR")]))
    assert res["A B"]["BUTS"]["price"] == 2.9 and res["A B"]["BUTS"]["price_source"] == "soft"


# ── Affichage Telegram ──────────────────────────────────────────────────────
FR_PICK = {"Joueur": "Pavel Dorofeyev", "Ref": "B12", "Cote": 3.02, "Bookmaker": "Betclic", "PriceSource": "fr",
           "CoteSeuil": 2.85, "Mise": "1.0 U", "IsHome": True, "Match": "New York Rangers vs Utah Mammoth",
           "FrPrices": {"betclic": 3.02, "unibet": 2.75, "winamax": 2.80}}


def test_pick_line_shows_real_book_price():
    from nhl.core.formatter import _pick_line
    line = _pick_line(FR_PICK)
    assert "@3.02" in line and "Betclic" in line and "mini 2.85" in line and "B12" not in line


def test_pick_card_lists_the_other_books():
    from nhl.core.services import pick_card_text
    txt = pick_card_text(FR_PICK, "but")
    assert "@3.02</b> chez <b>Betclic" in txt and "mini 2.85" in txt and "B12" in txt
    assert "Autres : Winamax 2.80 · Unibet 2.75" in txt


@pytest.mark.parametrize("moment,asks_points", [("apercu", True), ("vague", True), ("cloture", False), (None, False)])
def test_points_market_is_requested_only_when_logging_a_wave(tmp_path, monkeypatch, moment, asks_points):
    """[fr_odds] log_points : player_points demandé à l'aperçu et aux picks confirmés, jamais à T-5."""
    import nhl.core.database as db
    import nhl.core.odds as odds
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "bot.db"))
    db.init_db()
    asked = []

    async def fake_odds_api(sport, market, players_map, **kw):
        asked.append(market)
        if market == "player_points":
            return {"Adam Fox": {"POINTS": {"soft_median": 1.52, "pin_yes": 1.55, "pin_no": 2.45, "p_novig": 0.6}}}
        return {}
    monkeypatch.setattr(odds.OddsAPIClient, "fetch_odds", staticmethod(fake_odds_api))
    monkeypatch.setattr(F, "settings", lambda: F.FrConfig(enabled=True, use_as_exec=True, log_points=True))
    monkeypatch.setattr(F, "fetch_fr_odds", lambda *a, **k: _fr({"Adam Fox": {"POINTS": {"winamax": 1.45}}}))

    res = asyncio.run(odds.fetch_nhl_odds({"Adam Fox": "NYR"}, games=[("NYR", "UTA")], log_moment=moment,
                                          session_date="2026-10-07"))
    assert ("player_points" in asked) is asks_points
    assert "price" not in res["Adam Fox"]["POINTS"] or res["Adam Fox"]["POINTS"].get("price_source") != "fr"
    if moment == "vague":
        conn = sqlite3.connect(tmp_path / "bot.db")
        rows = conn.execute("SELECT market, book, cote, cote_non FROM book_odds ORDER BY book").fetchall()
        conn.close()
        assert rows == [("pts", "pinnacle", 1.55, 2.45), ("pts", "us_median", 1.52, None), ("pts", "winamax", 1.45, None)]
