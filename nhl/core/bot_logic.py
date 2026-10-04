import os
import csv
import json
import logging
import threading
from datetime import datetime, timedelta
from shared.utils import paris_now
import subprocess
import sys
from typing import Dict, List, Any, Optional, Set, Tuple

# Ajout du dossier racine au sys.path pour permettre l'exécution standalone
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import nhl.core.loaders as loaders
import nhl.core.scraper as scraper

import asyncio
from nhl.core.datastore import DataStore
from nhl.core.services import TelegramNotifier
from nhl.config.settings import cfg
from nhl.core.inference import InsufficientHistoryError

logger = logging.getLogger("NHL.BotLogic")

from shared.base_bot import BaseSportBot
from shared.portfolio import Portfolio

class NhlBot(BaseSportBot):
    """
    Main logic for the NHL Betting Bot.
    Handles scanning, wave management, analysis, and notification.
    """
    sport_name = "NHL"

    def __init__(self, datastore: DataStore, telegram_notifier: TelegramNotifier) -> None:
        """
        Initializes the NhlBot.

        Args:
            datastore: The DataStore instance for in-memory data access.
            telegram_notifier: The TelegramNotifier instance for sending alerts.
        """
        super().__init__()
        self.datastore = datastore
        self.telegram = telegram_notifier
        self.portfolio = Portfolio()

        self.matchs_traites: Set[str] = set()
        self.matches_du_jour: List[Dict[str, Any]] = []
        self.compos_en_memoire: Dict[str, Dict[str, Any]] = {}
        self.vagues_envoyees: Set[str] = set()
        self.matchs_envoyes: Set[str] = set()
        self._scan_lock = threading.Lock()

        self.ecart_max_vague_min: int = cfg.wave.ecart_max_min
        self.force_envoi_min_avant: int = cfg.wave.force_envoi_min_avant
        self.log_path: str = './stats/picks_log.csv'
        self.players_log_path: str = './stats/players_log.csv'
        self.fichier_compos_temp: str = "compos_live.txt"
        self.is_paused: bool = False
        self._history_alert_sent: bool = False
        self.sent_state_path: str = "sent_matches.json"
        self._load_sent_matches()
        from nhl.core.inference import FeatureEngine
        self.engine = FeatureEngine()

    def _load_sent_matches(self) -> None:
        """Recharge les matchs déjà envoyés pour la session NHL courante.

        Le watchdog redémarre le bot à chaque pull : sans cette persistance,
        les mêmes vagues étaient renvoyées (et loggées) plusieurs fois.
        """
        try:
            with open(self.sent_state_path, encoding="utf-8") as f:
                state = json.load(f)
        except FileNotFoundError:
            return
        except (OSError, json.JSONDecodeError) as e:
            logger.warning(f"État des matchs envoyés illisible ({e}) — ignoré.")
            return
        if state.get("session_date") == self.get_nhl_session_date():
            self.matchs_envoyes.update(state.get("matchs", []))
            self.vagues_envoyees.update(state.get("vagues", []))
            logger.info(f"{len(self.matchs_envoyes)} match(s) déjà envoyé(s) aujourd'hui rechargé(s).")

    def _save_sent_matches(self) -> None:
        """Écrit l'état des matchs envoyés sur disque."""
        try:
            with open(self.sent_state_path, "w", encoding="utf-8") as f:
                json.dump({"session_date": self.get_nhl_session_date(),
                           "matchs": sorted(self.matchs_envoyes),
                           "vagues": sorted(self.vagues_envoyees)}, f)
        except OSError as e:
            logger.error(f"Impossible de sauvegarder l'état des matchs envoyés : {e}")

    @staticmethod
    def get_nhl_session_date() -> str:
        """
        Returns the current NHL session date (J-1 if before 07:00 AM).
        
        Returns:
            Date string in YYYY-MM-DD format.
        """
        return (paris_now() - timedelta(hours=14)).strftime("%Y-%m-%d")

    def is_active_hours(self) -> bool:
        """
        Checks if the current time is within active scanning hours.

        Returns:
            True if active, False otherwise.
        """
        now = paris_now()
        hour = now.hour
        return (hour > 16 or (hour == 16 and paris_now().minute >= 30)) or hour <= 4

    def update_daily_stats(self) -> bool:
        """
        Ensures daily CSV stats are updated and loaded into DataStore.

        Returns:
            True if successful, False otherwise.
        """
        now = paris_now()
        nhl_date = self.get_nhl_session_date()

        ok, ko_files = self._check_csv_integrity()

        if self.datastore.last_load_date != nhl_date or not ok:
            if not ok and self.datastore.last_load_date == nhl_date:
                logger.warning(f"[{now.strftime('%H:%M:%S')}] CSV KO : {', '.join(ko_files)} — Re-extraction forcée...")
            else:
                logger.info(f"\n[{now.strftime('%H:%M:%S')}] MISE À JOUR API NHL EN COURS...")

            try:
                from nhl.data.fetcher import update_all_stats_sync
                update_all_stats_sync()
                
                ok2, ko2 = self._check_csv_integrity()
                if not ok2:
                    logger.error(f"ÉCHEC CRITIQUE: Fichiers manquants après mise à jour: {', '.join(ko2)}")
                    return False

                self.datastore.force_refresh()
                self.engine.refresh()
                logger.info("Fichiers API NHL mis à jour avec succès et chargés en RAM.")
                return True
            except InsufficientHistoryError as e:
                logger.critical(str(e))
                if not self._history_alert_sent:
                    self.telegram.send_message(f"🚨 <b>NHL : aucun pick</b>\n{e}")
                    self._history_alert_sent = True
                return False
            except Exception as e:
                logger.error(f"Exception lors de la mise à jour des stats : {e}")
                import traceback
                logger.error(traceback.format_exc())
                return False

        return True

    def _check_csv_integrity(self) -> Tuple[bool, List[str]]:
        """
        Checks if all required CSV files exist, have minimum required lines,
        and are not older than 7 days (stale data detection).

        Returns:
            A tuple (is_ok, list_of_errors).
        """
        required_csv = {
            "last 10.csv": 50, "Player Season Totals.csv": 200, "team.csv": 10,
            "power play.csv": 50, "goalies.csv": 30, "on_ice.csv": 50, "pk.csv": 10,
        }
        max_age_days = 7  # Fichiers plus vieux que 7 jours → forcer un re-fetch
        now_ts = paris_now().timestamp()
        ko = []
        for filename, min_lines in required_csv.items():
            path = f"./stats/{filename}"
            if not os.path.exists(path):
                ko.append(f"{filename} (manquant)")
                continue
            try:
                with open(path, encoding="utf-8-sig") as f:
                    nb = sum(1 for _ in f)
                if nb < min_lines:
                    ko.append(f"{filename} ({nb} lignes < {min_lines} attendues)")
                    continue
                # Vérification de l'âge du fichier
                file_age_days = (now_ts - os.path.getmtime(path)) / 86400
                if file_age_days > max_age_days:
                    ko.append(f"{filename} (périmé : {file_age_days:.0f} jours)")
            except Exception as e:
                ko.append(f"{filename} (erreur : {e})")
        return (len(ko) == 0, ko)

    def parse_match_datetime(self, time_str: str) -> Optional[datetime]:
        """Parses Flashscore time string into a datetime object."""
        now = paris_now()
        try:
            # L'année n'est pas fournie : on prend celle qui place le match au plus près
            # de maintenant (gère le passage 31.12 -> 01.01).
            dts = [datetime.strptime(f"{time_str} {y}", "%d.%m. %H:%M %Y") for y in (now.year - 1, now.year, now.year + 1)]
            dt = min(dts, key=lambda d: abs((d - now).total_seconds()))
            if dt < now - timedelta(hours=12):
                dt += timedelta(days=1)
            return dt
        except ValueError:
            return None

    def purge_old_matches(self) -> None:
        """Removes matches older than 5 minutes from memory."""
        now = paris_now()
        a_supprimer = []
        for match_id, data in self.compos_en_memoire.items():
            dt = self.parse_match_datetime(data["match_info"]["time"])
            if dt and now > dt + timedelta(minutes=5):
                a_supprimer.append(match_id)
        for m_id in a_supprimer:
            del self.compos_en_memoire[m_id]
            logger.info(f"   Match {m_id} purgé de la mémoire.")

    def build_waves(self, match_ids: List[str]) -> List[List[str]]:
        """Groups matches into waves based on their start time proximity."""
        if not match_ids:
            return []
        sorted_matches = sorted(
            match_ids,
            key=lambda mid: self.parse_match_datetime(self.compos_en_memoire[mid]["match_info"]["time"]) or datetime.max
        )
        waves = []
        curr_wave = [sorted_matches[0]]
        for i in range(1, len(sorted_matches)):
            prev_dt = self.parse_match_datetime(self.compos_en_memoire[sorted_matches[i-1]]["match_info"]["time"])
            curr_dt = self.parse_match_datetime(self.compos_en_memoire[sorted_matches[i]]["match_info"]["time"])

            ecart = (curr_dt - prev_dt).total_seconds() / 60 if prev_dt and curr_dt else 999

            if ecart <= self.ecart_max_vague_min:
                curr_wave.append(sorted_matches[i])
            else:
                waves.append(curr_wave)
                curr_wave = [sorted_matches[i]]
        waves.append(curr_wave)
        return waves

    def is_wave_complete(self, wave_ids: List[str], all_matches: List[Dict[str, Any]]) -> bool:
        """Checks if all matches in a time window have lineups available."""
        first_dt = self.parse_match_datetime(self.compos_en_memoire[wave_ids[0]]["match_info"]["time"])
        last_dt = self.parse_match_datetime(self.compos_en_memoire[wave_ids[-1]]["match_info"]["time"])
        if not first_dt or not last_dt: return True

        window_start = first_dt - timedelta(minutes=1)
        window_end = last_dt + timedelta(minutes=self.ecart_max_vague_min)

        for m in all_matches:
            m_dt = self.parse_match_datetime(m["time"])
            if m_dt and window_start <= m_dt <= window_end:
                if m["id"] not in self.compos_en_memoire:
                    return False
        return True

    def should_force_send(self, wave_ids: List[str]) -> bool:
        """Checks if a wave should be sent regardless of completeness due to time limit."""
        first_dt = self.parse_match_datetime(self.compos_en_memoire[wave_ids[0]]["match_info"]["time"])
        if not first_dt: return False
        mins_before = (first_dt - paris_now()).total_seconds() / 60
        return mins_before <= self.force_envoi_min_avant

    def run_scan_cycle(self) -> None:
        """Main periodic task: scans Flashscore, updates lineups, and triggers evaluation."""
        if self.is_paused:
            logger.info(f"[{paris_now().strftime('%H:%M:%S')}] Bot en PAUSE. Scan ignoré.")
            return

        if not self._scan_lock.acquire(blocking=False):
            logger.warning("Un scan est déjà en cours. Ignoré pour éviter les lancements multiples.")
            return
        try:
            if not self.update_daily_stats():
                logger.warning("Analyse suspendue — CSV invalides.")
                return

            mode_icon = "🏆" if cfg.api.mode == "playoff" else "🏒"
            logger.info(f"\n[{paris_now().strftime('%H:%M:%S')}] {mode_icon} Lancement du scan API / RotoWire (Mode: {cfg.api.mode})...")
            self.purge_old_matches()

            self.matches_du_jour = scraper.get_scheduled_matches()

            if not self.is_active_hours():
                logger.info(f"[{paris_now().strftime('%H:%M:%S')}] Hors horaires (05h-17h). Scan des compos ignoré.")
                return

            for m in self.matches_du_jour:
                match_id = m['id']
                if match_id in self.matchs_envoyes:
                    continue

                logger.info(f"   Vérification compo : {m['home']} - {m['away']}...")
                compo = scraper.get_lineups(match_id, m['home'], m['away'])

                if isinstance(compo, dict):
                    logger.info("    COMPO TROUVÉE (ou mise à jour) ! Mise en mémoire.")
                    self.compos_en_memoire[match_id] = {"match_info": m, "compo": compo}
                    self.matchs_traites.add(match_id)
                else:
                    logger.info(f"   {compo} — On réessaiera au prochain cycle.")

            # L'Early Pass à 17:00 a été retiré à la demande de l'utilisateur.
            # self.evaluate_waves(self.matches_du_jour) continue de gérer les scans normaux.

            self.evaluate_waves(self.matches_du_jour)
        except Exception as e:
            logger.error(f"ERREUR CRITIQUE lors du run_scan_cycle : {e}", exc_info=True)
            self.telegram.send_crash_alert(e, context="run_scan_cycle")
        finally:
            self._scan_lock.release()

    def evaluate_early_pass(self) -> None:
        """Envoie un message informatif avec les compos probables à 17h."""
        if not self.compos_en_memoire:
            return
        
        # Ne pas renvoyer les matchs déjà envoyés par evaluate_waves()
        ready_ids = [mid for mid in self.compos_en_memoire if mid not in self.matchs_envoyes]
        if ready_ids:
            wave_label = f"PREMIER JET 17H - COMPOS PROBABLES ({len(ready_ids)} matchs)"
            logger.info(f"   Early Pass {wave_label}   ENVOI !")
            self.run_analysis_and_send(ready_ids, wave_label, is_early=True)

    def evaluate_waves(self, matches_du_jour: List[Dict[str, Any]]) -> None:
        """Processes available lineups into waves and triggers analysis."""
        if not self.compos_en_memoire:
            return

        # Filtrer les matchs déjà envoyés pour éviter les doublons
        pending_ids = [mid for mid in self.compos_en_memoire if mid not in self.matchs_envoyes]
        if not pending_ids:
            return

        waves = self.build_waves(pending_ids)
        ready_ids = []
        
        for wave in waves:
            wave_key = self.compos_en_memoire[wave[0]]["match_info"]["time"]
            if wave_key in self.vagues_envoyees:
                continue

            if self.is_wave_complete(wave, matches_du_jour) or self.should_force_send(wave):
                self.vagues_envoyees.add(wave_key)
                for mid in wave:
                    self.matchs_envoyes.add(mid)
                    ready_ids.append(mid)

        if ready_ids:
            self._save_sent_matches()
            wave_label = f"Matchs du Jour ({len(ready_ids)} matchs)"
            logger.info(f"   Vagues combinées {wave_label}   ENVOI !")
            self.run_analysis_and_send(ready_ids, wave_label)

    def run_analysis_and_send(self, wave_ids: List[str], wave_label: str, is_early: bool = False) -> None:
        """Performs analysis on a wave of matches and sends results."""
        from nhl.core.market_filter import MIN_GP, evaluate_early_season
        from nhl.core.features import FEATURES_VERSION
        from nhl.core.betting import select_bets
        from nhl.core.formatter import format_telegram_v18
        from nhl.core.logger_csv import log_picks_to_db, log_picks_to_csv

        logger.info(f"\n--- ANALYSE VAGUE {wave_label} ---")

        with open(self.fichier_compos_temp, "w", encoding="utf-8") as f:
            for mid in wave_ids:
                data = self.compos_en_memoire[mid]
                m = data["match_info"]
                c = data["compo"]
                f.write(f"Match : {m['home']} - {m['away']} ({m['time']})\n"
                        f"  goal dom: {c['goalDom']}\n  goal ext: {c['goalext']}\n"
                        f"  f1 dom: {', '.join(c['f1_dom']) if isinstance(c['f1_dom'], list) else c['f1_dom']}\n"
                        f"  f1 ext: {', '.join(c['f1_ext']) if isinstance(c['f1_ext'], list) else c['f1_ext']}\n"
                        f"  f2 dom: {', '.join(c['f2_dom']) if isinstance(c['f2_dom'], list) else c['f2_dom']}\n"
                        f"  f2 ext: {', '.join(c['f2_ext']) if isinstance(c['f2_ext'], list) else c['f2_ext']}\n"
                        f"{'-'*40}\n")

        ds = self.datastore
        TODAY = paris_now().strftime("%Y-%m-%d")

        matches_soir = []
        compos_brutes = []
        goalies = set()
        rotowire_teams = {}

        for mid in wave_ids:
            m = self.compos_en_memoire[mid]["match_info"]
            c = self.compos_en_memoire[mid]["compo"]
            
            home, away = m["home"], m["away"]
            matches_soir.append((home, away))
            
            if c.get("goalDom"): goalies.add(c["goalDom"])
            if c.get("goalext"): goalies.add(c["goalext"])
            
            for key in ["f1_dom", "f1_ext", "f2_dom", "f2_ext"]:
                if key in c and isinstance(c[key], list):
                    team_for_key = home if "dom" in key else away
                    team_abbr = loaders.clean_team_name(team_for_key)
                    for player in c[key]:
                        matched_player = player
                        if player in ds.known_players:
                            compos_brutes.append(player)
                        else:
                            from shared.utils import normalize_name
                            n_player = normalize_name(player)
                            matched = False
                            for known_p in ds.known_players:
                                if normalize_name(known_p) == n_player:
                                    compos_brutes.append(known_p)
                                    matched_player = known_p
                                    matched = True
                                    break
                            if not matched:
                                compos_brutes.append(player)
                        rotowire_teams[matched_player] = team_abbr

        compos_filtrees = [p for p in compos_brutes if p in ds.form_data]
        
        # Diagnostic : combien de joueurs passent chaque étape du filtre
        logger.info(f"  Joueurs compos bruts: {len(compos_brutes)} → filtrés (dans form_data): {len(compos_filtrees)}")
        if len(compos_brutes) > 0 and len(compos_filtrees) == 0:
            logger.warning("  ⚠️ AUCUN joueur RotoWire reconnu dans form_data (last 10.csv). "
                           "Données potentiellement périmées ou début de saison.")
        
        home_teams = [loaders.clean_team_name(m[0]) for m in matches_soir]
        
        opponents = {}
        for t1, t2 in matches_soir:
            t1_abbr = loaders.clean_team_name(t1)
            t2_abbr = loaders.clean_team_name(t2)
            opponents[t1_abbr] = t2_abbr
            opponents[t2_abbr] = t1_abbr

        b2b_teams = [t for t in loaders.get_b2b_teams('./stats/match.csv', TODAY) if t in opponents]
        pp1_players = set(loaders.get_auto_pp1_players(ds.form_data, ds.pp_stats, list(opponents.keys())))
        seen_players: Set[str] = set()

        if self.engine.logs is None:
            try:
                self.engine.refresh()
            except InsufficientHistoryError as e:
                logger.critical(f"Vague {wave_label} ignorée : {e}")
                return
        ml_models = {m: b for m, b in self.engine.models.items()
                     if b.get("features_version") == FEATURES_VERSION}
        for m in set(self.engine.models) - set(ml_models):
            logger.error(f"Modèle '{m}' incompatible (features_version="
                         f"{self.engine.models[m].get('features_version')} ≠ {FEATURES_VERSION}) : "
                         f"ré-entraîner avec nhl/scripts/train_models.py. Aucun pick {m} émis.")

        final_picks_but: List[Dict[str, Any]] = []
        final_picks_ast: List[Dict[str, Any]] = []
        all_evaluated_players: List[Dict[str, Any]] = []

        # Passe 1 : Filtrage de base pour identifier les candidats potentiels
        candidates_but = []
        candidates_ast = []

        for player in compos_filtrees:
            if player in seen_players:
                continue
            seen_players.add(player)

            p_form = ds.form_data[player]
            form_team = loaders.clean_team_name(p_form['Team'])
            compo_team = rotowire_teams.get(player, form_team)
            
            if form_team != compo_team:
                logger.warning(f"⚠️ TRADE DÉTECTÉ: {player} form_data={form_team}, "
                               f"RotoWire={compo_team}. Utilisation de l'équipe RotoWire.")
                team = compo_team
            else:
                team = form_team

            if p_form['ATOI'] < cfg.thresholds.general.atoi_min or team not in opponents:
                continue

            adv = opponents[team]
            adv_stats = ds.matchups.get(adv) or {}
            
            # Identifier le gardien adverse
            adv_goalie = ""
            for mid in wave_ids:
                c = self.compos_en_memoire[mid]["compo"]
                m = self.compos_en_memoire[mid]["match_info"]
                if m["home"] == adv: adv_goalie = c.get("goalDom", "")
                elif m["away"] == adv: adv_goalie = c.get("goalext", "")
            
            adv_goalie_stats = ds.goalie_stats.get(adv_goalie, {})
            goalie_sv_pct = adv_goalie_stats.get('SV%', 0.0) # Assume loaders adds it, or we use defaults if missing
            if not goalie_sv_pct: goalie_sv_pct = adv_goalie_stats.get('sv_pct', 0.0)
            
            is_backup = loaders.check_if_backup_goalie(adv_goalie, ds.goalie_stats)
            v5_p = ds.v5_data.get(player, {})
            is_home = team in home_teams

            # GP de la saison calculé sur les logs (pas de repli sur la saison précédente)
            session_day = self.get_nhl_session_date()
            v5_eval = {**(v5_p or {}), "GP": self.engine.season_games(player, team, session_day)}
            # Moins de 10 matchs : mode découverte ([early_season]), taux mélangés avec la saison passée
            prev = self.engine.prev_season_rates(player, team, session_day) if v5_eval["GP"] < MIN_GP else None
            cat_but, cat_ast, phase = evaluate_early_season(
                player, p_form, v5_eval, adv_stats, is_home, prev
            )

            is_pp1 = player in pp1_players
            is_b2b = team in b2b_teams and adv not in b2b_teams
            opp_is_b2b = adv in b2b_teams and team not in b2b_teams
            
            common_data = {
                "Joueur": player, "Equipe": team, "Adversaire": adv, "IsHome": is_home,
                "Pos": str(v5_p.get('Position', '')).strip() if v5_p else "",
                "PP1": "⭐" if is_pp1 else "",
                "Backup": is_backup, "B2B": is_b2b,
                "Synergie": False,
                "p_form": p_form, "v5_p": v5_p, "adv_stats": adv_stats,
                "opp_is_b2b": opp_is_b2b, "consec": int(p_form.get('ConsecGoals', 0)),
                "is_pp1": is_pp1, "is_b2b": is_b2b, "goalie_sv_pct": goalie_sv_pct,
                "Phase": phase,
            }

            if cat_but:
                p_but = common_data.copy()
                p_but["Categorie"] = cat_but
                candidates_but.append(p_but)
            if cat_ast:
                p_ast = common_data.copy()
                p_ast["Categorie"] = cat_ast
                candidates_ast.append(p_ast)

            all_evaluated_players.append({
                "Joueur": player, "Equipe": team, "Adversaire": adv, "IsHome": is_home,
                "Score_But": 0.0, "Score_Assist": 0.0, "Score_Point": 0.0,
                "Picked_But": bool(cat_but), "Picked_Assist": bool(cat_ast), "Picked_Point": False,
                "Backup": is_backup, "B2B": is_b2b,
                "p_form": p_form, "p_v5": v5_p, "adv_stats": adv_stats,
                "goalie_sv_pct": goalie_sv_pct
            })

        # Diagnostic : combien de joueurs passent les filtres de pré-sélection
        logger.info(f"  Évalués: {len(all_evaluated_players)} | Candidats Buteur: {len(candidates_but)} | Candidats Passeur: {len(candidates_ast)}")

        # Passe 2 : Récupération des cotes The Odds API AVANT prédiction ML
        # On fetch les cotes pour tous les joueurs évalués pour enrichir le log
        players_to_fetch = {r["Joueur"]: r["Equipe"] for r in all_evaluated_players}
        odds_map = {}
        if players_to_fetch:
            logger.info(f"Récupération des cotes (API) pour {len(players_to_fetch)} joueurs évalués...")
            from nhl.core.odds import fetch_nhl_odds
            # asyncio.run() ne fonctionne pas dans un thread background — créer un loop dédié
            loop = asyncio.new_event_loop()
            try:
                odds_map = loop.run_until_complete(fetch_nhl_odds(players_to_fetch, games=matches_soir))
                if not is_early:
                    self._log_market_data(loop, matches_soir, wave_ids)
            finally:
                loop.close()
            
            any_odds_found = any((data.get('BUTS') is not None) or (data.get('ASSISTS') is not None) for data in odds_map.values())
            if not any_odds_found:
                logger.error("ALERTE CRITIQUE : AUCUNE COTE TROUVÉE POUR AUCUN JOUEUR DE LA VAGUE !")
                self.telegram.send_message(f"🚨 <b>ALERTE CRITIQUE SCRAPER</b> 🚨\nLe scraper n'a trouvé <b>aucune cote</b> pour la vague {wave_label}.")

        # Mise à jour des cotes dans all_evaluated_players pour logger_csv
        for p in all_evaluated_players:
            odds_but = odds_map.get(p["Joueur"], {}).get("BUTS", {})
            if isinstance(odds_but, dict): p["Cote"] = odds_but.get("price")

        # Passe 3 : Inférence ML (chaîne de features unique, cf. nhl/core/features.py)
        games = []
        for mid in wave_ids:
            mi = self.compos_en_memoire[mid]["match_info"]
            games.append({"gameId": int(mi["id"]), "home": loaders.clean_team_name(mi["home"]),
                          "away": loaders.clean_team_name(mi["away"])})
        lineup = {p["Joueur"]: p["Equipe"] for p in candidates_but + candidates_ast}
        preds = self.engine.predict(games, lineup, self.get_nhl_session_date()) if ml_models else {}

        # Passe 4 : stratégie de mise P2 (nhl/core/betting.py) — mélange modèle / Pinnacle
        # no-vig, EV sur la cote Winamax uniquement, Kelly sans plancher, plafonds par match/jour.
        game_of_team = {}
        for g in games:
            game_of_team[g["home"]] = g["gameId"]
            game_of_team[g["away"]] = g["gameId"]
        cands = []
        for market, candidates, odds_key, score_key in (
            ("but", candidates_but, "BUTS", "Score_But"),
            ("ast", candidates_ast, "ASSISTS", "Score_Assist"),
        ):
            for p in candidates:
                odds_data = odds_map.get(p["Joueur"], {}).get(odds_key, {})
                odds_data = odds_data if isinstance(odds_data, dict) else {}
                p["Cote"] = odds_data.get("price")
                p["Bookmaker"] = odds_data.get("bookmaker", "Inconnu")
                p["PNovig"] = odds_data.get("p_novig")
                p["PriceSource"] = odds_data.get("price_source")
                pred = preds.get(p["Joueur"])
                if market not in ml_models or not pred or market not in pred:
                    continue
                p["PModel"] = pred[market]
                p["PlayerId"] = pred.get("playerId")
                p["Features"] = pred["features"].get(market, {})
                p["ModelVersion"] = f"{ml_models[market].get('algo')}@{ml_models[market].get('train_cutoff')}"
                for ep in all_evaluated_players:
                    if ep["Joueur"] == p["Joueur"]:
                        ep[score_key] = p["PModel"]
                        ep.setdefault("Features", {})[market] = p["Features"]
                cands.append({"market": market, "p_model": p["PModel"], "p_novig": p["PNovig"],
                              "cote": p["Cote"], "game_id": game_of_team.get(p["Equipe"]),
                              "early": p.get("Phase") == "early", "_pick": p})

        selected = select_bets(cands, bankroll=self.portfolio.get_balance(),
                               current_exposure=self.portfolio.get_pending_exposure())
        for b in selected:
            p = b["_pick"]
            p.update(Proba=b["p_final"], EV=b["ev"], MiseNum=b["mise"], Mise=f"{b['mise']} U",
                     CoteSeuil=b["cote_seuil"])
            (final_picks_but if b["market"] == "but" else final_picks_ast).append(p)
        # Contexte du match (fiches privées admin) : affiche, heure
        for mid in wave_ids:
            mi = self.compos_en_memoire[mid]["match_info"]
            teams = {loaders.TEAM_MAPPING.get(mi["home"], mi["home"]), loaders.TEAM_MAPPING.get(mi["away"], mi["away"])}
            for p in final_picks_but + final_picks_ast:
                if p["Equipe"] in teams:
                    full = [loaders.REVERSE_TEAM_MAPPING.get(t, t) for t in (mi["home"], mi["away"])]
                    p.update(Match=f"{full[0]} vs {full[1]}", Heure=mi.get("time", ""))
        logger.info(f"  Candidats avec proba : {len(cands)} | Paris retenus : {len(selected)} "
                    f"(but {len(final_picks_but)}, ast {len(final_picks_ast)})")

        # Enregistrement AVANT l'envoi : le message affiche la référence (B12/A7) de chaque
        # pick, utilisée par /pris et /skip.
        if not is_early:
            session_date = self.get_nhl_session_date()
            log_picks_to_db(final_picks_but, final_picks_ast, [], all_evaluated_players, wave_label, session_date, ds)

        msg = format_telegram_v18(
            final_picks_but, final_picks_ast, [],
            wave_label, wave_ids, self.compos_en_memoire
        )
        self.telegram.send_message(msg)

        if not is_early:
            # Fiche privée par pick (boutons Pris / Skip) : seul l'admin les voit
            for market, picks in (("but", final_picks_but), ("ast", final_picks_ast)):
                for p in picks:
                    if p.get("Ref"):
                        self.telegram.send_pick_card(p, market)
            log_picks_to_csv(final_picks_but, final_picks_ast, [], all_evaluated_players, wave_label, session_date, self.log_path, self.players_log_path)

    def _log_market_data(self, loop: asyncio.AbstractEventLoop, matches: List[Tuple[str, str]],
                         wave_ids: List[str]) -> None:
        """Journalise le contexte de marché (futures features, audit P2) sans bloquer la vague."""
        from nhl.core.odds_logging import log_extra_props, log_match_context
        session_date = self.get_nhl_session_date()
        goalies = {}
        for mid in wave_ids:
            mi, c = self.compos_en_memoire[mid]["match_info"], self.compos_en_memoire[mid]["compo"]
            goalies[(mi["home"], mi["away"])] = (c.get("goalDom"), c.get("goalext"))
        try:
            if getattr(cfg.betting, "log_match_context", True):
                loop.run_until_complete(log_match_context(matches, goalies, session_date))
            loop.run_until_complete(log_extra_props(matches, session_date))
        except Exception as e:  # la journalisation ne doit jamais empêcher l'envoi des picks
            logger.error(f"[Contexte] Journalisation du marché impossible : {e}", exc_info=True)

    def end_of_day_cleanup(self) -> None:
        """Resolves pending picks and cleans up session data."""
        try:
            from nhl.core.updater import update_pending_picks
            logger.info("🔄 Auto-résolution des résultats dans la DB avant le rapport final...")
            update_pending_picks()
            
            # --- EXPORT DASHBOARD ---
            import dashboard.exporter as dashboard_exporter
            dashboard_exporter.export_data()
            dashboard_exporter.git_commit_and_push()
        except Exception as e:
            logger.error(f"Erreur auto-résolution ou export : {e}")

        if self.matchs_traites:

            self.matchs_traites.clear()
            self.compos_en_memoire.clear()
            self.vagues_envoyees.clear()
            self.matchs_envoyes.clear()
            self._save_sent_matches()
            logger.info("Nettoyage de fin de journée terminé.")

