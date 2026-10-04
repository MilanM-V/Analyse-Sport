"""
core/odds.py — Cotes NHL : adaptation du client générique shared/odds_api.py à la NHL
(noms d'équipes, réglages [betting] de settings.toml).

Déplacé de shared/odds_api.py à l'audit P3 du 2026-10-04 : la couche partagée ne dépend
plus de nhl/.
"""
import asyncio
from typing import Callable, Dict, Iterable, Optional, Tuple

from nhl.config.constants import TEAM_ABBR_TO_FULL, TEAM_FULL_TO_ABBR
from nhl.config.settings import cfg
from shared.odds_api import OddsAPIClient, _norm


def nhl_team_key() -> Callable[[str], str]:
    """Nom d'équipe (complet, alias, accentué) -> abréviation NHL ; sinon nom normalisé.

    The Odds API écrit « Montréal Canadiens », « St Louis Blues », « Utah Mammoth ».
    """
    idx = {_norm(k): v for k, v in TEAM_FULL_TO_ABBR.items()}
    return lambda name: idx.get(_norm(name), _norm(name))


async def fetch_nhl_odds(players_map: Dict[str, str],
                         games: Optional[Iterable[Tuple[str, str]]] = None) -> Dict[str, Dict[str, float]]:
    """
    Scrape les cotes NHL (Buteurs, Passeurs, Pointeurs).
    Args:
        players_map: Dict {Nom_Joueur: Equipe}.
        games: affiches du soir [(domicile, extérieur)], abréviations ou noms complets.
    Returns:
        Dict des cotes: {'McDavid': {'BUTEUR': 2.2, 'PASSEUR': 1.8}}
    """
    if not players_map:
        return {}
        
    # Cote d'exécution = meilleure cote parmi les books FR où l'utilisateur a un compte
    # ([betting] exec_books) ; Pinnacle sert de référence no-vig.
    # Mode "proxy" (défaut) : aucun book FR ne cote les props NHL dans The Odds API
    # (test du 2026-10-04) → cote d'exécution = médiane US × exec_haircut ; l'utilisateur
    # vérifie à la main que la cote FR dépasse la cote seuil du pick.
    b = cfg.betting
    books = list(getattr(b, "exec_books", ["winamax_fr"]))
    proxy = ((b.exec_haircut, b.pin_haircut) if getattr(b, "exec_mode", "proxy") == "proxy" else None)
    full = [(TEAM_ABBR_TO_FULL.get(h, h), TEAM_ABBR_TO_FULL.get(a, a)) for h, a in games] if games else None
    key = nhl_team_key()
    tasks = [
        OddsAPIClient.fetch_odds('icehockey_nhl', mk, players_map, exec_books=books, proxy=proxy,
                                 team_names=TEAM_ABBR_TO_FULL, games=full, team_key=key,
                                 devig_method=getattr(b, "devig_method", "multiplicative"))
        for mk in ('player_goal_scorer_anytime', 'player_assists')
    ]
    
    res_buteur, res_assist = await asyncio.gather(*tasks)
    
    # Fusion des résultats
    final_results = {}
    for name in players_map.keys():
        final_results[name] = {}
        if name in res_buteur and 'GOAL_SCORER_ANYTIME' in res_buteur[name]:
            data_but = res_buteur[name]['GOAL_SCORER_ANYTIME']
            final_results[name]['BUTEUR'] = data_but
            final_results[name]['BUTS'] = data_but
        if name in res_assist and 'ASSISTS' in res_assist[name]:
            data_ast = res_assist[name]['ASSISTS']
            final_results[name]['PASSEUR'] = data_ast
            final_results[name]['ASSISTS'] = data_ast
            
    return final_results
