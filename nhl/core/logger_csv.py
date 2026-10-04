"""
core/logger_csv.py — Logging des picks et joueurs en SQL et CSV.

Extrait de bot_logic.py pour séparation des responsabilités.
"""
import os
import csv
import json
import logging
from typing import Dict, List, Any

from nhl.core.database import get_pick_id, insert_pick, insert_player, pick_ref
from nhl.config.settings import cfg
from shared.portfolio import Portfolio

logger = logging.getLogger("NHL.LoggerCSV")
portfolio = Portfolio()


# Audit P3 (2026-10-04) : les colonnes héritées is_top6, linemate_synergy, team_scoring_env,
# prior_* et opp_xga_60 ne sont plus écrites (features de l'ancien modèle, valeurs 0 trompeuses).
# Le vecteur réellement servi au modèle est dans features_json.
def _trace(p: Dict[str, Any]) -> Dict[str, Any]:
    """Colonnes de traçabilité du pari (audit P3) : probas, EV, version et vecteur exact du modèle."""
    return {
        "p_model": p.get("PModel"), "p_novig": p.get("PNovig"), "p_final": p.get("Proba"),
        "ev": p.get("EV"), "bookmaker": p.get("Bookmaker"), "model_version": p.get("ModelVersion"),
        "features_json": json.dumps(p.get("Features") or {}, separators=(",", ":")),
        # Cote estimée (médiane US décotée) ; si une vraie cote FR l'a remplacée, l'estimation d'origine
        "cote_proxy": p.get("CoteProxy") if p.get("PriceSource") == "fr" else (p.get("Cote") if p.get("PriceSource") else None),
        "cote_seuil": p.get("CoteSeuil"), "price_source": p.get("PriceSource"),
        "player_id": p.get("PlayerId"),  # résolution fiable (void si absent du boxscore)
        "phase": p.get("Phase", "normal"),  # 'early' = mode découverte (moins de 10 matchs)
    }


def _after_insert(table: str, p: Dict[str, Any], pick_id: Any, today: str) -> None:
    """Référence Telegram du pick (B12/A7) et, hors paper trading, pari au portefeuille.

    En mode proxy, la cote enregistrée est une estimation : le pari n'entre au portefeuille
    qu'avec la cote réellement obtenue (commande /pris).
    """
    pid = pick_id or get_pick_id(table, today, p["Joueur"])
    if pid:
        p["Ref"] = pick_ref(table, pid)
    proxy_mode = getattr(cfg.betting, "exec_mode", "proxy") == "proxy"
    if pick_id and p.get("Cote") and p.get("MiseNum") and not cfg.mode.paper_trading and not proxy_mode:
        portfolio.log_bet("nhl", p["Joueur"], p["Categorie"], p["Cote"], p["MiseNum"], pick_id)


