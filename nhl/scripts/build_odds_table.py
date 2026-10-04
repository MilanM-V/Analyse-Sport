"""
scripts/build_odds_table.py — Table de cotes historiques propre (par bookmaker).

Lit nhl/data/odds/historical_odds.db (JSON brut The Odds API) et produit :
  - odds_long.parquet : une ligne par (event, bookmaker, marché, joueur, côté).
  - odds_wide.parquet : une ligne par (date, playerId, marché) avec
      pin_yes / pin_no / p_novig (Pinnacle dévigé, multiplicatif),
      soft_median / soft_max / n_soft (bookmakers hors Pinnacle, côté Yes/Over).

Le joueur est rattaché à un playerId via les gamelogs (date + équipes du match),
ce qui lève les homonymes (ex. les deux Sebastian Aho).

Usage:
    python nhl/scripts/build_odds_table.py
"""
import difflib
import json
import os
import re
import sqlite3
import sys
import unicodedata
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from nhl.config.constants import TEAM_FULL_TO_ABBR  # noqa: E402

ODDS_DIR = os.path.join(ROOT, "nhl", "data", "odds")
DB_PATH = os.path.join(ODDS_DIR, "historical_odds.db")
GAMELOG_DIR = os.path.join(ROOT, "nhl", "data", "gamelogs")

TEAM_MAP = dict(TEAM_FULL_TO_ABBR, **{"Arizona Coyotes": "ARI"})
MARKETS = {"player_goal_scorer_anytime": "but", "player_assists": "ast"}


def norm_full(name: str) -> str:
    """Nom complet normalisé : minuscules, sans accents ni ponctuation."""
    if not isinstance(name, str):
        return ""
    s = "".join(c for c in unicodedata.normalize("NFD", name) if unicodedata.category(c) != "Mn")
    s = re.sub(r"[^a-z ]", " ", s.lower())
    return " ".join(s.split())


def norm_drop(name: str) -> str:
    """Comme norm_full mais SUPPRIME les caractères non-ASCII au lieu de les translittérer.

    Les noms MoneyPuck ont perdu leurs lettres accentuées ('Alexis Lafrenire'),
    cette clé permet de les rapprocher de 'Alexis Lafrenière'.
    """
    if not isinstance(name, str):
        return ""
    s = re.sub(r"[^a-z ]", " ", "".join(c for c in name.lower() if ord(c) < 128))
    return " ".join(s.split())


def parse_long() -> pd.DataFrame:
    """Parse le cache SQLite en table longue (dernier snapshot par event)."""
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT snapshot_time, json_response FROM api_cache WHERE event_id != 'EVENTS'"
    ).fetchall()
    conn.close()
    recs: List[Dict] = []
    for snap, raw in rows:
        data = (json.loads(raw) or {}).get("data") or {}
        if not data.get("bookmakers"):
            continue
        commence = pd.Timestamp(data["commence_time"])
        home, away = TEAM_MAP.get(data.get("home_team")), TEAM_MAP.get(data.get("away_team"))
        if not home or not away:
            continue
        date_et = commence.tz_convert("US/Eastern").strftime("%Y-%m-%d")
        for bm in data["bookmakers"]:
            for mkt in bm.get("markets", []):
                market = MARKETS.get(mkt["key"])
                if not market:
                    continue
                for o in mkt.get("outcomes", []):
                    if market == "ast" and o.get("point") != 0.5:
                        continue
                    recs.append({
                        "date": date_et, "commence_time": commence, "snapshot": snap,
                        "home": home, "away": away, "book": bm["key"], "market": market,
                        "side": "yes" if o.get("name") in ("Yes", "Over") else "no",
                        "player_raw": o.get("description", ""),
                        "price": float(o.get("price", np.nan)),
                    })
    df = pd.DataFrame(recs)
    df["player_norm"] = df["player_raw"].map(norm_full)
    df["player_drop"] = df["player_raw"].map(norm_drop)
    # Plusieurs snapshots possibles pour un même event : on garde le plus tardif (≈ closing)
    df = (df.sort_values("snapshot")
            .drop_duplicates(["date", "home", "away", "book", "market", "side", "player_norm"], keep="last"))
    return df


def to_wide(long: pd.DataFrame) -> pd.DataFrame:
    """Pivot : Pinnacle dévigé + statistiques des soft books (long doit contenir playerId)."""
    key = ["date", "home", "away", "market", "playerId", "gameId", "team"]
    pin = (long[long.book == "pinnacle"]
           .pivot_table(index=key, columns="side", values="price", aggfunc="last")
           .rename(columns={"yes": "pin_yes", "no": "pin_no"})
           .reset_index())
    soft = (long[(long.book != "pinnacle") & (long.side == "yes")]
            .groupby(key)["price"].agg(soft_median="median", soft_max="max", n_soft="count")
            .reset_index())
    wide = soft.merge(pin, on=key, how="outer")
    for c in ("pin_yes", "pin_no"):
        if c not in wide:
            wide[c] = np.nan
    inv_y, inv_n = 1.0 / wide["pin_yes"], 1.0 / wide["pin_no"]
    # p_novig reste multiplicatif (reproductibilité des phases historiques) ; les autres
    # méthodes sont stockées à côté (la prod utilise [betting] devig_method).
    wide["p_novig"] = inv_y / (inv_y + inv_n)  # NaN si un côté manque
    from shared.devig import METHODS, devig_yes
    for meth in METHODS:
        wide[f"p_novig_{meth}"] = devig_yes(wide["pin_yes"].to_numpy(), wide["pin_no"].to_numpy(), meth)
    wide["pin_overround"] = inv_y + inv_n
    return wide


