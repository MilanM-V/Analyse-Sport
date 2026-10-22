"""
core/dailyfaceoff.py — Lignes du jour Daily Faceoff, journalisées pour de futures features.

Lit la page publique « line combinations » de chaque équipe (JSON `__NEXT_DATA__`) : trios
F1-F4, paires D1-D3, gardiens, unités PP1/PP2 et PK1/PK2, blessés (IR, « dtd » / « out »)
et « game-time decision ». Sans effet sur les paris : aucun historique de ces lignes
n'existe, on les enregistre pour pouvoir les tester comme features dans 2-3 mois
(nhl/reports/TESTS_PISTES_PINNACLE_2026-10-07.md, piste H15b).

Test manuel : python -m nhl.core.dailyfaceoff MTL TOR
"""
import json
import logging
import re
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

from nhl.config.constants import TEAM_ABBR_TO_FULL
from nhl.core.database import get_connection
from shared.odds_api import _norm

logger = logging.getLogger("NHL.DailyFaceoff")

URL = "https://www.dailyfaceoff.com/teams/{slug}/line-combinations"
_NEXT_DATA = re.compile(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', re.S)
# Slug = nom complet sans accents ni ponctuation, mots reliés par des tirets ; seule exception :
# TEAM_ABBR_TO_FULL garde « Utah Hockey Club », Daily Faceoff écrit « Utah Mammoth ».
_SLUG_OVERRIDES = {"UTA": "utah-mammoth"}
# Empreintes de navigateur (curl_cffi) essayées dans l'ordre : la 2e ne sert que si la 1re est refusée.
IMPERSONATE = ("chrome", "safari")
# Raison du dernier échec de lecture par équipe, remise à zéro à chaque vague (log_team_lines) et
# reprise dans l'alerte Telegram (failure_summary) : du 09 au 19/10/2026 le journal est resté vide
# sans que la cause apparaisse ailleurs que dans bot.log.
FAILURES: Dict[str, str] = {}
COLUMNS = ["date", "snapshot_utc", "team", "source_name", "source", "updated_at", "player", "dfo_id",
           "position", "category", "grp", "injury", "gtd"]


def team_slug(abbr: str) -> str:
    """Abréviation NHL -> slug de la page Daily Faceoff (« St. Louis Blues » -> « st-louis-blues »)."""
    return _SLUG_OVERRIDES.get(abbr) or "-".join(_norm(TEAM_ABBR_TO_FULL[abbr]).split())


def parse_combinations(next_data: Dict[str, Any]) -> Dict[str, Any]:
    """Lignes d'une équipe depuis le JSON `__NEXT_DATA__` de sa page.

    Returns:
        {'source_name', 'source', 'updated_at', 'players': [{player, dfo_id, position,
        category (ev/pp/pk/oi), grp (f1..f4, d1..d3, g, pp1, pp2, pk1, pk2, ir), injury, gtd}]}
    """
    c = next_data["props"]["pageProps"]["combinations"]
    players = [{"player": p.get("name"), "dfo_id": p.get("playerId"), "position": p.get("positionIdentifier"),
                "category": p.get("categoryIdentifier"), "grp": p.get("groupIdentifier"),
                "injury": p.get("injuryStatus"), "gtd": int(bool(p.get("gameTimeDecision")))}
               for p in c.get("players") or []]
    return {"source_name": c.get("sourceName"), "source": c.get("source"), "updated_at": c.get("updatedAt"),
            "players": players}


def _read_page(url: str, impersonate: str, timeout: float) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Une lecture de page : (lignes, None) ou (None, raison de l'échec en clair)."""
    from curl_cffi import requests as creq
    try:
        r = creq.get(url, impersonate=impersonate, timeout=timeout)
    except Exception as e:  # réseau : la raison remonte à l'appelant, la vague continue
        return None, f"page illisible ({type(e).__name__})"
    if r.status_code != 200:
        return None, f"HTTP {r.status_code}"
    m = _NEXT_DATA.search(r.text)
    if not m:
        return None, "page sans données (__NEXT_DATA__ absent)"
    try:
        return parse_combinations(json.loads(m.group(1))), None
    except (KeyError, TypeError, ValueError) as e:
        return None, f"format inattendu ({e})"


def fetch_team_lines(abbr: str, timeout: float = 20.0) -> Optional[Dict[str, Any]]:
    """Lit la page Daily Faceoff d'une équipe, avec chaque empreinte d'IMPERSONATE tant qu'elle est refusée.

    Returns:
        Les lignes, ou None : la raison est journalisée et gardée dans FAILURES[abbr].
    """
    url = URL.format(slug=team_slug(abbr))
    reasons: List[str] = []
    for imp in IMPERSONATE:
        data, reason = _read_page(url, imp, timeout)
        if data is not None:
            return data
        reasons.append(reason)
        if reason.startswith("format inattendu"):
            break  # la page est arrivée : une autre empreinte n'y changera rien
    FAILURES[abbr] = reasons[0] if len(set(reasons)) == 1 else " puis ".join(reasons)
    logger.warning(f"[DFO] {abbr} : {FAILURES[abbr]} ({url})")
    return None


def failure_summary() -> str:
    """Raisons des échecs de la dernière vague, regroupées : « HTTP 403 (12 équipes) »."""
    return " ; ".join(f"{r} ({n} équipe{'s' if n > 1 else ''})" for r, n in Counter(FAILURES.values()).most_common())


def _ensure_table(conn) -> None:
    conn.execute("""CREATE TABLE IF NOT EXISTS dfo_lines (
        id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT, snapshot_utc TEXT, team TEXT,
        source_name TEXT, source TEXT, updated_at TEXT, player TEXT, dfo_id INTEGER,
        position TEXT, category TEXT, grp TEXT, injury TEXT, gtd INTEGER)""")


def log_team_lines(teams: Iterable[str], session_date: str,
                   fetch: Callable[[str], Optional[Dict[str, Any]]] = fetch_team_lines,
                   pause_s: float = 0.5) -> int:
    """Journalise dans la table `dfo_lines` les lignes Daily Faceoff des équipes données.

    Args:
        teams: abréviations NHL des équipes de la vague.
        session_date: date de session NHL (YYYY-MM-DD).
        fetch: lecteur d'une équipe (remplaçable en test).
        pause_s: pause entre deux pages.

    Returns:
        Nombre de lignes écrites.
    """
    snap = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    rows: List[tuple] = []
    FAILURES.clear()
    for i, team in enumerate(sorted(set(teams))):
        if team not in TEAM_ABBR_TO_FULL:
            logger.warning(f"[DFO] équipe inconnue « {team} » ignorée")
            FAILURES[team] = "équipe inconnue"
            continue
        if i and pause_s:
            time.sleep(pause_s)
        data = fetch(team)
        if not data:
            FAILURES.setdefault(team, "illisible")
            continue
        rows += [(session_date, snap, team, data["source_name"], data["source"], data["updated_at"], p["player"],
                  p["dfo_id"], p["position"], p["category"], p["grp"], p["injury"], p["gtd"])
                 for p in data["players"]]
    if not rows:
        return 0
    conn = get_connection()
    try:
        _ensure_table(conn)
        conn.executemany(f"INSERT INTO dfo_lines ({', '.join(COLUMNS)}) VALUES ({', '.join('?' * len(COLUMNS))})",
                         rows)
        conn.commit()
    finally:
        conn.close()
    logger.info(f"[DFO] {len(rows)} lignes journalisées ({len(set(teams))} équipes)")
    return len(rows)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    for abbr in sys.argv[1:] or ["MTL"]:
        d = fetch_team_lines(abbr)
        if d is None:
            print(f"{abbr} : illisible")
            continue
        groups: Dict[str, List[str]] = {}
        for p in d["players"]:
            groups.setdefault(p["grp"], []).append(p["player"] + (f" ({p['injury']})" if p["injury"] else ""))
        print(f"{abbr} — {d['source_name']} — mis à jour {d['updated_at']}")
        for g, names in groups.items():
            print(f"  {g:4s} {', '.join(names)}")
