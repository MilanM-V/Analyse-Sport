"""
shared/odds_api.py — Scraper centralisé pour The Odds API.

Gère les requêtes pour la NHL et la MLB de manière asynchrone, 
tout en surveillant le quota global mensuel (limite 500 requêtes).
"""

import os
import aiohttp
import asyncio
import logging
import re
import unicodedata
from collections import Counter
from typing import Any, Dict, Iterable, List, Optional, Tuple
from dotenv import load_dotenv

from shared.telegram_hub import send_telegram

load_dotenv()

logger = logging.getLogger("OddsAPI")

ODDS_API_KEY = os.getenv("api_odds")
BASE_URL = "https://api.the-odds-api.com/v4/sports"

def _norm(name: str) -> str:
    """Nom normalisé : sans accents, ponctuation ni casse."""
    s = "".join(c for c in unicodedata.normalize("NFD", str(name)) if unicodedata.category(c) != "Mn")
    return " ".join(re.sub(r"[^a-z ]", " ", s.lower()).split())


# Books « soft » US dont la médiane sert de proxy au prix FR (méthode du backtest)
SOFT_BOOKS = {
    "draftkings": "DraftKings", "fanduel": "FanDuel", "fanatics": "Fanatics", "bovada": "Bovada",
    "betmgm": "BetMGM", "williamhill_us": "Caesars", "betrivers": "BetRivers",
}


