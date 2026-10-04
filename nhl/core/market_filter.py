"""
core/market_filter.py — Éligibilité des joueurs par marché (Buteur, Passeur).

Les features et l'inférence sont dans nhl/core/features.py et nhl/core/inference.py.
"""
import logging
from typing import Any, Dict, Optional, Tuple

from nhl.config.settings import cfg

logger = logging.getLogger("NHL.Filter")


def evaluate_player_markets(
    player: str,
    p_form: Dict[str, Any],
    v5_p: Dict[str, Any],
    adv_stats: Dict[str, Any],
    is_home: bool,
) -> Tuple[Optional[str], Optional[str]]:
    """Évalue un joueur contre les filtres de base des marchés (Buteur et Passeur).
    Les pointeurs sont désactivés pour ROI négatif.

    Args:
        player: Nom du joueur.
        p_form: Stats récentes (last 10 games).
        v5_p: Stats saison complète.
        adv_stats: Stats de l'équipe adverse.
        is_home: True si le joueur joue à domicile.

    Returns:
        Tuple (cat_but, cat_ast) — chaque valeur est le nom de la
        catégorie ("BUTEUR", "PASSEUR") ou None si non qualifié.
    """
    # Extractions de métriques
    season_g = float(v5_p.get('G_GP', 0)) if v5_p else 0.0
    l10_sog = float(p_form.get('L10_SOG_G', 0))
    l10_hdcf = float(p_form.get('L10_iHDCF_G', 0))

    season_a = float(v5_p.get('A_GP', 0)) if v5_p else 0.0
    opp_ga = float(adv_stats.get('GA_G', 0)) if adv_stats else 0.0
    l10_a = float(p_form.get('L10_A_G', 0))
    p_atoi = float(p_form.get('ATOI', 0))
    pos = str(v5_p.get('Position', '')).strip() if v5_p else ""

    # Mode Playoff / Modern Scanning : On ouvre l'évaluation à tout le Top 9 actif (ATOI >= 13.5 min ou PP1)
    is_playoff = (cfg.api.mode == "playoff")
    is_top9 = (p_atoi >= 13.5)

    # Buteurs : Attaquants actifs (Défenseurs toujours strictement exclus)
    cat_but = None
    # On rejette explicitement 'D', 'LD', 'RD', mais aussi les positions vides (Cold Start) 
    # pour éviter que l'IA hallucine sur un défenseur avec un gros temps de glace.
    # Les CSV NHL API codent les ailiers 'L' / 'R' (et non 'LW' / 'RW')
    is_forward = pos in ('C', 'L', 'R', 'LW', 'RW', 'F', 'W')
    gp = int(v5_p.get('GP', 0)) if v5_p else 0
    
    if gp >= 10 and (is_forward or (pos == '' and season_g >= 1.0)) and (is_top9 or season_g >= 0.20):
        if (is_home or is_playoff or not cfg.thresholds.buteurs.home_only):
            cat_but = "BUTEUR"

    # Passeurs : Joueurs avec temps de glace significatif
    cat_ast = None
    if gp >= 10 and (is_top9 or season_a >= 0.30):
        if (is_home or is_playoff or not cfg.thresholds.passeurs.home_only):
            cat_ast = "PASSEUR"

    return cat_but, cat_ast
