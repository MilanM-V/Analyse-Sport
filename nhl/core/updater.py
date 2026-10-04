import requests
import logging
import os
import sys
from datetime import datetime

# Ajout du dossier racine au sys.path pour permettre l'exécution standalone
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from  core.database import get_connection
from nhl.core.services import safe_get
from shared.portfolio import Portfolio
from shared.utils import normalize_name, match_player_name  # Source unique

logger = logging.getLogger("NHL.Updater")
portfolio = Portfolio()

# Import centralisé depuis la source unique
from nhl.config.constants import ALL_ABBRS

def update_pending_picks():
    """
    Scan la DB pour trouver les dates non-résolues (but IS NULL)
    et interroge l'API NHL pour valider si but=1 ou but=0.
    """
    conn = get_connection()
    c = conn.cursor()

    c.execute("""
        SELECT DISTINCT date FROM picks WHERE but IS NULL OR but = ''
        UNION
        SELECT DISTINCT date FROM picks_assists WHERE assist IS NULL OR assist = ''
        UNION
        SELECT DISTINCT date FROM picks_points WHERE point IS NULL OR point = ''
    """)
    dates_to_check = [r[0] for r in c.fetchall()]

    if not dates_to_check:
        logger.info("[Auto-ROI] Aucune donnée en attente de résolution.")
        conn.close()
        return 0

    logger.info(f"[Auto-ROI] Validation des résultats pour {len(dates_to_check)} date(s)...")

    resolved_count = 0

    for date_str in dates_to_check:
        try:
            sched_resp = safe_get(f"https://api-web.nhle.com/v1/schedule/{date_str}", timeout=10)
            sched = sched_resp.json()
            games = []
            for gw in sched.get("gameWeek", []):
                if gw["date"] == date_str:
                    games = gw.get("games", [])
                    break

            goals_map = {}
            for g in games:
                if g.get("gameState") not in ('OFF', 'FINAL', 'FINAL_OT', 'FINAL_SO'):
                    continue

                gid = g["id"]
                try:
                    box_resp = safe_get(f"https://api-web.nhle.com/v1/gamecenter/{gid}/boxscore", timeout=10)
                    box = box_resp.json()
                except:
                    continue

                for side in ["homeTeam", "awayTeam"]:
                    team_abbrev = g[side]["abbrev"]
                    players_data = box.get('playerByGameStats', {}).get(side, {})
                    all_players = players_data.get('forwards', []) + players_data.get('defense', [])

                    if team_abbrev not in goals_map:
                        goals_map[team_abbrev] = {}

                    for p in all_players:
                        name = p.get('name', {}).get('default', '')
                        goals_map[team_abbrev][name] = {
                            'goals': p.get('goals', 0),
                            'assists': p.get('assists', 0),
                            'points': p.get('points', 0),
                            'shots': p.get('shots', 0)
                        }

            if not goals_map:
                logger.info(f"[Auto-ROI] Les matchs du {date_str} ne sont pas encore terminés ou indisponibles.")
                continue

            # 1. Update table 'picks' (BUTS)
            c.execute("SELECT id, joueur, equipe, verdict FROM picks WHERE date = ? AND (but IS NULL OR but = '')", (date_str,))
            for pick_id, joueur, equipe, verdict in c.fetchall():
                if equipe in goals_map:
                    for api_name, stats in goals_map[equipe].items():
                        if match_player_name(joueur, api_name):
                            val = 1 if stats['goals'] > 0 else 0
                            c.execute("UPDATE picks SET but = ? WHERE id = ?", (val, pick_id))
                            portfolio.resolve_bet_by_pick_id(pick_id, "nhl", won=(val == 1))
                            resolved_count += 1
                            break

            # 2. Update table 'picks_assists'
            c.execute("SELECT id, joueur, equipe FROM picks_assists WHERE date = ? AND (assist IS NULL OR assist = '')", (date_str,))
            for pick_id, joueur, equipe in c.fetchall():
                if equipe in goals_map:
                    for api_name, stats in goals_map[equipe].items():
                        if match_player_name(joueur, api_name):
                            val = 1 if stats['assists'] > 0 else 0
                            c.execute("UPDATE picks_assists SET assist = ? WHERE id = ?", (val, pick_id))
                            portfolio.resolve_bet_by_pick_id(pick_id, "nhl", won=(val == 1))
                            resolved_count += 1
                            break

            # 3. Update table 'picks_points'
            c.execute("SELECT id, joueur, equipe FROM picks_points WHERE date = ? AND (point IS NULL OR point = '')", (date_str,))
            for pick_id, joueur, equipe in c.fetchall():
                if equipe in goals_map:
                    for api_name, stats in goals_map[equipe].items():
                        if match_player_name(joueur, api_name):
                            val = 1 if stats['points'] > 0 else 0
                            c.execute("UPDATE picks_points SET point = ? WHERE id = ?", (val, pick_id))
                            portfolio.resolve_bet_by_pick_id(pick_id, "nhl", won=(val == 1))
                            resolved_count += 1
                            break

            # 4. Update unified 'players' table
            c.execute("SELECT id, joueur, equipe FROM players WHERE date = ? AND (but IS NULL OR but = '')", (date_str,))
            for p_id, joueur, equipe in c.fetchall():
                if equipe in goals_map:
                    for api_name, stats in goals_map[equipe].items():
                        if match_player_name(joueur, api_name):
                            c.execute("UPDATE players SET but = ?, assist = ?, point = ? WHERE id = ?", 
                                      (stats['goals'], stats['assists'], stats['points'], p_id))
                            break

        except Exception as e:
            logger.error(f"[Auto-ROI] Erreur lors du fetch de la date {date_str} : {e}")

    conn.commit()
    conn.close()

    if resolved_count > 0:
        logger.info(f"[Auto-ROI] [OK] {resolved_count} pick(s) résolu(s) avec succès via API NHL !")
    return resolved_count

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
    from shared.odds_api import fetch_nhl_odds

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
    odds = await fetch_nhl_odds(players)
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
