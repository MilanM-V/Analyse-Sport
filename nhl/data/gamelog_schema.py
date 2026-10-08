"""
data/gamelog_schema.py — Schéma unique des logs de match (MoneyPuck & API NHL).

Les deux sources (historique MoneyPuck, collecteur API NHL) produisent un
DataFrame avec EXACTEMENT ces colonnes. `nhl.core.features.build_features`
ne consomme que ce schéma : c'est la garantie de parité train/serve.
"""
from typing import Dict, List

import pandas as pd

from nhl.config.constants import TEAM_CLEANER

GAMELOG_COLUMNS: List[str] = [
    "playerId", "name", "gameId", "season", "game_type", "gameDate",
    "team", "opp", "is_home", "position",
    "toi", "pp_toi",            # minutes
    "g", "a1", "a2", "sog", "missed", "blocked_att",
    "pp_g", "pp_sog",
]

GAMELOG_DTYPES: Dict[str, str] = {
    "playerId": "int64", "gameId": "int64", "season": "int16", "game_type": "int8",
    "is_home": "int8", "toi": "float32", "pp_toi": "float32",
    "g": "int16", "a1": "int16", "a2": "int16", "sog": "int16", "missed": "int16",
    "blocked_att": "int16", "pp_g": "int16", "pp_sog": "int16",
}

# Table xG match par match (une ligne par playerId x gameId), mêmes définitions que les logs
# MoneyPuck : historique 2008-2024 tiré de MoneyPuck (data/xg_moneypuck.py), saisons suivantes
# reconstruites à partir des tirs MoneyPuck et de l'API NHL (data/xg_nhlapi.py).
XG_COLUMNS: List[str] = [
    "I_F_xGoals", "I_F_highDangerShots", "I_F_highDangerxGoals",   # xG individuel, tirs et xG à haut danger
    "OnIce_F_xGoals", "OnIce_A_xGoals",                            # xG pour / contre sur la glace
    "pp_ixg",                                                       # xG individuel à 5 contre 4
    "ev_onice_xgf", "ev_onice_xga",                                 # xG pour / contre sur la glace à 5 contre 5
    "I_F_oZoneShiftStarts", "I_F_dZoneShiftStarts",                 # départs de présence en zone off. / déf.
    "icetime",                                                      # temps de glace (secondes)
]

# Codes historiques MoneyPuck / anciennes franchises -> abréviation courante
_EXTRA_TEAM_MAP: Dict[str, str] = {"PHX": "ARI", "ATL": "WPG"}


def clean_team(code: str) -> str:
    """Normalise une abréviation d'équipe (MoneyPuck 'L.A' -> 'LAK', etc.)."""
    code = str(code).strip()
    code = TEAM_CLEANER.get(code, code)
    return _EXTRA_TEAM_MAP.get(code, code)


def normalize_position(pos: str) -> str:
    """Ramène une position à C / L / R / D (G conservé)."""
    p = str(pos).strip().upper()
    return {"LW": "L", "RW": "R", "W": "L", "F": "C"}.get(p, p)


def enforce_schema(df: pd.DataFrame) -> pd.DataFrame:
    """Ordonne les colonnes, applique les types et vérifie la complétude.

    Raises:
        ValueError: si une colonne du schéma manque.
    """
    missing = [c for c in GAMELOG_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Colonnes manquantes dans le gamelog : {missing}")
    out = df[GAMELOG_COLUMNS].copy()
    out["gameDate"] = pd.to_datetime(out["gameDate"])
    for col, dt in GAMELOG_DTYPES.items():
        out[col] = out[col].fillna(0).astype(dt)
    out["team"] = out["team"].map(clean_team)
    out["opp"] = out["opp"].map(clean_team)
    out["position"] = out["position"].map(normalize_position)
    return out.sort_values(["gameDate", "gameId", "playerId"]).reset_index(drop=True)
