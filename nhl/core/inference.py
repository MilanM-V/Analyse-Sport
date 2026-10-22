"""
core/inference.py — Inférence de production à partir de la chaîne de features unique.

Le bot ne fabrique plus de features "à la main" (ancien prepare_features_for_player) :
il ajoute des lignes "match à venir" aux logs de match (API NHL, même schéma que
l'historique d'entraînement) et appelle `features.build_features`, exactement comme
l'entraînement et la simulation. C'est la garantie de parité train/serve.
"""
import logging
import os
import re
import unicodedata
from datetime import date
from typing import Any, Dict, Iterable, List, Optional, Tuple

import joblib
import numpy as np
import pandas as pd

from nhl.core.features import build_features, load_all_gamelogs, load_season_priors, load_xg_table
from nhl.data.gamelog_schema import GAMELOG_COLUMNS

logger = logging.getLogger("NHL.Inference")

NHL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODELS_DIR = os.path.join(NHL_DIR, "models")
# Les features « carrière » (car_*, sh_pct_shrunk) cumulent depuis le début des logs : le
# modèle a été entraîné avec un historique depuis 2008. Servir avec moins = train/serve skew.
HISTORY_START_MAX = pd.Timestamp("2009-10-01")


# Couverture xG minimale des saisons terminées (matchs-joueurs des logs présents dans la table xG)
XG_MIN_COVERAGE = 0.95
XG_MAX_LAG_DAYS = 2  # au-delà, alerte : le miroir MoneyPuck se met à jour une fois par jour


class InsufficientHistoryError(RuntimeError):
    """Les logs chargés ne couvrent pas l'historique attendu par le modèle (mp_gamelogs absent ?)."""


def check_history(logs: pd.DataFrame) -> None:
    """Lève InsufficientHistoryError si les logs commencent après HISTORY_START_MAX.

    Args:
        logs: logs de match chargés (colonne gameDate).
    """
    first = pd.to_datetime(logs["gameDate"]).min() if len(logs) else pd.NaT
    if pd.isna(first) or first > HISTORY_START_MAX:
        raise InsufficientHistoryError(
            f"Historique insuffisant : premiers logs au {first} (attendu ≤ {HISTORY_START_MAX.date()}). "
            "nhl/data/gamelogs/mp_gamelogs.parquet est-il présent ? (python -m nhl.data.gamelog_moneypuck)")


def check_xg_history(xg: pd.DataFrame, logs: pd.DataFrame, season: int) -> None:
    """Lève InsufficientHistoryError si la table xG ne couvre pas les saisons terminées des logs.

    Le moteur v2 a été entraîné avec l'xG de toutes les saisons depuis 2008 : le servir sans
    (fichier absent, rattrapage pas encore fait) fausserait ses features xG.

    Args:
        xg: table xG chargée (load_xg_table).
        logs: logs de match chargés.
        season: saison en cours (seules les saisons antérieures sont contrôlées).
    """
    done = logs.loc[(logs["season"] >= 2009) & (logs["season"] < season), ["playerId", "gameId", "season"]]
    if done.empty:
        return
    have = done.merge(xg[["playerId", "gameId"]].assign(_x=1), on=["playerId", "gameId"], how="left")["_x"].notna()
    cov = have.groupby(done["season"].to_numpy()).mean()
    bad = cov[cov < XG_MIN_COVERAGE]
    if len(bad):
        raise InsufficientHistoryError(
            "xG incomplet pour les saisons " + ", ".join(f"{int(s)} ({c:.0%})" for s, c in bad.items())
            + " : nhl/data/gamelogs/mp_xg.parquet (versionné) et xg_<saison>.parquet sont-ils présents ? "
            "(python -m nhl.data.xg_nhlapi --season <saison>)")


def xg_lag_days(xg: pd.DataFrame, logs: pd.DataFrame, season: int) -> int:
    """Jours entre le dernier match des logs de la saison et le dernier match qui a son xG."""
    cur = logs.loc[logs["season"] == season, ["gameId", "gameDate"]].drop_duplicates("gameId")
    if cur.empty:
        return 0
    last = pd.to_datetime(cur["gameDate"]).max()
    with_xg = cur[cur["gameId"].isin(set(xg["gameId"]))]
    ref = pd.to_datetime(with_xg["gameDate"]).max() if len(with_xg) else pd.to_datetime(cur["gameDate"]).min() - pd.Timedelta(days=1)
    return int((last - ref).days)


