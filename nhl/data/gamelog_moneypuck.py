"""
data/gamelog_moneypuck.py — Extraction des logs de match depuis MoneyPuck.

Source : nhl/stats/skaters_all.csv (game-by-game MoneyPuck, une ligne par
joueur x match x situation). On pivote les situations 'all' et '5on4'
vers le schéma unique `gamelog_schema.GAMELOG_COLUMNS`.

Usage:
    python -m nhl.data.gamelog_moneypuck
"""
import os
import sys
import time

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from nhl.data.gamelog_schema import enforce_schema  # noqa: E402

NHL_DIR = os.path.join(ROOT, "nhl")
SRC = os.path.join(NHL_DIR, "stats", "skaters_all.csv")
OUT = os.path.join(NHL_DIR, "data", "gamelogs", "mp_gamelogs.parquet")

_COLS = [
    "playerId", "name", "gameId", "season", "gameDate", "playerTeam", "opposingTeam",
    "home_or_away", "position", "situation", "icetime",
    "I_F_goals", "I_F_primaryAssists", "I_F_secondaryAssists", "I_F_shotsOnGoal",
    "I_F_missedShots", "I_F_blockedShotAttempts",
]


def extract(src: str = SRC, min_season: int = 2008) -> pd.DataFrame:
    """Lit skaters_all.csv par chunks et produit le gamelog unifié.

    Args:
        src: chemin du CSV MoneyPuck game-by-game.
        min_season: première saison conservée.

    Returns:
        DataFrame au schéma GAMELOG_COLUMNS.
    """
    t0 = time.time()
    alls, pps = [], []
    for chunk in pd.read_csv(src, usecols=_COLS, chunksize=500_000, low_memory=False):
        chunk = chunk[chunk["season"] >= min_season]
        alls.append(chunk[chunk["situation"] == "all"])
        pps.append(chunk[chunk["situation"] == "5on4"][
            ["playerId", "gameId", "icetime", "I_F_goals", "I_F_shotsOnGoal"]])
        sys.stdout.write(f"\r  lecture... {sum(len(a) for a in alls):,} lignes 'all' ({time.time() - t0:.0f}s)")
        sys.stdout.flush()
    print()
    df = pd.concat(alls, ignore_index=True)
    pp = pd.concat(pps, ignore_index=True).rename(columns={
        "icetime": "pp_icetime", "I_F_goals": "pp_g", "I_F_shotsOnGoal": "pp_sog"})
    df = df.merge(pp, on=["playerId", "gameId"], how="left")

    out = pd.DataFrame({
        "playerId": df["playerId"],
        "name": df["name"],
        "gameId": df["gameId"],
        "season": df["season"],
        "game_type": (df["gameId"] // 10_000) % 100,   # 2 = saison régulière, 3 = playoffs
        "gameDate": pd.to_datetime(df["gameDate"].astype(str), format="%Y%m%d"),
        "team": df["playerTeam"],
        "opp": df["opposingTeam"],
        "is_home": (df["home_or_away"] == "HOME").astype(int),
        "position": df["position"],
        "toi": df["icetime"] / 60.0,
        "pp_toi": df["pp_icetime"].fillna(0) / 60.0,
        "g": df["I_F_goals"],
        "a1": df["I_F_primaryAssists"],
        "a2": df["I_F_secondaryAssists"],
        "sog": df["I_F_shotsOnGoal"],
        "missed": df["I_F_missedShots"],
        "blocked_att": df["I_F_blockedShotAttempts"],
        "pp_g": df["pp_g"].fillna(0),
        "pp_sog": df["pp_sog"].fillna(0),
    })
    out = enforce_schema(out)
    print(f"  {len(out):,} matchs-joueurs, saisons {out.season.min()}-{out.season.max()} ({time.time() - t0:.0f}s)")
    return out


def main() -> None:
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    df = extract()
    df.to_parquet(OUT, index=False)
    print(f"  écrit : {OUT}")


if __name__ == "__main__":
    main()
