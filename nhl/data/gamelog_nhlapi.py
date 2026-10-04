"""
data/gamelog_nhlapi.py — Collecteur de logs de match depuis l'API NHL (automatisé).

Produit, pour une saison, un parquet au schéma unique `gamelog_schema.GAMELOG_COLUMNS`
(identique à l'historique MoneyPuck) :
  - boxscore      : TOI, tirs cadrés, position, équipe, domicile
  - play-by-play  : buts / A1 / A2 hors tirs au but, tirs ratés, tirs bloqués,
                    buts et tirs en 5c4 (même définition que la situation '5on4' MoneyPuck)
  - stats REST    : TOI en avantage numérique par match (skater/timeonice?isGame=true)

Incrémental : seuls les matchs terminés absents du parquet sont téléchargés.

Usage:
    python -m nhl.data.gamelog_nhlapi --season 2025            # saison 2025-26
    python -m nhl.data.gamelog_nhlapi --season 2024 --start 2024-12-01 --end 2024-12-31
"""
import argparse
import asyncio
import logging
import os
import sys
from collections import defaultdict
from datetime import date
from typing import Any, Dict, Iterable, List, Optional

import aiohttp
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from nhl.config.constants import TEAM_ABBR_TO_FULL  # noqa: E402
from nhl.data.gamelog_schema import enforce_schema  # noqa: E402

logger = logging.getLogger("NHL.GamelogAPI")

WEB = "https://api-web.nhle.com/v1"
STATS = "https://api.nhle.com/stats/rest/en"
GAMELOG_DIR = os.path.join(ROOT, "nhl", "data", "gamelogs")
CONCURRENCY = 12


def season_path(season: int) -> str:
    """Chemin du parquet API NHL d'une saison (année de début, ex. 2025 = 2025-26)."""
    return os.path.join(GAMELOG_DIR, f"nhlapi_{season}.parquet")


def current_season(today: Optional[date] = None) -> int:
    """Saison NHL en cours (année de début). Bascule au 1er août."""
    today = today or date.today()
    return today.year if today.month >= 8 else today.year - 1


async def _get(session: aiohttp.ClientSession, sem: asyncio.Semaphore, url: str,
               params: Optional[Dict[str, Any]] = None, retries: int = 5) -> Optional[Dict]:
    """GET JSON avec retry et gestion du rate limit."""
    async with sem:
        for i in range(retries):
            try:
                async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=30)) as r:
                    if r.status == 200:
                        return await r.json()
                    if r.status in (429, 500, 502, 503):
                        await asyncio.sleep(min(2 ** (i + 1), 30))
                        continue
                    logger.warning(f"HTTP {r.status} — {url}")
                    return None
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                logger.warning(f"Tentative {i + 1}/{retries} échouée ({e}) — {url}")
                await asyncio.sleep(2)
    logger.error(f"Abandon après {retries} tentatives — {url}")
    return None


async def list_finished_games(session, sem, season: int, start: Optional[str], end: Optional[str]) -> Dict[int, str]:
    """{gameId: date} des matchs de saison régulière terminés (calendrier de chaque club)."""
    sid = f"{season}{season + 1}"
    teams = sorted(set(TEAM_ABBR_TO_FULL))
    res = await asyncio.gather(*[_get(session, sem, f"{WEB}/club-schedule-season/{t}/{sid}") for t in teams])
    ids: Dict[int, str] = {}
    for data in res:
        for g in (data or {}).get("games", []):
            if g.get("gameType") != 2 or g.get("gameState") not in ("OFF", "FINAL"):
                continue
            if (start and g["gameDate"] < start) or (end and g["gameDate"] > end):
                continue
            ids[int(g["id"])] = g["gameDate"]
    return dict(sorted(ids.items()))