def _xg_files_stamp() -> Tuple:
    """Empreinte (nom, taille, date) des fichiers xG : la table n'est rechargée que s'ils ont changé."""
    d = os.path.join(NHL_DIR, "data", "gamelogs")
    if not os.path.isdir(d):
        return ()
    return tuple(sorted((f, os.path.getsize(os.path.join(d, f)), os.path.getmtime(os.path.join(d, f)))
                        for f in os.listdir(d) if f.endswith(".parquet") and (f == "mp_xg.parquet" or f.startswith("xg_"))))


def serving_history(logs: pd.DataFrame, season: int, pids: Iterable[int], today: pd.Timestamp) -> pd.DataFrame:
    """Logs passés nécessaires aux features des matchs à venir.

    - Tous les joueurs des saisons `season - 1` et `season` : les fenêtres d'équipe (team_gf_l10,
      opp_ga_l10, opp_sa_l10...) remontent sur la saison précédente pendant les ~10 premiers
      matchs. Avec les seuls joueurs du soir, ces matchs étaient incomplets, d'où un écart
      entre entraînement et service en début de saison (corrigé le 2026-10-08).
    - L'historique complet des joueurs du soir (features carrière, moyennes exponentielles).

    Args:
        logs: tous les logs de match chargés.
        season: saison des matchs à venir (année de début).
        pids: playerId des lignes à venir.
        today: date de la session ; seuls les matchs antérieurs sont gardés.
    """
    keep = (logs["season"] >= season - 1) | logs["playerId"].isin(set(pids))
    return logs[keep & (logs["gameDate"] < today)]


def norm_name(name: str) -> str:
    """Nom normalisé (sans accents, ponctuation, casse)."""
    s = "".join(c for c in unicodedata.normalize("NFD", str(name)) if unicodedata.category(c) != "Mn")
    return " ".join(re.sub(r"[^a-z ]", " ", s.lower()).split())


def load_model_bundle(market: str) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
    """Modèle à servir : retrain du VPS (models/live/) s'il est de la version de features courante, sinon models/.

    Un modèle live d'une ancienne version de features (retrain d'avant un changement de features)
    était servi quand même et le bot n'émettait plus aucun pick. Il est désormais ignoré. Si aucun
    modèle n'est compatible, le premier trouvé est renvoyé : bot_logic signale alors l'incompatibilité.

    Returns:
        (chemin, bundle joblib), ou (None, None) si aucun modèle n'existe.
    """
    from nhl.core.features import FEATURES_VERSION
    fallback: Tuple[Optional[str], Optional[Dict[str, Any]]] = (None, None)
    for d in (os.path.join(MODELS_DIR, "live"), MODELS_DIR):
        path = os.path.join(d, f"ml_model_{market}.pkl")
        if not os.path.exists(path):
            continue
        bundle = joblib.load(path)
        if bundle.get("features_version") == FEATURES_VERSION:
            return path, bundle
        logger.warning(f"Modèle {market} ignoré : {path} (features_version={bundle.get('features_version')} "
                       f"≠ {FEATURES_VERSION})")
        if fallback[0] is None:
            fallback = (path, bundle)
    return fallback


def model_path(market: str) -> Optional[str]:
    """Chemin du modèle servi pour `market` (cf. load_model_bundle)."""
    return load_model_bundle(market)[0]


def load_models() -> Dict[str, Dict[str, Any]]:
    """Charge ml_model_{but,ast}.pkl (dicts joblib) une seule fois."""
    models = {}
    for m in ("but", "ast"):
        path, bundle = load_model_bundle(m)
        if bundle is not None:
            models[m] = bundle
            logger.info(f"Modèle {m} chargé depuis {path} (algo={bundle.get('algo')}, "
                        f"features_version={bundle.get('features_version')}, cutoff={bundle.get('train_cutoff')})")
        else:
            logger.error(f"Modèle introuvable pour le marché {m}")
    return models


