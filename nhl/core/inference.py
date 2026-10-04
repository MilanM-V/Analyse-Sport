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

from nhl.core.features import FEATURES, build_features, load_all_gamelogs, load_season_priors
from nhl.data.gamelog_schema import GAMELOG_COLUMNS

logger = logging.getLogger("NHL.Inference")

NHL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODELS_DIR = os.path.join(NHL_DIR, "models")


def norm_name(name: str) -> str:
    """Nom normalisé (sans accents, ponctuation, casse)."""
    s = "".join(c for c in unicodedata.normalize("NFD", str(name)) if unicodedata.category(c) != "Mn")
    return " ".join(re.sub(r"[^a-z ]", " ", s.lower()).split())


def model_path(market: str) -> Optional[str]:
    """Chemin du modèle à servir : retrain du VPS (models/live/) s'il existe, sinon models/."""
    for d in (os.path.join(MODELS_DIR, "live"), MODELS_DIR):
        path = os.path.join(d, f"ml_model_{market}.pkl")
        if os.path.exists(path):
            return path
    return None


def load_models() -> Dict[str, Dict[str, Any]]:
    """Charge ml_model_{but,ast}.pkl (dicts joblib) une seule fois."""
    models = {}
    for m in ("but", "ast"):
        path = model_path(m)
        if path:
            models[m] = joblib.load(path)
            logger.info(f"Modèle {m} chargé (algo={models[m].get('algo')}, "
                        f"features_version={models[m].get('features_version')}, cutoff={models[m].get('train_cutoff')})")
        else:
            logger.error(f"Modèle introuvable pour le marché {m}")
    return models


class FeatureEngine:
    """Maintient les logs de match + priors et produit les probabilités du jour."""

    def __init__(self) -> None:
        self.logs: Optional[pd.DataFrame] = None
        self.priors: Optional[Dict[str, pd.DataFrame]] = None
        self.models: Dict[str, Dict[str, Any]] = {}
        self._name_idx: Dict[str, List[Tuple[int, str, pd.Timestamp, str]]] = {}

    # ── Chargement ──────────────────────────────────────────────────────────
    def refresh(self, collect: bool = True) -> None:
        """Met à jour les logs (collecteur API NHL incrémental), les priors et les modèles."""
        from nhl.scripts.combine_season_data import ensure_combined
        ensure_combined()
        if collect:
            from nhl.data.gamelog_nhlapi import ensure_recent_seasons
            ensure_recent_seasons()
        self.logs = load_all_gamelogs()
        self.priors = load_season_priors()
        self.models = load_models()
        self._build_name_index()
        logger.info(f"FeatureEngine prêt : {len(self.logs):,} lignes de logs, "
                    f"dernière date {self.logs['gameDate'].max().date()}.")

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
        pids = set(up["playerId"])
        season = int(up["season"].iloc[0])
        hist = self.logs[(self.logs["season"] == season) | (self.logs["playerId"].isin(pids))]
        hist = hist[hist["gameDate"] < pd.Timestamp(today)]
        feats = build_features(pd.concat([hist, up], ignore_index=True), self.priors)
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
