"""
data/xg_nhlapi.py — xG match par match des saisons récentes (≥ 2025-26), reconstruit en saison.

MoneyPuck ne sert plus ses logs match par match en accès direct (HTTP 403). On reconstruit les
colonnes de `nhl/data/gamelogs/mp_xg.parquet` (`gamelog_schema.XG_COLUMNS`) à partir de :
- ses tirs et leur xG : miroir public github.com/mattkravec/moneypuck-data (release `data-v2`,
  `shots_<saison>.parquet`, rafraîchi chaque jour vers 17h20 UTC). Données MoneyPuck
  (moneypuck.com), usage non commercial, à citer ;
- les présences sur la glace (shift charts) et les mises en jeu (play-by-play) de l'API NHL.

Parité contre les logs MoneyPuck sur 300 matchs de 2024-25 (`--parity 2024`) : corrélation de
0,976 à 0,9996 selon la colonne (étude du 2026-10-08).

Incrémental : le fichier de tirs n'est retéléchargé que si le miroir l'a mis à jour, et seuls
les matchs terminés (présents dans les logs de match) absents de `xg_<saison>.parquet` sont
reconstruits.

Usage:
    python -m nhl.data.xg_nhlapi --season 2025              # rattrapage d'une saison
    python -m nhl.data.xg_nhlapi --status                   # couverture par saison
    python -m nhl.data.xg_nhlapi --parity 2024 --sample 300 # contrôle contre MoneyPuck
"""
import argparse
import asyncio
import json
import logging
import os
import sys
from typing import Any, Dict, Iterable, List, Optional

import aiohttp
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from nhl.data.gamelog_nhlapi import CONCURRENCY, GAMELOG_DIR, _get, current_season  # noqa: E402
from nhl.data.gamelog_schema import XG_COLUMNS, clean_team  # noqa: E402

logger = logging.getLogger("NHL.XgAPI")

MIRROR_API = "https://api.github.com/repos/mattkravec/moneypuck-data/releases/tags/data-v2"
SHIFTS = "https://api.nhle.com/stats/rest/en/shiftcharts"
PBP = "https://api-web.nhle.com/v1/gamecenter/{}/play-by-play"
FIRST_SEASON = 2025          # avant : mp_xg.parquet (logs MoneyPuck 2008-2024)
SHOT_COLUMNS = ["game_id", "isPlayoffGame", "period", "time", "teamCode", "isHomeTeam", "shooterPlayerId",
                "xGoal", "homeSkatersOnIce", "awaySkatersOnIce", "homeEmptyNet", "awayEmptyNet"]
HIGH_DANGER_XG = 0.2         # haut danger MoneyPuck : xGoal ≥ 0,2 (vérifié par la parité)


def xg_path(season: int) -> str:
    """Parquet xG reconstruit d'une saison (hors git)."""
    return os.path.join(GAMELOG_DIR, f"xg_{season}.parquet")


def shots_path(season: int) -> str:
    """Copie locale des tirs MoneyPuck d'une saison (hors git)."""
    return os.path.join(GAMELOG_DIR, f"mp_shots_{season}.parquet")


# ─────────────────────────────────────────────────────────────────────────────
# Tirs MoneyPuck (miroir)
# ─────────────────────────────────────────────────────────────────────────────
def download_shots(season: int, timeout: float = 60.0) -> bool:
    """Retélécharge `shots_<saison>.parquet` si le miroir l'a mis à jour depuis la copie locale.

    Returns:
        True si une copie locale utilisable existe à la fin (nouvelle ou ancienne).
    """
    import requests
    path, meta_path = shots_path(season), shots_path(season) + ".json"
    have = os.path.exists(path)
    try:
        rel = requests.get(MIRROR_API, timeout=timeout)
        rel.raise_for_status()
        asset = next((a for a in rel.json().get("assets", []) if a.get("name") == f"shots_{season}.parquet"), None)
        if asset is None:
            logger.warning(f"[xG] shots_{season}.parquet absent du miroir.")
            return have
        meta = json.load(open(meta_path, encoding="utf-8")) if os.path.exists(meta_path) and have else {}
        if meta.get("updated_at") == asset["updated_at"]:
            return True
        r = requests.get(asset["browser_download_url"], timeout=timeout)
        r.raise_for_status()
        tmp = path + ".tmp"
        with open(tmp, "wb") as f:
            f.write(r.content)
        missing = [c for c in SHOT_COLUMNS if c not in pd.read_parquet(tmp).columns]
        if missing:
            os.remove(tmp)
            logger.error(f"[xG] shots_{season} : colonnes manquantes {missing} — copie locale conservée.")
            return have
        os.replace(tmp, path)
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump({"updated_at": asset["updated_at"]}, f)
        logger.info(f"[xG] shots_{season}.parquet mis à jour ({len(r.content) / 1e6:.1f} Mo, {asset['updated_at']}).")
        return True
    except Exception as e:  # miroir indisponible : on garde la copie locale
        logger.warning(f"[xG] miroir MoneyPuck injoignable ({e}) — copie locale {'conservée' if have else 'absente'}.")
        return have


