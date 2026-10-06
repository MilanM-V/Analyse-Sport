"""
dashboard/botdata.py — Lecture seule des bases du bot pour le dashboard (export JSON, exporter.py).

- nhl/bot_database.db : picks (buteur, passeur), joueurs évalués, contexte de match ;
- portfolio.db (racine) : paris pris et solde (bankroll()).

Les bases peuvent dater d'un ancien schéma : toute colonne absente est traitée comme vide.
"""
import logging
import os
import sqlite3
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger("NHL.Dashboard")
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NHL_DIR = os.path.join(REPO_ROOT, "nhl")
BOT_DB = os.path.join(NHL_DIR, "bot_database.db")
PORTFOLIO_DB = os.path.join(REPO_ROOT, "portfolio.db")
PICK_TABLES = {"but": ("picks", "but"), "ast": ("picks_assists", "assist")}
MARKET_LABEL = {"but": "Buteur", "ast": "Passeur"}


def _connect(path: str) -> Optional[sqlite3.Connection]:
    """Connexion en lecture seule (None si la base n'existe pas)."""
    if not os.path.exists(path):
        return None
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def list_tables(path: Optional[str] = None) -> Dict[str, int]:
    """{table: nombre de lignes} d'une base (défaut : base du bot)."""
    path = path or BOT_DB
    conn = _connect(path)
    if conn is None:
        return {}
    try:
        names = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        return {n: conn.execute(f'SELECT COUNT(*) FROM "{n}"').fetchone()[0] for n in names}
    finally:
        conn.close()


def read_table(table: str, path: Optional[str] = None, limit: Optional[int] = None) -> pd.DataFrame:
    """Contenu d'une table (les plus récentes d'abord si une colonne id existe)."""
    path = path or BOT_DB
    conn = _connect(path)
    if conn is None or table not in list_tables(path):
        return pd.DataFrame()
    try:
        cols = [r[1] for r in conn.execute(f'PRAGMA table_info("{table}")')]
        order = ' ORDER BY id DESC' if "id" in cols else ""
        lim = f" LIMIT {int(limit)}" if limit else ""
        return pd.read_sql_query(f'SELECT * FROM "{table}"{order}{lim}', conn)
    finally:
        conn.close()


def picks(path: Optional[str] = None) -> pd.DataFrame:
    """Tous les picks (buteur + passeur) dans un format commun, avec résultat et profit.

    Colonnes : date, marche, joueur, equipe, adversaire, cote (prise si /pris, sinon proxy),
    cote_seuil, mise, p_final, ev, resultat (1 gagné / 0 perdu / NaN en attente),
    statut ('gagné', 'perdu', 'en attente', 'annulé', 'non pris'), profit (U), ev_cloture,
    phase ('normal' ou 'early' = mode découverte).
    """
    path = path or BOT_DB
    frames = []
    for market, (table, col) in PICK_TABLES.items():
        df = read_table(table, path)
        if df.empty:
            continue
        g = lambda c, default=np.nan: df[c] if c in df else pd.Series(default, index=df.index)  # noqa: E731
        out = pd.DataFrame({
            "ref": [("B" if market == "but" else "A") + str(i) for i in g("id")],
            "date": g("date"), "marche": MARKET_LABEL[market], "joueur": g("joueur"), "equipe": g("equipe"),
            "adversaire": g("adversaire"), "cote_proxy": pd.to_numeric(g("cote"), errors="coerce"),
            "cote_reelle": pd.to_numeric(g("cote_reelle"), errors="coerce"),
            "cote_seuil": pd.to_numeric(g("cote_seuil"), errors="coerce"),
            "mise": pd.to_numeric(g("mise"), errors="coerce"), "p_final": pd.to_numeric(g("p_final"), errors="coerce"),
            "ev": pd.to_numeric(g("ev"), errors="coerce"), "pris": pd.to_numeric(g("pris"), errors="coerce"),
            "statut_db": g("statut", None), "resultat": pd.to_numeric(g(col), errors="coerce"),
            "closing_p_novig": pd.to_numeric(g("closing_p_novig"), errors="coerce"),
            "phase": g("phase", "normal"),
        })
        frames.append(out)
    if not frames:
        return pd.DataFrame()
    p = pd.concat(frames, ignore_index=True)
    p["cote"] = p["cote_reelle"].fillna(p["cote_proxy"])
    p["mise"] = p["mise"].fillna(1.0)
    p["phase"] = p["phase"].fillna("normal")
    p["statut"] = np.select(
        [p["statut_db"] == "void", p["pris"] == 0, p["resultat"] == 1, p["resultat"] == 0],
        ["annulé", "non pris", "gagné", "perdu"], default="en attente")
    played = p["statut"].isin(["gagné", "perdu"])
    p["profit"] = np.where(p["statut"] == "gagné", p["mise"] * (p["cote"] - 1),
                           np.where(p["statut"] == "perdu", -p["mise"], np.nan))
    p.loc[~played, "profit"] = np.nan
    p["ev_cloture"] = p["closing_p_novig"] * p["cote"] - 1
    p["date"] = pd.to_datetime(p["date"], errors="coerce")
    return p.drop(columns=["statut_db"]).sort_values(["date", "ref"], ascending=False).reset_index(drop=True)


