"""
scripts/calibrate_proxy.py — Le proxy de cote (médiane US × décote) colle-t-il aux cotes FR réelles ?

Source : picks de nhl/bot_database.db où l'utilisateur a saisi la cote réellement trouvée
(/pris <ref> <cote> [book]) ou signalé qu'aucun book FR n'atteignait la cote seuil (/skip).

Pour chaque marché × source du proxy (soft = médiane US, pinnacle = repli) :
- ratio cote_reelle / cote_proxy (médiane, IC 95 % bootstrap) ;
- décote suggérée = décote actuelle × ratio médian (à reporter À LA MAIN dans settings.toml
  [betting] exec_haircut / pin_haircut, puis relancer export_simulator_data.py) ;
- taux de picks « jouables » (cote FR ≥ cote seuil).

Usage:
    python nhl/scripts/calibrate_proxy.py [--min-obs 30]
"""
import argparse
import os
import sqlite3
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from nhl.config.settings import cfg  # noqa: E402

DB = os.path.join(ROOT, "nhl", "bot_database.db")
TABLES = {"but": "picks", "ast": "picks_assists"}


def load_decisions(db_path: str = DB) -> pd.DataFrame:
    """Picks en mode proxy ayant reçu une décision (/pris ou /skip)."""
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    parts = []
    try:
        for market, table in TABLES.items():
            cols = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
            if "pris" not in cols:
                continue
            q = (f"SELECT date, joueur, cote_proxy, cote_seuil, price_source, cote_reelle, book_reel, pris "
                 f"FROM {table} WHERE pris IS NOT NULL AND cote_proxy IS NOT NULL")
            d = pd.read_sql_query(q, conn)
            d["market"] = market
            parts.append(d)
    finally:
        conn.close()
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()


def bootstrap_median(x: np.ndarray, n: int = 2000, seed: int = 0) -> tuple:
    rng = np.random.default_rng(seed)
    meds = np.median(rng.choice(x, size=(n, len(x)), replace=True), axis=1)
    return float(np.percentile(meds, 2.5)), float(np.percentile(meds, 97.5))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-obs", type=int, default=30)
    a = ap.parse_args()
    df = load_decisions()
    if df.empty:
        print("Aucune décision enregistrée (/pris ou /skip) : rien à calibrer.")
        return
    haircut = {"soft": cfg.betting.exec_haircut, "pinnacle": cfg.betting.pin_haircut}
    print(f"{len(df)} décisions ({int((df.pris == 1).sum())} pris, {int((df.pris == 0).sum())} non pris)\n")
    for (market, src), g in df.groupby(["market", "price_source"]):
        taken = g[(g.pris == 1) & g.cote_reelle.notna()]
        playable = (taken.cote_reelle >= taken.cote_seuil).sum()
        print(f"[{market} / {src}] {len(g)} picks — jouables (cote FR ≥ seuil) : "
              f"{playable}/{len(g)} ({100 * playable / len(g):.0f} %)")
        if taken.empty:
            continue
        ratio = (taken.cote_reelle / taken.cote_proxy).to_numpy()
        lo, hi = bootstrap_median(ratio)
        med = float(np.median(ratio))
        sugg = haircut.get(src, 1.0) * med
        print(f"   cote réelle / proxy : médiane {med:.3f} (IC 95 % [{lo:.3f} ; {hi:.3f}], n={len(ratio)})")
        if len(ratio) >= a.min_obs:
            key = "exec_haircut" if src == "soft" else "pin_haircut"
            print(f"   → décote suggérée : {key} = {sugg:.3f} (actuelle {haircut.get(src)})")
        else:
            print(f"   → pas assez d'observations ({len(ratio)} < {a.min_obs}) pour recalibrer")
        books = taken.book_reel.dropna()
        if not books.empty:
            print("   books : " + ", ".join(f"{b}={n}" for b, n in books.value_counts().items()))


if __name__ == "__main__":
    main()