def log_picks_to_db(
    buts: List[Dict[str, Any]],
    asts: List[Dict[str, Any]],
    pts: List[Dict[str, Any]],
    all_players: List[Dict[str, Any]],
    wave_label: str,
    today: str,
    ds: Any,
) -> None:
    """Insère les picks et les joueurs évalués dans la base SQLite.

    Args:
        buts: Picks buteurs sélectionnés.
        asts: Picks passeurs sélectionnés.
        pts: Picks pointeurs sélectionnés.
        all_players: Tous les joueurs évalués (picks + non-picks).
        wave_label: Label de la vague.
        today: Date de la session NHL (YYYY-MM-DD).
        ds: DataStore pour accéder aux form_data, v5_data, matchups.
    """
    for p in buts:
        f = ds.form_data.get(p["Joueur"], {})
        v5 = ds.v5_data.get(p["Joueur"], {})
        adv = ds.matchups.get(p["Adversaire"], {})
        pick_id = insert_pick("picks", {
            "date": today, "vague": wave_label, "joueur": p["Joueur"], "equipe": p["Equipe"],
            "adversaire": p["Adversaire"], "score": p.get("Proba", 0), "verdict": p["Categorie"],
            "pp1": bool(p["PP1"]), "backup": p["Backup"], "b2b": p["B2B"], "is_home": p["IsHome"],
            "ixg": f.get("L10_ixG_G", 0), "hdcf": f.get("L10_iHDCF_G", 0), "sog": f.get("L10_SOG_G", 0),
            "atoi": f.get("ATOI", 0), "l10_g": f.get("L10_G_G", 0), "season_g": v5.get("G_GP", 0),
            "ga_g": adv.get("GA_G", 0), "hdca_g": adv.get("HDCA_G", 0),
            "opp_b2b": adv.get("B2B", False), "consec_goals": f.get("ConsecGoals", 0),
            "cote": p.get("Cote"), "mise": p.get("MiseNum"), "game_mode": cfg.api.mode,
            **_trace(p),
        })
        _after_insert("picks", p, pick_id, today)

    for p in asts:
        f = ds.form_data.get(p["Joueur"], {})
        v5 = ds.v5_data.get(p["Joueur"], {})
        adv = ds.matchups.get(p["Adversaire"], {})
        pick_id = insert_pick("picks_assists", {
            "date": today, "vague": wave_label, "joueur": p["Joueur"], "equipe": p["Equipe"],
            "adversaire": p["Adversaire"], "score": p.get("Proba", 0), "verdict": p["Categorie"],
            "pp1": bool(p["PP1"]), "backup": p["Backup"], "b2b": p["B2B"], "is_home": p["IsHome"],
            "atoi": f.get("ATOI", 0), "l10_a": f.get("L10_A_G", 0), "season_a": v5.get("A_GP", 0),
            "ga_g": adv.get("GA_G", 0), "opp_b2b": adv.get("B2B", False),
            "cote": p.get("Cote"), "mise": p.get("MiseNum"), "game_mode": cfg.api.mode,
            **_trace(p),
        })
        _after_insert("picks_assists", p, pick_id, today)

    # Marché Points supprimé tel que demandé par l'analyse.

    # Unified Player SQL Log
    for p in all_players:
        f, v5, adv = p["p_form"], p["p_v5"], p["adv_stats"]
        insert_player({
            "date": today, "vague": wave_label, "joueur": p["Joueur"], "equipe": p["Equipe"], "adversaire": p["Adversaire"],
            "score_but": p["Score_But"], "score_assist": p["Score_Assist"],
            "picked_but": p["Picked_But"], "picked_assist": p["Picked_Assist"],
            "pp1": "⭐" in f.get("PP1", ""), "backup": p["Backup"], "b2b": p["B2B"], "is_home": p["IsHome"],
            "ixg": f.get("L10_ixG_G", 0), "hdcf": f.get("L10_iHDCF_G", 0), "sog": f.get("L10_SOG_G", 0),
            "atoi": f.get("ATOI", 0), "l10_g": f.get("L10_G_G", 0), "l10_a": f.get("L10_A_G", 0),
            "season_g": v5.get("G_GP", 0), "season_a": v5.get("A_GP", 0),
            "ga_g": adv.get("GA_G", 0) if adv else 0, "hdca_g": adv.get("HDCA_G", 0) if adv else 0,
            "consec_goals": f.get("ConsecGoals", 0), "game_mode": cfg.api.mode,
            "cote": p.get("Cote"), "goalie_sv_pct": p.get("goalie_sv_pct"),
            "features_json": json.dumps(p.get("Features") or {}, separators=(",", ":")),
        })


def log_picks_to_csv(
    buts: List[Dict[str, Any]],
    asts: List[Dict[str, Any]],
    pts: List[Dict[str, Any]],
    all_players: List[Dict[str, Any]],
    wave_label: str,
    today: str,
    log_path: str,
    players_log_path: str,
) -> None:
    """Écrit les picks et joueurs dans les fichiers CSV de suivi.

    Args:
        buts: Picks buteurs.
        asts: Picks passeurs.
        pts: Picks pointeurs.
        all_players: Tous les joueurs évalués.
        wave_label: Label de la vague.
        today: Date de la session NHL.
        log_path: Chemin du CSV picks.
        players_log_path: Chemin du CSV joueurs.
    """
    def format_csv(val: Any) -> Any:
        return str(val).replace('.', cfg.csv.decimal_separator) if isinstance(val, float) else val

    # Picks CSV
    file_exists = os.path.exists(log_path)
    try:
        with open(log_path, 'a', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=['date', 'vague', 'joueur', 'type', 'score', 'cote', 'but'])
            if not file_exists:
                writer.writeheader()
            for p in buts:
                writer.writerow({k: format_csv(v) for k, v in {"date": today, "vague": wave_label, "joueur": p["Joueur"], "type": "BUT", "score": p.get("Proba", 0), "cote": p.get("Cote", ""), "but": ""}.items()})
            for p in asts:
                writer.writerow({k: format_csv(v) for k, v in {"date": today, "vague": wave_label, "joueur": p["Joueur"], "type": "ASSIST", "score": p.get("Proba", 0), "cote": p.get("Cote", ""), "but": ""}.items()})
    # CSV Logs (Points désactivés)
    except Exception as e:
        logger.error(f"Error writing to picks_log.csv: {e}")

    # Players CSV
    pl_exists = os.path.exists(players_log_path)
    try:
        with open(players_log_path, 'a', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=['date', 'vague', 'joueur', 'score_but', 'score_ast'])
            if not pl_exists:
                writer.writeheader()
            for p in all_players:
                writer.writerow({k: format_csv(v) for k, v in {"date": today, "vague": wave_label, "joueur": p["Joueur"], "score_but": p["Score_But"], "score_ast": p["Score_Assist"]}.items()})
    except Exception as e:
        logger.error(f"Error writing to players_log.csv: {e}")