def summary(p: pd.DataFrame) -> Dict[str, float]:
    """KPIs : paris joués, gain, ROI, réussite, EV de clôture moyenne, en attente."""
    played = p[p["statut"].isin(["gagné", "perdu"])] if not p.empty else p
    stake = float(played["mise"].sum()) if len(played) else 0.0
    profit = float(played["profit"].sum()) if len(played) else 0.0
    ev = p["ev_cloture"].dropna() if not p.empty else pd.Series(dtype=float)
    return {"n_picks": int(len(p)), "n_joues": int(len(played)), "mise": stake, "gain": profit,
            "roi": profit / stake if stake else float("nan"),
            "reussite": float((played["statut"] == "gagné").mean()) if len(played) else float("nan"),
            "en_attente": int((p["statut"] == "en attente").sum()) if not p.empty else 0,
            "ev_cloture": float(ev.mean()) if len(ev) else float("nan"), "n_ev_cloture": int(len(ev))}


def cumulative(p: pd.DataFrame) -> pd.DataFrame:
    """Gain cumulé par date (paris résolus), par marché et au total."""
    played = p[p["statut"].isin(["gagné", "perdu"])]
    if played.empty:
        return pd.DataFrame(columns=["date", "marche", "gain_cumule"])
    d = played.groupby(["date", "marche"])["profit"].sum().reset_index().sort_values("date")
    tot = played.groupby("date")["profit"].sum().reset_index().assign(marche="Total")
    d = pd.concat([d, tot], ignore_index=True).sort_values("date")
    d["gain_cumule"] = d.groupby("marche")["profit"].cumsum()
    return d


def portfolio(path: Optional[str] = None) -> pd.DataFrame:
    """Mouvements du portefeuille (paris, dépôts, retraits) avec solde reconstruit."""
    path = path or PORTFOLIO_DB
    df = read_table("portfolio", path)
    if df.empty:
        return df
    df = df.sort_values("id")
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df["solde"] = 100.0 + df["gain"].where(df["resolved"] >= 1, 0).fillna(0).cumsum()
    return df


INITIAL_BANKROLL = 100.0  # même valeur que shared.portfolio (non importé : lecture seule, sans effet de bord)
BANK_MARKET_LABEL = {"BUTEUR": "Buteur", "PASSEUR": "Passeur", "POINTEUR": "Points", "DEPOSIT": "Dépôt",
                     "WITHDRAW": "Retrait"}


