import logging
import os
import sys
from typing import Any, Dict, Optional, Tuple

# Ajout du dossier racine au sys.path pour permettre l'exécution standalone
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from nhl.core.database import get_connection
from nhl.core.services import safe_get
from shared.portfolio import Portfolio
from shared.utils import match_player_name  # Source unique

logger = logging.getLogger("NHL.Updater")
portfolio = Portfolio()

FINAL_STATES = ("OFF", "FINAL", "FINAL_OT", "FINAL_SO")
# (table, colonne résultat, stat du boxscore, marché du portefeuille)
PICK_TABLES = (("picks", "but", "goals", "BUTEUR"),
               ("picks_assists", "assist", "assists", "PASSEUR"),
               ("picks_points", "point", "points", "POINTEUR"))


def fetch_final_boxscores(date_str: str) -> Dict[str, Dict[str, Any]]:
    """Stats des joueurs des matchs TERMINÉS d'une date, par équipe.

    Returns:
        {abréviation: {"by_id": {playerId: stats}, "by_name": {nom: stats}}} ; une équipe
        n'apparaît que si son match est terminé et que son boxscore a été lu.
    """
    sched = safe_get(f"https://api-web.nhle.com/v1/schedule/{date_str}", timeout=10).json()
    games = next((gw.get("games", []) for gw in sched.get("gameWeek", []) if gw["date"] == date_str), [])
    out: Dict[str, Dict[str, Any]] = {}
    for g in games:
        if g.get("gameState") not in FINAL_STATES:
            continue
        try:
            box = safe_get(f"https://api-web.nhle.com/v1/gamecenter/{g['id']}/boxscore", timeout=10).json()
        except Exception as e:  # boxscore indisponible : l'équipe reste en attente, retentée demain
            logger.warning(f"[Auto-ROI] Boxscore {g['id']} illisible ({e}) — résolution reportée.")
            continue
        for side in ("homeTeam", "awayTeam"):
            team = g[side]["abbrev"]
            pdata = box.get("playerByGameStats", {}).get(side, {})
            entry = out.setdefault(team, {"by_id": {}, "by_name": {}})
            for p in pdata.get("forwards", []) + pdata.get("defense", []):
                stats = {k: p.get(k, 0) for k in ("goals", "assists", "points", "shots")}
                entry["by_id"][int(p.get("playerId", 0))] = stats
                entry["by_name"][p.get("name", {}).get("default", "")] = stats
    return out


def find_player_stats(team_box: Dict[str, Any], joueur: str, player_id: Optional[int]) -> Tuple[Optional[Dict], bool]:
    """Stats d'un joueur dans le boxscore de son équipe.

    Returns:
        (stats ou None, sûr) : `sûr` = True si l'absence est certaine (recherche par playerId).
        Sans playerId, un nom non trouvé peut venir d'une graphie différente.
    """
    if player_id:
        return team_box["by_id"].get(int(player_id)), True
    for api_name, stats in team_box["by_name"].items():
        if match_player_name(joueur, api_name):
            return stats, True
    return None, False


def update_pending_picks() -> int:
    """Résout les picks en attente via les boxscores de l'API NHL.

    - Joueur présent au boxscore : 1 si la stat du marché est > 0, sinon 0.
    - Match terminé et joueur absent (scratch, blessure à l'échauffement) : pick `void`
      (mise rendue au portefeuille, exclu du ROI). Sans playerId, le pick n'est annulé que
      si aucun nom ne correspond, et un warning est loggé.

    Returns:
        Nombre de picks résolus (void compris).
    """
    conn = get_connection()
    try:
        dates = set()
        for table, col, _, _ in PICK_TABLES:
            rows = conn.execute(f"SELECT DISTINCT date FROM {table} WHERE ({col} IS NULL OR {col} = '') "
                                f"AND (statut IS NULL OR statut != 'void')").fetchall()
            dates.update(r[0] for r in rows)
    finally:
        conn.close()
    if not dates:
        logger.info("[Auto-ROI] Aucune donnée en attente de résolution.")
        return 0

    logger.info(f"[Auto-ROI] Validation des résultats pour {len(dates)} date(s)...")
    # Téléchargement des boxscores SANS connexion ouverte : avant (2026-10-04), la transaction
    # d'écriture restait ouverte pendant les appels réseau et bloquait les autres jobs.
    boxes = {}
    for date_str in sorted(dates):
        try:
            box = fetch_final_boxscores(date_str)
        except Exception as e:
            logger.error(f"[Auto-ROI] Erreur lors du fetch de la date {date_str} : {e}")
            continue
        if not box:
            logger.info(f"[Auto-ROI] Les matchs du {date_str} ne sont pas encore terminés ou indisponibles.")
            continue
        boxes[date_str] = box

    resolved = 0
    for date_str, box in boxes.items():
        resolved += _resolve_date(date_str, box)
    if resolved:
        logger.info(f"[Auto-ROI] [OK] {resolved} pick(s) résolu(s) via API NHL.")
    return resolved