def load_player_index(min_date: str) -> pd.DataFrame:
    """Index des joueurs ayant joué (tous gamelogs disponibles) avec clés de matching."""
    cols = ["gameDate", "gameId", "playerId", "name", "team"]
    frames = [pd.read_parquet(os.path.join(GAMELOG_DIR, f), columns=cols)
              for f in sorted(os.listdir(GAMELOG_DIR)) if f.endswith(".parquet")]
    idx = pd.concat(frames, ignore_index=True)
    idx = idx[idx.gameDate >= pd.Timestamp(min_date)].copy()
    idx["date"] = idx["gameDate"].dt.strftime("%Y-%m-%d")
    idx["full"] = idx["name"].map(norm_full)
    idx["drop"] = idx["name"].map(norm_drop)
    idx["last"] = idx["full"].str.split().str[-1]
    idx["init_last"] = idx["full"].str[0] + " " + idx["last"]
    return idx


def match_players(long: pd.DataFrame, idx: pd.DataFrame) -> pd.DataFrame:
    """Associe chaque joueur coté à un playerId.

    Ordre : nom complet exact > nom sans non-ASCII > initiale + nom > nom de famille seul,
    toujours restreint aux deux équipes du match et accepté seulement si unique.
    """
    by_key = {k: g for k, g in idx.groupby(["date", "team"])}
    empty = idx.iloc[:0]
    res = []
    cand = long[["date", "home", "away", "player_norm", "player_drop"]].drop_duplicates()
    for date, home, away, pn, pdrop in cand.itertuples(index=False):
        pool = pd.concat([by_key.get((date, home), empty), by_key.get((date, away), empty)])
        parts = pn.split()
        # Suffixe d'équipe ajouté par certains books pour les homonymes ("sebastian aho car")
        if len(parts) > 2 and parts[-1] in (home.lower(), away.lower()):
            team_hint = parts[-1].upper()
            parts = parts[:-1]
            pool = pool[pool["team"] == team_hint]
        if pool.empty or not parts:
            continue
        pn_c = " ".join(parts)
        hit: Optional[pd.Series] = None
        for col, key in (("full", pn_c), ("drop", pdrop), ("init_last", f"{pn_c[0]} {parts[-1]}"), ("last", parts[-1])):
            m = pool[pool[col] == key]
            if len(m) == 1:
                hit = m.iloc[0]
                break
        if hit is None:
            # Dernier recours : similarité de chaîne, acceptée seulement si unique et nette
            scores = pool["full"].map(lambda f: difflib.SequenceMatcher(None, f, pn_c).ratio())
            best = scores[scores >= 0.85]
            if len(best) == 1:
                hit = pool.loc[best.index[0]]
        if hit is not None:
            res.append((date, home, away, pn, int(hit.playerId), int(hit.gameId), hit.team))
    return pd.DataFrame(res, columns=["date", "home", "away", "player_norm", "playerId", "gameId", "team"])


def main() -> None:
    print("[1/3] Parsing du cache The Odds API...")
    long = parse_long()
    long.to_parquet(os.path.join(ODDS_DIR, "odds_long.parquet"), index=False)
    print(f"      {len(long):,} cotes | {long.date.min()} -> {long.date.max()} | books: {long.book.nunique()}")

    print("[2/3] Rattachement aux playerId via les gamelogs...")
    idx = load_player_index(long.date.min())
    m = match_players(long, idx)
    long = long.merge(m, on=["date", "home", "away", "player_norm"], how="left")
    for mk in ("but", "ast"):
        names = long[(long.market == mk)].drop_duplicates(["date", "home", "away", "player_norm"])
        print(f"      {mk}: joueurs cotés rattachés {names.playerId.notna().mean():.1%} "
              f"(le reste = joueurs non alignés / playoffs sans gamelog)")
    long = long.dropna(subset=["playerId"])
    long["playerId"] = long["playerId"].astype("int64")
    # Un même joueur peut apparaître sous 2 graphies selon le book : on garde 1 prix par (book, côté)
    long = long.drop_duplicates(["date", "home", "away", "book", "market", "side", "playerId"], keep="last")

    print("[3/3] Agrégation (Pinnacle no-vig, médiane soft)...")
    wide = to_wide(long)
    for mk in ("but", "ast"):
        w = wide[wide.market == mk]
        print(f"      {mk}: {len(w):,} lignes | no-vig Pinnacle {w.p_novig.notna().mean():.1%} | "
              f"soft dispo {w.soft_median.notna().mean():.1%} | overround Pinnacle moyen {w.pin_overround.mean():.3f}")
    assert not wide.duplicated(["date", "playerId", "market"]).any(), "doublons (date, playerId, marché)"
    wide.to_parquet(os.path.join(ODDS_DIR, "odds_wide.parquet"), index=False)
    print(f"      écrit : odds_wide.parquet ({len(wide):,} lignes)")


if __name__ == "__main__":
    main()