async def fetch_pp_toi(session, sem, games: Dict[int, str]) -> Dict[tuple, float]:
    """TOI en avantage numérique (secondes) par (playerId, gameId).

    L'endpoint plafonne `total` à 10 000 lignes par requête : on interroge donc
    par fenêtres de 7 jours (limit=-1), ce qui reste très en dessous du plafond.
    """
    if not games:
        return {}
    days = sorted(pd.to_datetime(list(games.values())).unique())
    windows, cur = [], days[0]
    while cur <= days[-1]:
        windows.append((cur, cur + pd.Timedelta(days=6)))
        cur += pd.Timedelta(days=7)
    reqs = [_get(session, sem, f"{STATS}/skater/timeonice", {
        "isGame": "true", "limit": -1,
        "cayenneExp": f'gameDate>="{a:%Y-%m-%d}" and gameDate<="{b:%Y-%m-%d}" and gameTypeId=2'})
        for a, b in windows]
    out: Dict[tuple, float] = {}
    for data in await asyncio.gather(*reqs):
        for r in (data or {}).get("data", []):
            if r["gameId"] in games:
                out[(r["playerId"], r["gameId"])] = float(r.get("ppTimeOnIce") or 0)
    return out


def _toi_min(s: str) -> float:
    try:
        m, sec = map(int, str(s).split(":"))
        return m + sec / 60.0
    except ValueError:
        return 0.0


def parse_game(box: Dict, pbp: Dict) -> List[Dict[str, Any]]:
    """Transforme boxscore + play-by-play d'un match en lignes du schéma unique."""
    gid = int(box["id"])
    home_id, away_id = box["homeTeam"]["id"], box["awayTeam"]["id"]
    abbr = {home_id: box["homeTeam"]["abbrev"], away_id: box["awayTeam"]["abbrev"]}
    names = {}
    for p in pbp.get("rosterSpots", []):
        names[p["playerId"]] = f"{p['firstName']['default']} {p['lastName']['default']}".strip()

    ev = defaultdict(lambda: defaultdict(int))
    for play in pbp.get("plays", []):
        t = play.get("typeDescKey")
        if t not in ("goal", "shot-on-goal", "missed-shot", "blocked-shot"):
            continue
        if play.get("periodDescriptor", {}).get("periodType") == "SO":
            continue  # tirs au but exclus (comme MoneyPuck)
        d = play.get("details", {})
        owner = d.get("eventOwnerTeamId")
        sc = str(play.get("situationCode", ""))
        # situationCode = [gardien ext][patineurs ext][patineurs dom][gardien dom]
        pp54 = False
        if len(sc) == 4 and sc[0] == "1" and sc[3] == "1":
            away_sk, home_sk = int(sc[1]), int(sc[2])
            own, opp = (home_sk, away_sk) if owner == home_id else (away_sk, home_sk)
            pp54 = (own, opp) == (5, 4)
        if t == "goal":
            shooter = d.get("scoringPlayerId")
            ev[shooter]["g"] += 1
            if pp54:
                ev[shooter]["pp_g"] += 1
                ev[shooter]["pp_sog"] += 1
            if d.get("assist1PlayerId"):
                ev[d["assist1PlayerId"]]["a1"] += 1
            if d.get("assist2PlayerId"):
                ev[d["assist2PlayerId"]]["a2"] += 1
        elif t == "shot-on-goal":
            if pp54:
                ev[d.get("shootingPlayerId")]["pp_sog"] += 1
        elif t == "missed-shot":
            ev[d.get("shootingPlayerId")]["missed"] += 1
        elif t == "blocked-shot":
            ev[d.get("shootingPlayerId")]["blocked_att"] += 1

    rows = []
    for side, team_id, opp_id in (("homeTeam", home_id, away_id), ("awayTeam", away_id, home_id)):
        stats = box["playerByGameStats"][side]
        for grp in ("forwards", "defense"):
            for p in stats.get(grp, []):
                pid = p["playerId"]
                toi = _toi_min(p.get("toi", "0:00"))
                if toi <= 0:
                    continue
                e = ev.get(pid, {})
                rows.append({
                    "playerId": pid, "name": names.get(pid, p["name"]["default"]),
                    "gameId": gid, "season": int(str(box["season"])[:4]), "game_type": int(box["gameType"]),
                    "gameDate": box["gameDate"], "team": abbr[team_id], "opp": abbr[opp_id],
                    "is_home": int(side == "homeTeam"), "position": p.get("position", ""),
                    "toi": toi, "pp_toi": 0.0,
                    "g": e.get("g", 0), "a1": e.get("a1", 0), "a2": e.get("a2", 0),
                    "sog": int(p.get("sog", 0)), "missed": e.get("missed", 0),
                    "blocked_att": e.get("blocked_att", 0),
                    "pp_g": e.get("pp_g", 0), "pp_sog": e.get("pp_sog", 0),
                })
    return rows


