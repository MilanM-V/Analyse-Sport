"""
scripts/paper_quality.py — Qualité du moteur en paper trading : log-loss contre Pinnacle sur les joueurs évalués.

Lit la table `players` de la base du bot. Depuis le 2026-10-08, chaque joueur évalué y est
enregistré avec le no-vig Pinnacle et la probabilité finale de chaque marché, et son résultat
est résolu en fin de journée. Pour chaque marché, sur les candidats qui ont une probabilité du
modèle, une cote Pinnacle et un résultat :
  - Δ log-loss modèle − Pinnacle et mélange (probabilité finale) − Pinnacle, en millinats
    (négatif = mieux que Pinnacle), IC 95 % bootstrap par soirée ;
  - nombre de soirées et de lignes.
C'est la mesure retenue pour juger le moteur en paper trading : sur quelques centaines de
paris, le ROI dépend surtout de la chance (nhl/reports/COMBINAISON_PISTES_2026-10-08.md, §6).

Usage:
    python nhl/scripts/paper_quality.py                        # base du bot (nhl/bot_database.db)
    python nhl/scripts/paper_quality.py --since 2026-10-08 --db autre.db
"""
import argparse
import os
import sqlite3
import sys
from typing import Dict, Optional

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for p in (ROOT, os.path.join(ROOT, "nhl")):
    if p not in sys.path:
        sys.path.insert(0, p)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from nhl.scripts.engine_report import delta_ll  # noqa: E402

DEFAULT_DB = os.path.join(ROOT, "nhl", "bot_database.db")
MARKETS = {"but": ("score_but", "picked_but", "p_novig_but", "p_final_but", "but"),
           "ast": ("score_assist", "picked_assist", "p_novig_ast", "p_final_ast", "assist")}


def load_players(db: str, since: Optional[str] = None) -> pd.DataFrame:
    """Joueurs évalués (dernière ligne par soirée et par joueur : les vagues relancées sont dédoublonnées)."""
    conn = sqlite3.connect(db)
    try:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(players)")}
        if "p_novig_but" not in cols:
            return pd.DataFrame()
        df = pd.read_sql_query("SELECT * FROM players", conn)
    finally:
        conn.close()
    if since:
        df = df[df["date"] >= since]
    key = np.where(df["player_id"].notna(), df["player_id"].astype("Int64").astype(str), df["joueur"].astype(str))
    return df.assign(_k=key).sort_values("id").drop_duplicates(["date", "_k"], keep="last")


def quality(df: pd.DataFrame) -> Dict[str, Dict]:
    """Δ log-loss modèle / mélange contre Pinnacle, par marché."""
    out: Dict[str, Dict] = {}
    for mk, (p_col, cand, nv, fin, res) in MARKETS.items():
        d = df[(df[cand] == 1) & (df[p_col] > 0) & df[nv].notna() & df[res].notna()]
        if len(d) < 30:
            out[mk] = {"n": int(len(d))}
            continue
        y = (pd.to_numeric(d[res]) > 0).astype(int).to_numpy()
        out[mk] = {"n": int(len(d)), "nights": int(d["date"].nunique()),
                   "model_vs_pinnacle": delta_ll(y, d[p_col], d[nv], d["date"]),
                   "final_vs_pinnacle": delta_ll(y, d[fin].fillna(d[p_col]), d[nv], d["date"])}
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--since", default=None, help="première soirée (YYYY-MM-DD)")
    a = ap.parse_args()
    if not os.path.exists(a.db):
        print(f"Base introuvable : {a.db}")
        return
    df = load_players(a.db, a.since)
    if df.empty:
        print("Pas encore de no-vig Pinnacle dans la table players (journalisé depuis le 2026-10-08).")
        return
    for mk, r in quality(df).items():
        if "model_vs_pinnacle" not in r:
            print(f"{mk} : {r['n']} ligne(s) complète(s), trop peu pour conclure (≥ 30).")
            continue
        m, f = r["model_vs_pinnacle"], r["final_vs_pinnacle"]
        print(f"{mk} : {r['n']} lignes sur {r['nights']} soirées | modèle − Pinnacle {m['d_mnat']:+.2f} mnat "
              f"[{m['lo']:+.2f} ; {m['hi']:+.2f}] | mélange − Pinnacle {f['d_mnat']:+.2f} [{f['lo']:+.2f} ; {f['hi']:+.2f}]")
    print("Lecture : négatif = plus précis que Pinnacle ; fourchette entièrement sous 0 = avance réelle.")


if __name__ == "__main__":
    main()
