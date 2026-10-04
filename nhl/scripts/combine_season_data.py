"""
scripts/combine_season_data.py — Fusionne les agrégats de saison MoneyPuck.

Pour chaque type (goalies, lines, skaters, teams) :
    <type>_2008_to_2024.csv (historique) + <type>.csv (saison la plus récente)
    -> <type>_all.csv (une seule table, toutes saisons).

Les fichiers sources ne sont jamais modifiés. En cas de doublon sur la clé
(id, saison, situation), la ligne du fichier le plus récent est conservée.

Usage:
    python nhl/scripts/combine_season_data.py
"""
import os
import sys
from typing import Dict, List

import pandas as pd

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

# Clé d'unicité par type de fichier
KEYS: Dict[str, List[str]] = {
    "goalies": ["playerId", "season", "situation"],
    "skaters": ["playerId", "season", "situation"],
    "lines": ["lineId", "season", "situation", "team"],
    "teams": ["team", "season", "situation"],
}


def combine(kind: str) -> pd.DataFrame:
    """Concatène l'historique et la saison récente pour un type donné.

    Args:
        kind: 'goalies', 'lines', 'skaters' ou 'teams'.

    Returns:
        DataFrame combiné, trié par saison.
    """
    hist_path = os.path.join(DATA_DIR, f"{kind}_2008_to_2024.csv")
    cur_path = os.path.join(DATA_DIR, f"{kind}.csv")
    frames = []
    for prio, path in enumerate((hist_path, cur_path)):
        if not os.path.exists(path):
            print(f"  [{kind}] {os.path.basename(path)} introuvable — ignoré.")
            continue
        df = pd.read_csv(path, low_memory=False)
        df["_prio"] = prio
        frames.append(df)
        print(f"  [{kind}] {os.path.basename(path)} : {len(df):,} lignes, saisons {df['season'].min()}-{df['season'].max()}")
    if not frames:
        raise FileNotFoundError(f"Aucune source pour {kind}")

    out = pd.concat(frames, ignore_index=True, sort=False)
    n_before = len(out)
    out = (out.sort_values("_prio")
              .drop_duplicates(subset=KEYS[kind], keep="last")
              .drop(columns="_prio")
              .sort_values(["season"] + [k for k in KEYS[kind] if k != "season"])
              .reset_index(drop=True))
    print(f"  [{kind}] -> {len(out):,} lignes ({n_before - len(out)} doublons retirés), "
          f"saisons {out['season'].min()}-{out['season'].max()}")
    return out


def ensure_combined() -> None:
    """Régénère les *_all.csv manquants ou plus anciens que leurs sources (appelé par le bot)."""
    for kind in KEYS:
        out_path = os.path.join(DATA_DIR, f"{kind}_all.csv")
        srcs = [os.path.join(DATA_DIR, f"{kind}_2008_to_2024.csv"), os.path.join(DATA_DIR, f"{kind}.csv")]
        newest_src = max((os.path.getmtime(s) for s in srcs if os.path.exists(s)), default=0)
        if not os.path.exists(out_path) or os.path.getmtime(out_path) < newest_src:
            combine(kind).to_csv(out_path, index=False, encoding="utf-8")


def main() -> None:
    print("=" * 60)
    print(" FUSION DES DONNÉES DE SAISON (2008 -> dernière saison)")
    print("=" * 60)
    for kind in KEYS:
        df = combine(kind)
        out_path = os.path.join(DATA_DIR, f"{kind}_all.csv")
        df.to_csv(out_path, index=False, encoding="utf-8")
        print(f"  [{kind}] écrit : {out_path}\n")


if __name__ == "__main__":
    main()
