"""
core/odds_logging.py — Journalisation de données de marché pour de FUTURES features (audit P2).

Rien ici n'influence les paris du soir. On accumule ce qui manque à l'historique pour
entraîner un jour des features de marché :
- `match_context` : ligne de total de buts, cotes 1N2, probabilité de victoire (Shin) et
  gardiens titulaires annoncés (RotoWire), une ligne par match et par scan ;
- `props_log` : cotes points et tirs cadrés (lignes 0.5 / 1.5 / 2.5), derrière
  `[betting] log_extra_markets` (désactivé par défaut : double la consommation de crédits).
"""
import logging
from typing import Any, Dict, Iterable, List, Optional, Tuple

from nhl.config.settings import cfg
from nhl.core.database import get_connection
from shared.devig import devig_yes

logger = logging.getLogger("NHL.OddsLogging")

SPORT = "icehockey_nhl"
EXTRA_PROP_MARKETS = ("player_points", "player_shots_on_goal")


def _ensure_tables() -> None:
    conn = get_connection()
    try:
        conn.execute("""CREATE TABLE IF NOT EXISTS match_context (
            id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, date TEXT, home TEXT, away TEXT,
            commence_time TEXT, total_line REAL, over_price REAL, under_price REAL, total_book TEXT,
            home_price REAL, away_price REAL, p_home REAL, h2h_book TEXT,
            goalie_home TEXT, goalie_away TEXT)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS props_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, date TEXT, home TEXT, away TEXT,
            market TEXT, joueur TEXT, point REAL, side TEXT, book TEXT, price REAL)""")
        conn.commit()
    finally:
        conn.close()


def _pick_book(rows: List[Dict[str, Any]]) -> Optional[str]:
    """Pinnacle si présent (référence sharp), sinon le premier book disponible."""
    books = {r["book"] for r in rows}
    return "pinnacle" if "pinnacle" in books else (sorted(books)[0] if books else None)


def summarize_match_lines(rows: List[Dict[str, Any]], home: str, away: str) -> Dict[str, Any]:
    """Résumé h2h + totals d'un match à partir des lignes de `shared.odds_api.parse_outcomes`.

    La ligne de total retenue est la ligne principale du book de référence : celle dont
    les cotes Over / Under sont les plus proches (marché le plus équilibré).
    """
    out: Dict[str, Any] = {"total_line": None, "over_price": None, "under_price": None, "total_book": None,
                           "home_price": None, "away_price": None, "p_home": None, "h2h_book": None}
    tot = [r for r in rows if r["market"] == "totals"]
    book = _pick_book(tot)
    if book:
        lines: Dict[float, Dict[str, float]] = {}
        for r in tot:
            if r["book"] == book and r["point"] is not None:
                lines.setdefault(float(r["point"]), {})[str(r["name"]).lower()] = float(r["price"])
        full = {k: v for k, v in lines.items() if "over" in v and "under" in v}
        if full:
            line = min(full, key=lambda k: abs(full[k]["over"] - full[k]["under"]))
            out.update(total_line=line, over_price=full[line]["over"], under_price=full[line]["under"],
                       total_book=book)
    h2h = [r for r in rows if r["market"] == "h2h"]
    book = _pick_book(h2h)
    if book:
        prices = {r["name"]: float(r["price"]) for r in h2h if r["book"] == book}
        hp, ap = prices.get(home), prices.get(away)
        if hp and ap:
            out.update(home_price=hp, away_price=ap, p_home=devig_yes(hp, ap, "shin"), h2h_book=book)
    return out


async def log_match_context(games: Iterable[Tuple[str, str]], goalies: Dict[Tuple[str, str], Tuple[str, str]],
                            session_date: str) -> int:
    """Journalise ligne de total, 1N2 et gardiens titulaires des matchs du soir.

    Args:
        games: affiches [(domicile, extérieur)] en noms complets.
        goalies: {(domicile, extérieur): (gardien domicile, gardien extérieur)} (RotoWire).
        session_date: date de session NHL.

    Returns:
        Nombre de matchs journalisés.
    """
    from shared.odds_api import fetch_event_odds_raw, nhl_team_key
    from shared.utils import paris_now
    games = list(games)
    rows = await fetch_event_odds_raw(SPORT, games, ("h2h", "totals"), regions="eu,us", team_key=nhl_team_key())
    key = nhl_team_key()
    _ensure_tables()
    conn = get_connection()
    n = 0
    try:
        for home, away in games:
            ev = [r for r in rows if key(r["home"]) == key(home) and key(r["away"]) == key(away)]
            s = summarize_match_lines(ev, ev[0]["home"], ev[0]["away"]) if ev else summarize_match_lines([], home, away)
            gh, ga = goalies.get((home, away), (None, None))
            conn.execute(
                "INSERT INTO match_context (ts, date, home, away, commence_time, total_line, over_price, under_price, "
                "total_book, home_price, away_price, p_home, h2h_book, goalie_home, goalie_away) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (paris_now().isoformat(), session_date, home, away, ev[0]["commence_time"] if ev else None,
                 s["total_line"], s["over_price"], s["under_price"], s["total_book"], s["home_price"],
                 s["away_price"], s["p_home"], s["h2h_book"], gh, ga))
            n += 1
        conn.commit()
    finally:
        conn.close()
    logger.info(f"[Contexte] {n} match(s) journalisé(s) (total, 1N2, gardiens).")
    return n


async def log_extra_props(games: Iterable[Tuple[str, str]], session_date: str) -> int:
    """Journalise les cotes points / tirs cadrés si `[betting] log_extra_markets` est activé.

    Returns:
        Nombre de cotes journalisées (0 si l'option est désactivée : aucun appel API).
    """
    if not getattr(cfg.betting, "log_extra_markets", False):
        return 0
    from shared.odds_api import fetch_event_odds_raw, nhl_team_key
    from shared.utils import paris_now
    rows = await fetch_event_odds_raw(SPORT, list(games), EXTRA_PROP_MARKETS, regions="us", team_key=nhl_team_key())
    _ensure_tables()
    conn = get_connection()
    try:
        ts = paris_now().isoformat()
        conn.executemany(
            "INSERT INTO props_log (ts, date, home, away, market, joueur, point, side, book, price) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [(ts, session_date, r["home"], r["away"], r["market"], r["description"], r["point"],
              str(r["name"]).lower(), r["book"], r["price"]) for r in rows])
        conn.commit()
    finally:
        conn.close()
    logger.info(f"[Props] {len(rows)} cote(s) points / tirs journalisée(s).")
    return len(rows)

