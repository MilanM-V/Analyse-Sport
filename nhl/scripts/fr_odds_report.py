"""
scripts/fr_odds_report.py — Bilan des vraies cotes des books français (table book_odds).

À lancer après 2 à 3 semaines de collecte (plan du 2026-10-04) :
1. ratio de chaque book à la médiane US et à Pinnacle « Oui », par marché et tranche de cote :
   base pour recalibrer la cote estimée du backtest (exec_haircut, audit P0-1) ;
2. part des lignes où le meilleur prix français dépasse le prix juste Pinnacle (Shin) ;
3. gain du meilleur book par rapport à Winamax seul (quand Winamax est lu) ;
4. stratégie « prix » (meilleur prix FR ≥ prix juste × 1,04) : résultats réels, mise plate.

Usage:
    python nhl/scripts/fr_odds_report.py [--db nhl/bot_database.db] [--moment vague] [--seuil 0.04]
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

from shared.devig import devig_yes  # noqa: E402

DB = os.path.join(ROOT, "nhl", "bot_database.db")
FR_BOOKS = ("winamax", "unibet", "betclic")
BANDS = [1, 2, 3, 4.5, 7, 100]
KEY = ["date", "market", "joueur"]
pd.set_option("display.width", 200)


def load(db: str, moment: str) -> pd.DataFrame:
    """Une ligne par (soirée, marché, joueur) : cote de chaque book, prix juste Pinnacle, résultat."""
    conn = sqlite3.connect(db)
    try:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        if not {"book_odds", "players"} <= tables:
            return pd.DataFrame()
        q = pd.read_sql("SELECT id, date, market, joueur, book, cote, cote_non FROM book_odds WHERE moment = ?",
                        conn, params=(moment,))
        res = pd.read_sql("SELECT id, date, joueur, but, assist FROM players WHERE but IS NOT NULL", conn)
    finally:
        conn.close()
    if q.empty:
        return q
    q = q.sort_values("id").groupby(KEY + ["book"], as_index=False).last()  # dernière vague de la soirée
    wide = q.pivot_table(index=KEY, columns="book", values="cote", aggfunc="last")
    pin_no = q[q["book"] == "pinnacle"].set_index(KEY)["cote_non"]
    wide = wide.join(pin_no.rename("pin_no")).reset_index()
    for col in ("pinnacle", "pin_no", "us_median", *FR_BOOKS):
        if col not in wide:
            wide[col] = np.nan
    wide["p_fair"] = devig_yes(wide["pinnacle"].to_numpy(float), wide["pin_no"].to_numpy(float), "shin")
    books = [b for b in FR_BOOKS if wide[b].notna().any()]
    wide["best_fr"] = wide[books].max(axis=1) if books else np.nan
    wide["best_book"] = wide[books].idxmax(axis=1) if books else None
    res = res.sort_values("id").groupby(["date", "joueur"], as_index=False).last()
    wide = wide.merge(res[["date", "joueur", "but", "assist"]], on=["date", "joueur"], how="left")
    stat = np.where(wide["market"] == "but", wide["but"], wide["assist"])
    wide["won"] = np.where(pd.isna(stat), np.nan, (pd.to_numeric(stat, errors="coerce") > 0).astype(float))
    return wide


def ratios(w: pd.DataFrame) -> None:
    print("\n== 1. Cote de chaque book / référence (médiane), par marché et tranche de la référence")
    for ref in ("us_median", "pinnacle"):
        rows = []
        for book in FR_BOOKS:
            x = w.dropna(subset=[book, ref])
            if x.empty:
                continue
            r = x[book] / x[ref]
            for (mk, band), g in r.groupby([x["market"], pd.cut(x[ref], BANDS)], observed=True):
                rows.append({"book": book, "marché": mk, "tranche": str(band), "n": len(g), "ratio": round(g.median(), 3)})
            for mk, g in r.groupby(x["market"]):
                rows.append({"book": book, "marché": mk, "tranche": "toutes", "n": len(g), "ratio": round(g.median(), 3)})
        print(f"\n-- référence {ref}")
        print(pd.DataFrame(rows).to_string(index=False) if rows else "   pas de données")


def value(w: pd.DataFrame) -> None:
    print("\n== 2. Meilleur prix français contre le prix juste Pinnacle (Shin)")
    x = w.dropna(subset=["best_fr", "p_fair"])
    if x.empty:
        print("   pas de ligne avec Pinnacle des deux côtés et une cote française")
        return
    ev = x["best_fr"] * x["p_fair"] - 1
    out = x.assign(ev=ev).groupby("market").agg(lignes=("ev", "size"), ev_moyenne=("ev", "mean"),
                                                 part_pos=("ev", lambda s: (s > 0).mean()),
                                                 part_4pct=("ev", lambda s: (s > 0.04).mean()),
                                                 part_8pct=("ev", lambda s: (s > 0.08).mean()))
    print(out.round(3).to_string())
    print("   meilleur book quand EV > 0 :", x.loc[ev > 0, "best_book"].value_counts().to_dict())


def best_vs_winamax(w: pd.DataFrame) -> None:
    print("\n== 3. Gain du meilleur book par rapport à Winamax seul")
    x = w.dropna(subset=["winamax", "best_fr"])
    x = x[x[[b for b in FR_BOOKS]].notna().sum(axis=1) >= 2]
    if x.empty:
        print("   Winamax n'est pas lu (VPS hors de France ?) ou un seul book par ligne")
        return
    gain = x["best_fr"] / x["winamax"] - 1
    print(f"   {len(x)} lignes : gain médian {gain.median():+.1%}, moyen {gain.mean():+.1%}, "
          f"Winamax meilleur dans {(gain == 0).mean():.0%} des cas")


def price_strategy(w: pd.DataFrame, seuil: float) -> None:
    print(f"\n== 4. Stratégie « prix » : meilleur prix FR ≥ prix juste × {1 + seuil:.2f}, mise plate")
    x = w.dropna(subset=["best_fr", "p_fair", "won"])
    x = x[x["best_fr"] * x["p_fair"] - 1 >= seuil]
    if x.empty:
        print("   aucun pari résolu pour l'instant")
        return
    profit = np.where(x["won"] == 1, x["best_fr"] - 1, -1.0)
    ev = x["best_fr"] * x["p_fair"] - 1
    sd = np.sqrt((x["p_fair"] * (1 - x["p_fair"]) * x["best_fr"] ** 2).sum())
    z = (profit.sum() - ev.sum()) / sd if sd else np.nan
    print(f"   {len(x)} paris ({x['date'].nunique()} soirées) : ROI réel {profit.mean():+.1%}, "
          f"EV attendue {ev.mean():+.1%}, réussite {x['won'].mean():.1%} contre {x['p_fair'].mean():.1%} attendu "
          f"(z = {z:+.2f} ; le ROI réel reste très bruité sur moins de quelques milliers de paris)")
    print("   par marché :", x.assign(p=profit).groupby("market")["p"].agg(["size", "mean"]).round(3).to_dict("index"))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=DB)
    ap.add_argument("--moment", default="vague", choices=["vague", "cloture"])
    ap.add_argument("--seuil", type=float, default=0.04, help="EV minimale contre le prix juste Pinnacle")
    a = ap.parse_args()
    w = load(a.db, a.moment)
    if w.empty:
        print(f"Aucune cote journalisée ({a.moment}) dans {a.db} : lancer le bot avec [fr_odds] enabled = true.")
        return
    books = {b: int(w[b].notna().sum()) for b in FR_BOOKS}
    print(f"{w['date'].nunique()} soirée(s), {len(w)} lignes joueur × marché ; cotes par book : {books}")
    ratios(w)
    value(w)
    best_vs_winamax(w)
    price_strategy(w, a.seuil)


if __name__ == "__main__":
    main()