def _resolve_date(date_str: str, box: dict) -> int:
    """Écrit les résultats d'une date dans une transaction courte. Renvoie le nombre de picks résolus."""
    conn = get_connection()
    c = conn.cursor()
    resolved = 0
    try:
        for table, col, stat, market in PICK_TABLES:
            c.execute(f"SELECT id, joueur, equipe, player_id FROM {table} WHERE date = ? "
                      f"AND ({col} IS NULL OR {col} = '') AND (statut IS NULL OR statut != 'void')", (date_str,))
            for pick_id, joueur, equipe, player_id in c.fetchall():
                if equipe not in box:
                    continue
                stats, sure = find_player_stats(box[equipe], joueur, player_id)
                if stats is None:
                    if not sure:
                        logger.warning(f"[Auto-ROI] {joueur} ({equipe}) introuvable par nom dans le boxscore "
                                       f"du {date_str} : pick {table}#{pick_id} annulé (void).")
                    c.execute(f"UPDATE {table} SET statut = 'void' WHERE id = ?", (pick_id,))
                    portfolio.resolve_bet_by_pick_id(pick_id, "nhl", won=False, market=market, void=True)
                else:
                    val = 1 if stats[stat] > 0 else 0
                    c.execute(f"UPDATE {table} SET {col} = ? WHERE id = ?", (val, pick_id))
                    portfolio.resolve_bet_by_pick_id(pick_id, "nhl", won=(val == 1), market=market)
                resolved += 1

        # Table unifiée des joueurs évalués (stats brutes, pas de void)
        c.execute("SELECT id, joueur, equipe FROM players WHERE date = ? AND (but IS NULL OR but = '')", (date_str,))
        for p_id, joueur, equipe in c.fetchall():
            if equipe in box:
                stats, _ = find_player_stats(box[equipe], joueur, None)
                if stats is not None:
                    c.execute("UPDATE players SET but = ?, assist = ?, point = ? WHERE id = ?",
                              (stats["goals"], stats["assists"], stats["points"], p_id))
        conn.commit()
    finally:
        conn.close()
    return resolved


async def log_closing_lines_for_match(home: str, away: str, session_date: str) -> int:
    """Snapshot de clôture (≈ T-5 min) pour les picks non résolus d'UN match.

    Enregistre la cote d'exécution (Winamax) et la probabilité no-vig Pinnacle de
    clôture : CLV = cote_prise / closing_cote - 1 et EV de clôture =
    closing_p_novig * cote_prise - 1 (meilleur indicateur d'edge sur petit échantillon).

    Args:
        home: abréviation de l'équipe à domicile.
        away: abréviation de l'équipe à l'extérieur.
        session_date: date de session NHL des picks (YYYY-MM-DD).

    Returns:
        Nombre de picks mis à jour.
    """
    from nhl.core.database import get_connection
    from nhl.core.odds import fetch_nhl_odds

    conn = get_connection()
    c = conn.cursor()
    players: dict = {}
    for table, col in (("picks", "but"), ("picks_assists", "assist")):
        c.execute(f"SELECT joueur, equipe FROM {table} WHERE date = ? AND equipe IN (?, ?) "
                  f"AND ({col} IS NULL OR {col} = '')", (session_date, home, away))
        players.update({j: e for j, e in c.fetchall()})
    if not players:
        conn.close()
        return 0
    odds = await fetch_nhl_odds(players, games=[(home, away)], log_moment="cloture", session_date=session_date)
    updates = 0
    for player, data in odds.items():
        for key, table, col in (("BUTS", "picks", "but"), ("ASSISTS", "picks_assists", "assist")):
            d = data.get(key) or {}
            if not d.get("price") and not d.get("p_novig"):
                continue
            c.execute(f"UPDATE {table} SET closing_cote = ?, closing_p_novig = ? WHERE joueur = ? AND date = ? "
                      f"AND ({col} IS NULL OR {col} = '')", (d.get("price"), d.get("p_novig"), player, session_date))
            updates += c.rowcount
    conn.commit()
    conn.close()
    logger.info(f"[CLV] {home}-{away} : {updates} pick(s) avec cote de clôture.")
    return updates