async def collect(season: int, start: Optional[str] = None, end: Optional[str] = None,
                  out_path: Optional[str] = None) -> pd.DataFrame:
    """Télécharge (incrémental) les logs de match d'une saison et les écrit en parquet.

    Args:
        season: année de début de saison (2025 = 2025-26).
        start, end: bornes de date optionnelles 'YYYY-MM-DD'.
        out_path: parquet de sortie (défaut : nhl/data/gamelogs/nhlapi_<season>.parquet).

    Returns:
        Le DataFrame complet de la saison (ancien + nouveaux matchs).
    """
    out_path = out_path or season_path(season)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    old = pd.read_parquet(out_path) if os.path.exists(out_path) else pd.DataFrame()
    done = set(old["gameId"].unique()) if not old.empty else set()

    sem = asyncio.Semaphore(CONCURRENCY)
    async with aiohttp.ClientSession(headers={"User-Agent": "Mozilla/5.0"}) as session:
        games = {g: d for g, d in (await list_finished_games(session, sem, season, start, end)).items()
                 if g not in done}
        ids = list(games)
        logger.info(f"[Gamelog API] saison {season} : {len(ids)} nouveau(x) match(s) à télécharger.")
        if not ids:
            return old
        boxes = await asyncio.gather(*[_get(session, sem, f"{WEB}/gamecenter/{g}/boxscore") for g in ids])
        pbps = await asyncio.gather(*[_get(session, sem, f"{WEB}/gamecenter/{g}/play-by-play") for g in ids])
        pp = await fetch_pp_toi(session, sem, games)

    rows = []
    for gid, box, pbp in zip(ids, boxes, pbps):
        if not box or not pbp:
            logger.warning(f"[Gamelog API] match {gid} incomplet — sera retenté au prochain passage.")
            continue
        for r in parse_game(box, pbp):
            r["pp_toi"] = pp.get((r["playerId"], gid), 0.0) / 60.0
            rows.append(r)
    new = enforce_schema(pd.DataFrame(rows)) if rows else pd.DataFrame()
    full = pd.concat([old, new], ignore_index=True) if not old.empty else new
    full = full.drop_duplicates(["playerId", "gameId"], keep="last")
    full.to_parquet(out_path, index=False)
    logger.info(f"[Gamelog API] {len(new):,} lignes ajoutées -> {out_path} ({len(full):,} au total)")
    return full


def update_current_season() -> pd.DataFrame:
    """Point d'entrée synchrone pour le bot (job quotidien)."""
    return asyncio.run(collect(current_season()))


def ensure_recent_seasons() -> None:
    """Saison en cours (incrémental) + saison précédente si absente.

    L'historique MoneyPuck s'arrête en 2024-25 : la saison précédente doit venir
    de l'API pour que les fenêtres glissantes et l'entraînement soient complets.
    Toute erreur réseau est loggée sans interrompre le bot (les logs existants restent utilisables).
    """
    cur = current_season()
    for season in (cur - 1, cur):
        if season <= 2024:
            continue  # couvert par mp_gamelogs.parquet
        if season == cur or not os.path.exists(season_path(season)):
            try:
                asyncio.run(collect(season))
            except Exception as e:  # le bot doit continuer avec les logs déjà présents
                logger.error(f"[Gamelog API] collecte saison {season} impossible : {e}", exc_info=True)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int, default=current_season())
    ap.add_argument("--start")
    ap.add_argument("--end")
    ap.add_argument("--out")
    a = ap.parse_args()
    asyncio.run(collect(a.season, a.start, a.end, a.out))


if __name__ == "__main__":
    main()