def bankroll(path: Optional[str] = None) -> Dict[str, object]:
    """Évolution de la bankroll à partir du portefeuille (paris pris avec /pris, dépôts, retraits).

    Le solde suit la règle de shared.portfolio.Portfolio.get_balance : 100 U + somme des gains
    résolus. Les paris en attente ne bougent pas le solde (ils comptent dans l'exposition).
    La date d'un pari est celle de sa prise : la courbe range chaque résultat au jour du pari.

    Returns:
        {"initial", "balance", "pending": {n, stake}, "stats": {...}, "events": [...], "daily": [...]}
        (events et daily vides si la base n'existe pas).
    """
    df = read_table("portfolio", path or PORTFOLIO_DB)
    out: Dict[str, object] = {"initial": INITIAL_BANKROLL, "balance": INITIAL_BANKROLL,
                              "pending": {"n": 0, "stake": 0.0}, "stats": None, "events": [], "daily": []}
    if df.empty:
        return out
    df = df.sort_values("id").reset_index(drop=True)
    df["gain"] = pd.to_numeric(df["gain"], errors="coerce")
    df["mise"] = pd.to_numeric(df["mise"], errors="coerce").fillna(0.0)
    df["resolved"] = pd.to_numeric(df["resolved"], errors="coerce").fillna(0).astype(int)
    df["date"] = pd.to_datetime(df["timestamp"], errors="coerce").dt.strftime("%Y-%m-%d")
    cash = df["market"].isin(["DEPOSIT", "WITHDRAW"])
    df["statut"] = np.select(
        [df["market"] == "DEPOSIT", df["market"] == "WITHDRAW", df["resolved"] == 0, df["resolved"] == 2,
         df["gain"] > 0, df["gain"] < 0],
        ["dépôt", "retrait", "en attente", "annulé", "gagné", "perdu"], default="remboursé")
    settled = df["resolved"] >= 1
    df["solde"] = INITIAL_BANKROLL + df["gain"].where(settled, 0.0).fillna(0.0).cumsum()
    df["marche"] = df["market"].map(BANK_MARKET_LABEL).fillna(df["market"])
    bets = df[~cash]
    played = bets[bets["statut"].isin(["gagné", "perdu"])]
    pending = bets[bets["statut"] == "en attente"]
    curve = df["solde"]
    stake = float(played["mise"].sum())
    gain = float(played["gain"].sum())
    out.update(
        balance=float(curve.iloc[-1]),
        pending={"n": int(len(pending)), "stake": float(pending["mise"].sum())},
        stats={"n_paris": int(len(bets)), "n_joues": int(len(played)), "mise": stake, "gain_paris": gain,
               "roi": gain / stake if stake else float("nan"),
               "reussite": float((played["statut"] == "gagné").mean()) if len(played) else float("nan"),
               "cote_moyenne": float(played["cote"].mean()) if len(played) else float("nan"),
               "depots": float(df.loc[df["market"] == "DEPOSIT", "gain"].sum()),
               "retraits": float(abs(df.loc[df["market"] == "WITHDRAW", "gain"].sum())),
               "plus_haut": float(max(INITIAL_BANKROLL, curve.max())),
               "drawdown_max": float((curve.cummax().clip(lower=INITIAL_BANKROLL) - curve).max())},
        events=df[["id", "date", "sport", "player", "marche", "cote", "mise", "gain", "statut", "solde"]]
        .iloc[::-1].to_dict("records"),
    )
    day = df.groupby("date", sort=True).agg(solde=("solde", "last")).reset_index()
    flows = bets[bets["statut"].isin(["gagné", "perdu"])].groupby("date").agg(
        gain=("gain", "sum"), mise=("mise", "sum"), paris=("id", "size")).reset_index()
    day = day.merge(flows, on="date", how="left").fillna({"gain": 0.0, "mise": 0.0, "paris": 0})
    out["daily"] = day.to_dict("records")
    return out


def bot_players_for(player: str, path: Optional[str] = None) -> pd.DataFrame:
    """Historique des évaluations du bot pour un joueur (table players)."""
    path = path or BOT_DB
    conn = _connect(path)
    if conn is None:
        return pd.DataFrame()
    try:
        return pd.read_sql_query("SELECT * FROM players WHERE joueur = ? ORDER BY date DESC", conn, params=(player,))
    except (sqlite3.DatabaseError, pd.errors.DatabaseError) as e:  # table absente d'une ancienne base
        logger.warning(f"Évaluations du bot illisibles pour {player} : {e}")
        return pd.DataFrame()
    finally:
        conn.close()


def market_tables() -> List[str]:
    """Noms des tables de picks."""
    return [t for t, _ in PICK_TABLES.values()]