def load_shots(season: int) -> pd.DataFrame:
    """Tirs de saison régulière (prolongation comprise, tirs de fusillade exclus), avec le gameId NHL."""
    s = pd.read_parquet(shots_path(season), columns=SHOT_COLUMNS)
    s = s[(s["isPlayoffGame"] == 0) & (s["game_id"] < 30000) & (s["period"] <= 4)].copy()
    s["gameId"] = season * 1_000_000 + s["game_id"].astype("int64")
    return s


# ─────────────────────────────────────────────────────────────────────────────
# Reconstruction d'un match
# ─────────────────────────────────────────────────────────────────────────────
def _mmss(s: Any) -> int:
    try:
        m, sec = str(s).split(":")
        return int(m) * 60 + int(sec)
    except (ValueError, AttributeError):
        return -1


def game_rows(gid: int, shots: pd.DataFrame, shifts: Optional[Dict], pbp: Optional[Dict]) -> List[Dict[str, Any]]:
    """Une ligne par joueur du match, aux colonnes `XG_COLUMNS` (mêmes définitions que MoneyPuck).

    - xG individuel (toutes situations, haut danger, 5 contre 4 sans filet vide) ;
    - xG pour / contre sur la glace : joueur en présence si début < t ≤ fin (toutes situations,
      et 5 contre 5 sans filet vide) ;
    - départs de présence en zone offensive / défensive : mise en jeu à la seconde du début ;
    - temps de glace en secondes.

    Returns:
        [] si les présences ou le play-by-play manquent (match retenté au prochain passage).
    """
    if not shifts or not pbp:
        return []
    sh = pd.DataFrame([x for x in shifts.get("data", []) if x.get("typeCode") == 517])
    if sh.empty:
        return []
    sh["start"], sh["end"] = sh["startTime"].map(_mmss), sh["endTime"].map(_mmss)
    sh["team"] = sh["teamAbbrev"].map(clean_team)
    sh = sh[(sh.start >= 0) & (sh.end > sh.start)]
    abbr = {pbp["homeTeam"]["id"]: clean_team(pbp["homeTeam"]["abbrev"]),
            pbp["awayTeam"]["id"]: clean_team(pbp["awayTeam"]["abbrev"])}
    # Mises en jeu : (période, seconde) -> zone du point de vue de chaque équipe
    faceoffs: Dict[tuple, Dict[str, str]] = {}
    for p in pbp.get("plays", []):
        if p.get("typeDescKey") != "faceoff":
            continue
        d = p.get("details", {})
        owner, zone = abbr.get(d.get("eventOwnerTeamId")), d.get("zoneCode")
        if owner and zone in ("O", "D", "N"):
            other = [t for t in abbr.values() if t != owner][0]
            faceoffs[(p["periodDescriptor"]["number"], _mmss(p.get("timeInPeriod")))] = {
                owner: zone, other: {"O": "D", "D": "O", "N": "N"}[zone]}
    g = shots.copy()
    g["t"] = g["time"] - 1200 * (g["period"] - 1)
    g["shoot_team"] = g["teamCode"].map(clean_team)
    own = np.where(g.isHomeTeam == 1, g.homeSkatersOnIce, g.awaySkatersOnIce)
    opp = np.where(g.isHomeTeam == 1, g.awaySkatersOnIce, g.homeSkatersOnIce)
    empty = (g.homeEmptyNet == 1) | (g.awayEmptyNet == 1)
    g["pp54"] = (own == 5) & (opp == 4) & ~empty
    g["ev55"] = (own == 5) & (opp == 5) & ~empty

    rows: Dict[int, Dict[str, Any]] = {
        int(pid): {"playerId": int(pid), "gameId": int(gid), **{c: 0.0 for c in XG_COLUMNS}}
        for pid in sh["playerId"].unique()}
    for r in sh.itertuples(index=False):
        rec = rows[int(r.playerId)]
        rec["icetime"] += r.end - r.start
        zone = faceoffs.get((r.period, r.start), {}).get(r.team)
        if zone == "O":
            rec["I_F_oZoneShiftStarts"] += 1
        elif zone == "D":
            rec["I_F_dZoneShiftStarts"] += 1
    by_period = {p: d for p, d in sh.groupby("period")}
    for s in g.itertuples(index=False):
        sid = s.shooterPlayerId
        if sid == sid and int(sid) in rows:
            rec = rows[int(sid)]
            rec["I_F_xGoals"] += s.xGoal
            if s.xGoal >= HIGH_DANGER_XG:
                rec["I_F_highDangerShots"] += 1
                rec["I_F_highDangerxGoals"] += s.xGoal
            if s.pp54:
                rec["pp_ixg"] += s.xGoal
        on = by_period.get(s.period)
        if on is None:
            continue
        for r in on[(on.start < s.t) & (on.end >= s.t)].itertuples(index=False):
            rec = rows[int(r.playerId)]
            if r.team == s.shoot_team:
                rec["OnIce_F_xGoals"] += s.xGoal
                if s.ev55:
                    rec["ev_onice_xgf"] += s.xGoal
            else:
                rec["OnIce_A_xGoals"] += s.xGoal
                if s.ev55:
                    rec["ev_onice_xga"] += s.xGoal
    return list(rows.values())