class FeatureEngine:
    """Maintient les logs de match + priors et produit les probabilités du jour."""

    def __init__(self) -> None:
        self.logs: Optional[pd.DataFrame] = None
        self.priors: Optional[Dict[str, pd.DataFrame]] = None
        self.models: Dict[str, Dict[str, Any]] = {}
        self.xg: Optional[pd.DataFrame] = None
        self.xg_lag: int = 0
        self._xg_stamp: Tuple = ()
        self._name_idx: Dict[str, List[Tuple[int, str, pd.Timestamp, str]]] = {}
        self._season_gp: Dict[Tuple[int, int], Dict[int, int]] = {}

    # ── Chargement ──────────────────────────────────────────────────────────
    def refresh(self, collect: bool = True) -> None:
        """Met à jour les logs (collecteur API NHL incrémental), les priors et les modèles."""
        from nhl.scripts.combine_season_data import ensure_combined
        ensure_combined()
        if collect:
            from nhl.data.gamelog_nhlapi import ensure_recent_seasons
            ensure_recent_seasons()
            try:  # xG des saisons récentes : quelques matchs (le rattrapage complet est fait en fin de journée)
                from nhl.data.xg_nhlapi import ensure_xg_recent
                ensure_xg_recent(backfill=False)
            except Exception as e:
                logger.error(f"[xG] mise à jour impossible : {e}", exc_info=True)
        logs = load_all_gamelogs()
        check_history(logs)  # aucune inférence sur un historique tronqué
        from nhl.data.gamelog_nhlapi import current_season
        xg = load_xg_table()
        check_xg_history(xg, logs, current_season())  # ni sur un xG incomplet (moteur v2)
        self.logs = logs
        self._set_xg(xg)
        self.priors = load_season_priors()
        self.models = load_models()
        self._season_gp = {}
        self._build_name_index()
        logger.info(f"FeatureEngine prêt : {len(self.logs):,} lignes de logs, "
                    f"dernière date {self.logs['gameDate'].max().date()}.")

    def _set_xg(self, xg: pd.DataFrame) -> None:
        from nhl.data.gamelog_nhlapi import current_season
        self.xg = xg
        self._xg_stamp = _xg_files_stamp()
        self.xg_lag = xg_lag_days(xg, self.logs, current_season()) if self.logs is not None else 0
        if self.xg_lag > XG_MAX_LAG_DAYS:
            logger.error(f"[xG] {self.xg_lag} jours de retard sur les logs de match (miroir MoneyPuck à jour ?)")

    def refresh_xg(self) -> None:
        """Avant chaque vague : derniers matchs xG (le miroir se met à jour vers 17h20 UTC), table rechargée si elle a changé."""
        try:
            from nhl.data.xg_nhlapi import ensure_xg_recent
            ensure_xg_recent(backfill=False)
        except Exception as e:  # l'xG déjà chargé reste utilisable
            logger.error(f"[xG] mise à jour impossible : {e}", exc_info=True)
        if self.logs is not None and _xg_files_stamp() != self._xg_stamp:
            self._set_xg(load_xg_table())

    def season_games(self, name: str, team: str, today: Optional[str] = None) -> int:
        """Matchs joués CETTE saison avant `today` (depuis les logs, sans repli sur la saison précédente).

        Le CSV « Player Season Totals » complète les joueurs absents de la saison en cours avec
        la saison précédente : un joueur sans match cette saison y apparaît avec GP ≥ 10, ce qui
        contournait le garde-fou « pas de pari avant 10 matchs » validé en simulation.
        """
        from nhl.data.gamelog_nhlapi import current_season
        hit = self.resolve(name, team)
        if hit is None or self.logs is None:
            return 0
        day = pd.Timestamp(today or date.today().isoformat())
        season = current_season(day.date())
        if (season, day.value) not in self._season_gp:
            cur = self.logs[(self.logs["season"] == season) & (self.logs["gameDate"] < day)]
            self._season_gp = {(season, day.value): cur.groupby("playerId").size().to_dict()}
        return int(self._season_gp[(season, day.value)].get(hit[0], 0))

    def prev_season_rates(self, name: str, team: str, today: Optional[str] = None) -> Optional[Dict[str, float]]:
        """GP, G/GP et A/GP de la saison régulière PRÉCÉDENTE (mode découverte, [early_season]).

        Returns:
            {'GP', 'G_GP', 'A_GP'}, ou None si le joueur est inconnu ou n'a pas joué la saison passée.
        """
        from nhl.data.gamelog_nhlapi import current_season
        hit = self.resolve(name, team)
        if hit is None or self.logs is None:
            return None
        day = pd.Timestamp(today or date.today().isoformat())
        prev = current_season(day.date()) - 1
        if getattr(self, "_prev_rates_season", None) != prev:
            lg = self.logs[(self.logs["season"] == prev) & (self.logs["game_type"] == 2)]
            agg = lg.assign(a=lg["a1"] + lg["a2"]).groupby("playerId").agg(GP=("g", "size"), G=("g", "sum"), A=("a", "sum"))
            self._prev_rates = {pid: {"GP": int(r.GP), "G_GP": r.G / r.GP, "A_GP": r.A / r.GP}
                                for pid, r in agg.iterrows()}
            self._prev_rates_season = prev
        return self._prev_rates.get(hit[0])

    def _build_name_index(self) -> None:
        last = (self.logs.sort_values("gameDate")
                    .drop_duplicates("playerId", keep="last")[["playerId", "name", "team", "gameDate", "position"]])
        idx: Dict[str, List[Tuple[int, str, pd.Timestamp, str]]] = {}
        for r in last.itertuples(index=False):
            idx.setdefault(norm_name(r.name), []).append((int(r.playerId), r.team, r.gameDate, r.position))
        self._name_idx = idx

    def resolve(self, name: str, team: str) -> Optional[Tuple[int, str]]:
        """Nom + équipe -> (playerId, position). Préfère l'homonyme de la bonne équipe, puis le plus récent."""
        cands = self._name_idx.get(norm_name(name), [])
        if not cands:
            parts = norm_name(name).split()
            if len(parts) >= 2:  # "A. Lafreniere" / variantes de prénom : initiale + nom
                cands = [c for k, v in self._name_idx.items() for c in v
                         if k.split()[-1] == parts[-1] and k[:1] == parts[0][:1]]
        if not cands:
            return None
        same_team = [c for c in cands if c[1] == team]
        best = max(same_team or cands, key=lambda c: c[2])
        return best[0], best[3]

    # ── Inférence ───────────────────────────────────────────────────────────
    def _upcoming_rows(self, games: List[Dict[str, Any]], lineup: Dict[str, str], today: str) -> pd.DataFrame:
        """Lignes "à venir" : effectif du dernier match de chaque équipe + joueurs alignés (RotoWire)."""
        # Saison du match à venir = saison calendaire courante (et non la dernière saison
        # présente dans les logs : en début de saison, aucun match n'est encore loggé).
        from nhl.data.gamelog_nhlapi import current_season
        season = current_season(pd.Timestamp(today).date())
        cur = self.logs[self.logs["season"] >= season - 1]  # effectif = dernier match connu
        rows = []
        by_team = {g["home"]: g for g in games} | {g["away"]: g for g in games}
        for team, g in by_team.items():
            is_home = int(team == g["home"])
            opp = g["away"] if is_home else g["home"]
            tl = cur[cur["team"] == team]
            if not tl.empty:
                last_gid = tl.loc[tl["gameDate"].idxmax(), "gameId"]
                for r in tl[tl["gameId"] == last_gid].itertuples(index=False):
                    rows.append((int(r.playerId), r.name, team, opp, is_home, r.position, g))
        for name, team in lineup.items():
            g = by_team.get(team)
            hit = self.resolve(name, team)
            if g is None or hit is None:
                continue
            pid, pos = hit
            is_home = int(team == g["home"])
            rows.append((pid, name, team, g["away"] if is_home else g["home"], is_home, pos, g))
        out = pd.DataFrame([{
            "playerId": pid, "name": nm, "gameId": int(g["gameId"]), "season": season, "game_type": 2,
            "gameDate": pd.Timestamp(today), "team": tm, "opp": op, "is_home": h, "position": pos,
        } for pid, nm, tm, op, h, pos, g in rows])
        out = out.drop_duplicates(["playerId", "gameId"], keep="last")
        for c in GAMELOG_COLUMNS:
            if c not in out:
                out[c] = np.nan
        return out[GAMELOG_COLUMNS]

    def predict(self, games: List[Dict[str, Any]], lineup: Dict[str, str],
                today: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
        """Probabilités but / passe pour les joueurs alignés.

        Args:
            games: [{'gameId': int, 'home': 'BOS', 'away': 'TOR'}, ...] (abréviations).
            lineup: {nom_joueur: abréviation_équipe} des joueurs à évaluer.
            today: date de la session NHL 'YYYY-MM-DD'.

        Returns:
            {nom_joueur: {'playerId', 'but', 'ast', 'features': {...}}}
        """
        if self.logs is None:
            self.refresh()
        today = today or date.today().isoformat()
        up = self._upcoming_rows(games, lineup, today)
        if up.empty:
            return {}
        season = int(up["season"].iloc[0])
        hist = serving_history(self.logs, season, up["playerId"], pd.Timestamp(today))
        feats = build_features(pd.concat([hist, up], ignore_index=True), self.priors, self.xg)
        feats = feats[feats["target_but"].isna() & feats["gameId"].isin(up["gameId"])]
        by_pid = feats.set_index("playerId")
        out: Dict[str, Dict[str, Any]] = {}
        for name, team in lineup.items():
            hit = self.resolve(name, team)
            if hit is None or hit[0] not in by_pid.index:
                logger.warning(f"[Inférence] {name} ({team}) introuvable dans les logs — ignoré.")
                continue
            row = by_pid.loc[[hit[0]]].iloc[0]
            res: Dict[str, Any] = {"playerId": hit[0], "features": {}}
            for m, bundle in self.models.items():
                cols = bundle["features"]
                x = row[cols].to_numpy(dtype=float).reshape(1, -1)
                res[m] = float(bundle["model"].predict_proba(x)[0, 1])
                res["features"][m] = {c: (None if pd.isna(v) else float(v)) for c, v in zip(cols, x[0])}
            out[name] = res
        return out
