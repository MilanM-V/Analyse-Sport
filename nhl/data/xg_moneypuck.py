"""
data/xg_moneypuck.py — Historique xG match par match tiré des logs MoneyPuck (2008-2024).

Source : nhl/stats/skaters_all.csv (game-by-game MoneyPuck, une ligne par joueur x match x
situation, comme gamelog_moneypuck.py). On garde, par (playerId, gameId), les colonnes
`gamelog_schema.XG_COLUMNS` dont sont tirées les features xG :
  - situation 'all'  : xG individuel, tirs et xG à haut danger, xG pour / contre sur la glace,
                       départs de présence en zone offensive / défensive, temps de glace ;
  - situation '5on4' : xG individuel en avantage numérique (pp_ixg) ;
  - situation '5on5' : xG pour / contre sur la glace à 5 contre 5.

Sortie : nhl/data/gamelogs/mp_xg.parquet, VERSIONNÉE dans git (le CSV source de 2,6 Go n'existe
que sur le PC ; la prod en a besoin pour servir et ré-entraîner). Les saisons suivantes sont
reconstruites en saison par data/xg_nhlapi.py.

Données MoneyPuck (moneypuck.com) : usage non commercial, à citer.

Usage:
    python -m nhl.data.xg_moneypuck
"""
import os
import sys
import time

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from nhl.data.gamelog_schema import XG_COLUMNS  # noqa: E402

NHL_DIR = os.path.join(ROOT, "nhl")
SRC = os.path.join(NHL_DIR, "stats", "skaters_all.csv")
OUT = os.path.join(NHL_DIR, "data", "gamelogs", "mp_xg.parquet")

_ALL = ["I_F_xGoals", "I_F_highDangerShots", "I_F_highDangerxGoals", "OnIce_F_xGoals", "OnIce_A_xGoals",
        "I_F_oZoneShiftStarts", "I_F_dZoneShiftStarts", "icetime"]
_KEYS = ["playerId", "gameId", "season", "situation"]


def extract(src: str = SRC, min_season: int = 2008, max_season: int = 2024) -> pd.DataFrame:
    """Lit skaters_all.csv par chunks et produit la table xG (une ligne par playerId x gameId).

    Args:
        src: chemin du CSV MoneyPuck game-by-game.
        min_season, max_season: saisons conservées (année de début).

    Returns:
        DataFrame [playerId, gameId] + XG_COLUMNS (float32), trié par gameId puis playerId.
    """
    t0 = time.time()
    parts = {"all": [], "5on4": [], "5on5": []}
    for chunk in pd.read_csv(src, usecols=_KEYS + _ALL, chunksize=500_000, low_memory=False):
        chunk = chunk[(chunk["season"] >= min_season) & (chunk["season"] <= max_season)]
        for sit in parts:
            parts[sit].append(chunk[chunk["situation"] == sit])
        sys.stdout.write(f"\r  lecture... {sum(len(p) for p in parts['all']):,} lignes 'all' ({time.time() - t0:.0f}s)")
        sys.stdout.flush()
    print()
    out = pd.concat(parts["all"], ignore_index=True)[["playerId", "gameId"] + _ALL]
    pp = pd.concat(parts["5on4"], ignore_index=True)[["playerId", "gameId", "I_F_xGoals"]].rename(
        columns={"I_F_xGoals": "pp_ixg"})
    ev = pd.concat(parts["5on5"], ignore_index=True)[["playerId", "gameId", "OnIce_F_xGoals", "OnIce_A_xGoals"]].rename(
        columns={"OnIce_F_xGoals": "ev_onice_xgf", "OnIce_A_xGoals": "ev_onice_xga"})
    out = (out.merge(pp, on=["playerId", "gameId"], how="left").merge(ev, on=["playerId", "gameId"], how="left")
              .drop_duplicates(["playerId", "gameId"], keep="last"))
    out = out[["playerId", "gameId"] + XG_COLUMNS].astype(
        {"playerId": "int64", "gameId": "int64", **{c: "float32" for c in XG_COLUMNS}})
    out = out.sort_values(["gameId", "playerId"]).reset_index(drop=True)
    print(f"  {len(out):,} matchs-joueurs ({time.time() - t0:.0f}s)")
    return out


def main() -> None:
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    df = extract()
    df.to_parquet(OUT, index=False, compression="zstd")
    print(f"  écrit : {OUT} ({os.path.getsize(OUT) / 1e6:.1f} Mo)")


if __name__ == "__main__":
    main()