async def _fetch(gids: Iterable[int]) -> tuple:
    sem = asyncio.Semaphore(CONCURRENCY)
    async with aiohttp.ClientSession(headers={"User-Agent": "Mozilla/5.0"}) as session:
        gids = list(gids)
        shifts = await asyncio.gather(*[_get(session, sem, SHIFTS, {"cayenneExp": f"gameId={g}"}) for g in gids])
        pbps = await asyncio.gather(*[_get(session, sem, PBP.format(g)) for g in gids])
    return shifts, pbps


def rebuild(gids: List[int], shots: pd.DataFrame) -> pd.DataFrame:
    """Reconstruit les matchs donnés (présences et play-by-play téléchargés)."""
    if not gids:
        return pd.DataFrame(columns=["playerId", "gameId"] + XG_COLUMNS)
    shifts, pbps = asyncio.run(_fetch(gids))
    by_game = {g: d for g, d in shots[shots.gameId.isin(gids)].groupby("gameId")}
    rows: List[Dict[str, Any]] = []
    for gid, s, p in zip(gids, shifts, pbps):
        got = game_rows(gid, by_game.get(gid, shots.iloc[:0]), s, p)
        if not got:
            logger.warning(f"[xG] match {gid} : présences ou play-by-play indisponibles — retenté plus tard.")
        rows += got
    out = pd.DataFrame(rows, columns=["playerId", "gameId"] + XG_COLUMNS)
    return out.astype({"playerId": "int64", "gameId": "int64", **{c: "float32" for c in XG_COLUMNS}})


def collect(season: int, finished: Optional[Iterable[int]] = None, max_games: Optional[int] = None) -> pd.DataFrame:
    """Ajoute à `xg_<saison>.parquet` les matchs terminés pas encore reconstruits.

    Args:
        season: année de début de saison (2025 = 2025-26).
        finished: gameId des matchs terminés (défaut : ceux des logs de match API NHL de la saison).
        max_games: plafond de matchs reconstruits par appel (None = tous).

    Returns:
        La table xG complète de la saison.
    """
    path = xg_path(season)
    old = pd.read_parquet(path) if os.path.exists(path) else pd.DataFrame(columns=["playerId", "gameId"] + XG_COLUMNS)
    if not os.path.exists(shots_path(season)):
        logger.warning(f"[xG] pas de fichier de tirs pour {season} : rien à reconstruire.")
        return old
    shots = load_shots(season)
    if finished is None:
        from nhl.data.gamelog_nhlapi import season_path
        logs = season_path(season)
        finished = set(pd.read_parquet(logs, columns=["gameId"])["gameId"]) if os.path.exists(logs) else set()
    todo = sorted(set(shots["gameId"]) & set(finished) - set(old["gameId"]))
    if max_games is not None:
        todo = todo[:max_games]
    if not todo:
        return old
    logger.info(f"[xG] saison {season} : {len(todo)} match(s) à reconstruire.")
    new = rebuild(todo, shots)
    full = new if old.empty else pd.concat([old, new], ignore_index=True)
    full = full.drop_duplicates(["playerId", "gameId"], keep="last")
    full.to_parquet(path, index=False)
    logger.info(f"[xG] {new['gameId'].nunique()} match(s) ajouté(s) -> {path} ({full['gameId'].nunique()} au total)")
    return full