def apply_proxy(d: Dict[str, Any], exec_haircut: float, pin_haircut: float) -> None:
    """Cote d'exécution proxy d'un joueur/marché (modifie `d` en place).

    Médiane des cotes soft US × exec_haircut ; à défaut, cote « Oui » Pinnacle × pin_haircut
    (Pinnacle a moins de marge, d'où une décote plus forte). Rien si aucune des deux.
    """
    soft = sorted(d.get("soft") or [])
    if soft:
        n = len(soft)
        med = soft[n // 2] if n % 2 else (soft[n // 2 - 1] + soft[n // 2]) / 2
        d.update(soft_median=med, price=round(med * exec_haircut, 3), bookmaker="Proxy US",
                 price_source="soft", is_winamax=False)
    elif d.get("pin_yes"):
        d.update(price=round(d["pin_yes"] * pin_haircut, 3), bookmaker="Proxy Pinnacle",
                 price_source="pinnacle", is_winamax=False)


def match_player(api_name: str, candidates: Iterable[str]) -> Optional[str]:
    """Rapproche un nom de l'API d'un joueur de la liste (exact, puis initiale + nom, unique).

    Remplace l'ancien test par sous-chaîne qui confondait les homonymes partiels.
    """
    target = _norm(api_name)
    cands = list(candidates)
    exact = [c for c in cands if _norm(c) == target]
    if len(exact) == 1:
        return exact[0]
    parts = target.split()
    if len(parts) < 2:
        return None
    loose = [c for c in cands if _norm(c).split()[-1:] == parts[-1:] and _norm(c)[:1] == parts[0][:1]]
    return loose[0] if len(loose) == 1 else None


class OddsAPIClient:
    """Client centralisé pour The Odds API avec gestion de quota."""
    
    _quota_alert_sent = False
    
    @classmethod
    def check_quota(cls, headers: dict) -> None:
        """Vérifie l'en-tête x-requests-remaining et alerte si le quota est faible."""
        remaining = headers.get("x-requests-remaining")
        if remaining is None:
            return
            
        try:
            remaining = int(remaining)
            logger.info(f"[OddsAPI] Crédits restants : {remaining}")
            
            # Alerte si on passe sous les 50 crédits (et qu'on ne l'a pas encore envoyée)
            if remaining < 50 and not cls._quota_alert_sent:
                logger.warning(f"⚠️ QUOTA THE ODDS API CRITIQUE : {remaining} restants !")
                send_telegram(f"⚠️ <b>ALERTE THE ODDS API</b>\n\nIl ne te reste que <b>{remaining} requêtes</b> pour ce mois-ci sur ton compte The Odds API ! Le bot risque de s'arrêter bientôt.", recipient="admin")
                cls._quota_alert_sent = True
                
        except ValueError:
            pass

    @classmethod
    async def fetch_odds(cls, sport: str, market: str, players_map: Dict[str, str], bookmaker: str = "winamax",
                         exec_only_winamax: bool = False,
                         exec_books: Optional[Iterable[str]] = None,
                         proxy: Optional[Tuple[float, float]] = None,
                         team_names: Optional[Dict[str, str]] = None) -> Dict[str, Dict[str, Any]]:
        """
        Récupère les cotes pour une liste de joueurs sur un marché donné.
        
        Args:
            sport: Clé du sport (ex: 'icehockey_nhl', 'baseball_mlb').
            market: Le marché ciblé (ex: 'player_assists', 'pitcher_strikeouts').
            players_map: Dictionnaire {nom_joueur: equipe_du_joueur}.
            bookmaker: Le bookmaker principal ciblé (par défaut winamax).
            exec_only_winamax: si True, seule une cote Winamax peut servir de cote
                d'exécution (les autres books restent des références : Pinnacle no-vig).
            exec_books: clés The Odds API des books où l'utilisateur peut parier
                (ex. winamax_fr, betclic_fr). Prioritaire sur exec_only_winamax :
                la cote d'exécution est la MEILLEURE parmi ces books.
            proxy: (exec_haircut, pin_haircut). Si fourni, la cote d'exécution est un
                proxy (aucun book FR ne cote les props) : médiane des books soft US ×
                exec_haircut, sinon cote « Oui » Pinnacle × pin_haircut. Prioritaire
                sur exec_books.
            team_names: {abréviation: nom complet} pour cibler les events
                (les events The Odds API utilisent les noms complets).
            
        Returns:
            Dict { "Nom_Joueur": { "MARCHE": {price, bookmaker, is_winamax, pin_yes, pin_no, p_novig,
            soft_median, price_source} } }
        """
        if not ODDS_API_KEY or ODDS_API_KEY == "votre_cle_api_ici":
            logger.warning(f"Clé The Odds API manquante. Impossible de récupérer les cotes {sport}.")
            return {}

        results = {}
        
        async with aiohttp.ClientSession() as session:
            # 1. Récupérer la liste des matchs (events) du jour
            events_url = f"{BASE_URL}/{sport}/events"
            params = {"apiKey": ODDS_API_KEY}
            
            try:
                async with session.get(events_url, params=params) as resp:
                    cls.check_quota(resp.headers)
                    if resp.status != 200:
                        err_text = await resp.text()
                        logger.error(f"Erreur Events API [{resp.status}]: {err_text}")
                        if resp.status in (401, 429) or "credits" in err_text.lower():
                            if not getattr(cls, '_quota_error_sent', False):
                                send_telegram(f"❌ <b>ERREUR THE ODDS API</b>\n\nLe bot n'a plus de crédits ou la clé est bloquée (Code: {resp.status}). Récupération des cotes interrompue.", recipient="admin")
                                cls._quota_error_sent = True
                        return {}
                    events_data = await resp.json()
            except Exception as e:
                logger.error(f"Erreur connexion The Odds API (Events): {e}")
                return {}

            # Filtrer les events pour ne cibler que ceux où jouent nos joueurs
            # players_map contient {joueur: equipe}
            target_teams = {(team_names or {}).get(t, t) for t in players_map.values()}
            target_events = []
            for ev in events_data:
                home = ev.get('home_team', '')
                away = ev.get('away_team', '')
                
                # Checking partial overlap to accommodate different team names
                is_target = False
                for team in target_teams:
                    if team.lower() in home.lower() or team.lower() in away.lower() or home.lower() in team.lower() or away.lower() in team.lower():
                        is_target = True
                        break
                        
                if is_target:
                    target_events.append(ev['id'])
                    
            if not target_events:
                logger.warning(f"Aucun match correspondant trouvé dans l'API The Odds pour {target_teams}")
                return {}

            # 2. Récupérer les cotes pour chaque event ciblé
            logger.info(f"Appel Odds API sur {len(target_events)} matchs ciblés pour {len(players_map)} joueurs.")
            
            # L'utilisateur parie sur Winamax, mais on autorise Pinnacle/DraftKings comme cotes de repli
            target_bookmakers = {
                "winamax_fr": "Winamax",
                "winamax": "Winamax",
                "betclic_fr": "Betclic",
                "unibet_fr": "Unibet",
                "pmu_fr": "PMU",
                "pinnacle": "Pinnacle",
                **SOFT_BOOKS,
            }
            exec_set = set(exec_books) if exec_books else None
            coverage = Counter()  # nb de cotes "Oui/Over" par book : diagnostic de couverture
            
            for event_id in target_events:
                odds_url = f"{BASE_URL}/{sport}/events/{event_id}/odds"
                odds_params = {
                    "apiKey": ODDS_API_KEY,
                    "regions": "eu,us",
                    "markets": market,
                    "oddsFormat": "decimal"
                }
                
                try:
                    async with session.get(odds_url, params=odds_params) as resp:
                        cls.check_quota(resp.headers)
                        if resp.status == 422:
                            # Marché non disponible pour cet event, on l'ignore
                            continue
                        elif resp.status != 200:
                            err_text = await resp.text()
                            logger.error(f"Erreur Odds API event {event_id} [{resp.status}]: {err_text}")
                            if resp.status in (401, 429) or "credits" in err_text.lower():
                                if not getattr(cls, '_quota_error_sent', False):
                                    send_telegram(f"❌ <b>ERREUR THE ODDS API</b>\n\nLe bot n'a plus de crédits ou la clé est bloquée (Code: {resp.status}). Récupération des cotes interrompue.", recipient="admin")
                                    cls._quota_error_sent = True
                            continue
                            
                        event_odds = await resp.json()
                        bookmakers = event_odds.get('bookmakers', [])
                        
                        # Parsing des bookmakers
                        market_cap = market.upper().replace('PLAYER_', '').replace('PITCHER_', '')
                        is_goal_market = (market == 'player_goal_scorer_anytime')
                        for bm in bookmakers:
                            bm_key = bm['key']
                            if bm_key not in target_bookmakers:
                                continue  # On ignore les bookmakers exotiques/étrangers
                            bm_name = target_bookmakers[bm_key]
                            is_wm = "winamax" in bm_key
                            for mkt in bm.get('markets', []):
                                if mkt['key'] != market:
                                    continue
                                for outcome in mkt.get('outcomes', []):
                                    player_api = outcome.get('description', outcome.get('name', ''))
                                    price = outcome.get('price', 0)
                                    name_low = outcome.get('name', '').lower()
                                    point_ok = is_goal_market or outcome.get('point', 0.5) == 0.5
                                    side = ("yes" if name_low in ("yes", "over") else
                                            "no" if name_low in ("no", "under") else None)
                                    if side is None or not point_ok:
                                        continue
                                    p_name = match_player(player_api, players_map.keys())
                                    if p_name is None:
                                        continue
                                    data = results.setdefault(p_name, {}).setdefault(market_cap, {})
                                    # Référence "vraie" : Pinnacle, les deux côtés (pour le no-vig)
                                    if bm_key == "pinnacle":
                                        data["pin_" + side] = price
                                    if side != "yes":
                                        continue
                                    coverage[bm_key] += 1
                                    if bm_key in SOFT_BOOKS:
                                        data.setdefault("soft", []).append(price)
                                    if proxy is not None:
                                        continue  # cote d'exécution calculée après coup (apply_proxy)
                                    if exec_set is not None:
                                        # Meilleure cote parmi les books où l'utilisateur peut parier
                                        if bm_key in exec_set and price > data.get("price", 0):
                                            data.update(price=price, bookmaker=bm_name, is_winamax=is_wm)
                                        continue
                                    # Cote d'exécution : Winamax prioritaire ; les autres books
                                    # seulement si exec_only_winamax=False (MLB, ancien comportement)
                                    if is_wm:
                                        data.update(price=price, bookmaker="Winamax", is_winamax=True)
                                    elif not exec_only_winamax and not data.get("is_winamax"):
                                        if price > data.get("price", 0):
                                            data.update(price=price, bookmaker=bm_name, is_winamax=False)
                        # No-vig Pinnacle (multiplicatif) quand les deux côtés sont cotés
                        for p_name, mk in results.items():
                            d = mk.get(market_cap)
                            if d and d.get("pin_yes") and d.get("pin_no") and "p_novig" not in d:
                                iy, ino = 1.0 / d["pin_yes"], 1.0 / d["pin_no"]
                                d["p_novig"] = iy / (iy + ino)
                            if d and proxy is not None:
                                apply_proxy(d, *proxy)
                except Exception as e:
                    logger.error(f"Erreur connexion Odds API pour event {event_id}: {e}")

            logger.info(f"[OddsAPI] Couverture {market} (cotes Oui/Over par book) : {dict(coverage) or 'aucune'}")
            if proxy is not None:
                src = Counter(d.get("price_source") for mk in results.values() for d in mk.values() if d.get("price"))
                logger.info(f"[OddsAPI] Prix proxy {market} : {dict(src) or 'aucun'} (soft = médiane US, pinnacle = repli)")
            elif exec_set is not None and not any(coverage.get(b) for b in exec_set):
                logger.warning(f"[OddsAPI] Aucun book d'exécution ({sorted(exec_set)}) ne cote {market} : aucun pari possible.")
            return results

async def fetch_nhl_odds(players_map: Dict[str, str]) -> Dict[str, Dict[str, float]]:
    """
    Scrape les cotes NHL (Buteurs, Passeurs, Pointeurs).
    Args:
        players_map: Dict {Nom_Joueur: Equipe}.
    Returns:
        Dict des cotes: {'McDavid': {'BUTEUR': 2.2, 'PASSEUR': 1.8}}
    """
    if not players_map:
        return {}
        
    from nhl.config.constants import TEAM_ABBR_TO_FULL
    from nhl.config.settings import cfg
    # Cote d'exécution = meilleure cote parmi les books FR où l'utilisateur a un compte
    # ([betting] exec_books) ; Pinnacle sert de référence no-vig.
    # Mode "proxy" (défaut) : aucun book FR ne cote les props NHL dans The Odds API
    # (test du 2026-10-04) → cote d'exécution = médiane US × exec_haircut ; l'utilisateur
    # vérifie à la main que la cote FR dépasse la cote seuil du pick.
    b = cfg.betting
    books = list(getattr(b, "exec_books", ["winamax_fr"]))
    proxy = ((b.exec_haircut, b.pin_haircut) if getattr(b, "exec_mode", "proxy") == "proxy" else None)
    tasks = [
        OddsAPIClient.fetch_odds('icehockey_nhl', mk, players_map, exec_books=books, proxy=proxy,
                                 team_names=TEAM_ABBR_TO_FULL)
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

async def fetch_mlb_odds(players_map: Dict[str, str]) -> Dict[str, Dict[str, float]]:
    """
    Scrape les cotes MLB (Strikeouts).
    Args:
        players_map: Dict {Nom_Lanceur: Equipe}.
    Returns:
        Dict des cotes: {'Gerrit Cole': {'STRIKEOUTS': 1.85}}
    """
    if not players_map:
        return {}
        
    return await OddsAPIClient.fetch_odds('baseball_mlb', 'pitcher_strikeouts', players_map)

async def fetch_mlb_batter_odds(players_map: Dict[str, str], market: str = 'batter_home_runs') -> Dict[str, Dict[str, float]]:
    """
    Scrape les cotes MLB pour les frappeurs (Home Runs, Hits, etc.).
    Args:
        players_map: Dict {Nom_Joueur: Equipe}.
        market: Le marché ('batter_home_runs', 'batter_hits', etc.).
    Returns:
        Dict des cotes: {'Shohei Ohtani': {'HOME_RUNS': 3.50}}
    """
    if not players_map:
        return {}
        
    return await OddsAPIClient.fetch_odds('baseball_mlb', market, players_map)