def ensure_xg_recent(backfill: bool = False) -> None:
    """Saison en cours et précédente (≥ 2025) : tirs du miroir à jour puis matchs manquants.

    Args:
        backfill: False (avant chaque vague) : seulement les saisons déjà amorcées, quelques
            matchs ; True (fin de journée) : rattrapage complet, y compris une saison absente.

    Toute erreur est journalisée sans interrompre le bot.
    """
    cur = current_season()
    for season in (cur - 1, cur):
        if season < FIRST_SEASON:
            continue
        if not backfill and not os.path.exists(xg_path(season)):
            logger.warning(f"[xG] {xg_path(season)} absent : rattrapage au job de fin de journée "
                           f"(ou python -m nhl.data.xg_nhlapi --season {season}).")
            continue
        try:
            if download_shots(season):
                collect(season)
        except Exception as e:
            logger.error(f"[xG] mise à jour de la saison {season} impossible : {e}", exc_info=True)


# ─────────────────────────────────────────────────────────────────────────────
# Contrôles
# ─────────────────────────────────────────────────────────────────────────────
def status() -> pd.DataFrame:
    """Couverture : matchs des logs de match vs matchs reconstruits, par saison ≥ 2025."""
    from nhl.data.gamelog_nhlapi import season_path
    rows = []
    for season in range(FIRST_SEASON, current_season() + 1):
        logs = season_path(season)
        g = pd.read_parquet(logs, columns=["gameId", "gameDate"]) if os.path.exists(logs) else pd.DataFrame(columns=["gameId", "gameDate"])
        x = pd.read_parquet(xg_path(season), columns=["gameId"]) if os.path.exists(xg_path(season)) else pd.DataFrame(columns=["gameId"])
        done = set(x["gameId"])
        missing = g[~g["gameId"].isin(done)]
        rows.append({"saison": season, "matchs_logs": g["gameId"].nunique(), "matchs_xg": len(done),
                     "manquants": missing["gameId"].nunique(),
                     "dernier_log": str(pd.to_datetime(g["gameDate"]).max().date()) if len(g) else None,
                     "premier_manquant": str(pd.to_datetime(missing["gameDate"]).min().date()) if len(missing) else None})
    return pd.DataFrame(rows)


def parity(season: int, sample: int, reference: str) -> pd.DataFrame:
    """Corrélation colonne par colonne entre la reconstruction et les logs MoneyPuck d'une saison."""
    shots = load_shots(season)
    gids = sorted(shots["gameId"].unique())
    gids = sorted(np.random.default_rng(0).choice(gids, size=min(sample, len(gids)), replace=False).tolist())
    rb = rebuild(gids, shots)
    mp = pd.read_parquet(reference)
    x = rb.merge(mp, on=["playerId", "gameId"], suffixes=("_r", "_mp"))
    out = []
    for c in XG_COLUMNS:
        a, b = x[f"{c}_r"].astype(float), x[f"{c}_mp"].astype(float).fillna(0)
        out.append({"colonne": c, "corr": float(np.corrcoef(a, b)[0, 1]), "moy_reconstruite": float(a.mean()),
                    "moy_moneypuck": float(b.mean()), "lignes": len(x)})
    return pd.DataFrame(out)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="xG match par match des saisons récentes (tirs MoneyPuck + API NHL)")
    ap.add_argument("--season", type=int, help="saison à rattraper (année de début)")
    ap.add_argument("--max", type=int, default=None, help="plafond de matchs reconstruits")
    ap.add_argument("--status", action="store_true", help="couverture par saison")
    ap.add_argument("--parity", type=int, help="saison de contrôle contre les logs MoneyPuck (ex. 2024)")
    ap.add_argument("--sample", type=int, default=300)
    a = ap.parse_args()
    if a.parity is not None:
        if download_shots(a.parity):
            print(parity(a.parity, a.sample, os.path.join(GAMELOG_DIR, "mp_xg.parquet")).round(4).to_string(index=False))
        return
    if a.season is not None:
        if download_shots(a.season):
            collect(a.season, max_games=a.max)
    print(status().to_string(index=False))


if __name__ == "__main__":
    main()
