"""
scripts/parse_winamax_pages.py — Extrait les cotes joueurs de pages de match Winamax sauvegardées.

Entrée : fichiers .htm enregistrés depuis le navigateur (page d'un match NHL sur Winamax),
par défaut dans `nhl/cote historique winamax/` (dossier ignoré par git : les pages
contiennent le pseudo et le solde du compte).

Marchés extraits (cotes « 1 ou plus ») :
- `but` : section « Buteur » (nom, % des mises, cote) ;
- `ast` : « Passes décisives du joueur (paliers) », colonne « 1 ou plus » ;
- `pts` : « Points du joueur (paliers) », colonne « 1 ou plus ».

Chaque page est rattachée à son match via le calendrier de l'API NHL (affiche identique,
dernier match terminé avant la sauvegarde de la page).

Usage:
    python nhl/scripts/parse_winamax_pages.py [--dir "nhl/cote historique winamax"]
"""
import argparse
import glob
import os
import re
import sys
from datetime import datetime, timedelta
from html import unescape
from typing import Dict, List, Optional, Tuple

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from nhl.config.constants import TEAM_FULL_TO_ABBR  # noqa: E402
from nhl.core.fr_odds import clean_player  # noqa: E402  (source unique, partagée avec la lecture en direct)
from shared.odds_api import _norm  # noqa: E402

PAGES_DIR = os.path.join(ROOT, "nhl", "cote historique winamax")
OUT = os.path.join(ROOT, "nhl", "data", "odds", "winamax_snapshots.parquet")
ODD = re.compile(r"^\d+(,\d+)?$")
PCT = re.compile(r"^\d+%$")
END_MARKERS = ("Moins de sélections", "Plus de sélections")
_TEAM_IDX = {_norm(k): v for k, v in TEAM_FULL_TO_ABBR.items()}


def team_abbr(name: str) -> Optional[str]:
    """Nom d'équipe Winamax -> abréviation NHL (None si inconnu)."""
    return _TEAM_IDX.get(_norm(name))


def page_lines(html: str) -> List[str]:
    """Texte visible d'une page, une ligne par nœud texte non vide."""
    body = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html, flags=re.S)
    lines = (ln.strip() for ln in unescape(re.sub(r"<[^>]+>", "\n", body)).splitlines())
    return [ln for ln in lines if ln and not ln.startswith("'")]


def _odd(s: str) -> float:
    return float(s.replace(",", "."))


def parse_goalscorer(lines: List[str]) -> List[Tuple[str, float]]:
    """Section « Buteur » : triplets (nom, %, cote). S'arrête au premier nom répété.

    Sur certaines pages, une seconde liste sans titre (autre marché) suit directement :
    la répétition d'un nom en marque la fin.
    """
    if "Buteur" not in lines:
        return []
    k = lines.index("Buteur") + 1
    while k < len(lines) and lines[k] in ("?", "i"):
        k += 1
    out, seen = [], set()
    while k + 2 < len(lines) and PCT.match(lines[k + 1]) and ODD.match(lines[k + 2]):
        name = lines[k]
        if name in seen:
            break
        seen.add(name)
        out.append((name, _odd(lines[k + 2])))
        k += 3
    return out


def parse_ladder(lines: List[str], title: str, teams: Tuple[str, str]) -> List[Tuple[str, str, float]]:
    """Section à paliers (« 1 ou plus », « 2 ou plus »...) : (équipe, nom, cote 1+).

    Structure : en-têtes de colonnes, puis pour chaque équipe son nom, puis pour chaque
    joueur : nom, puis jusqu'à 3 paires (cote, %). Fin au bouton « Moins / Plus de
    sélections » ou au titre de section suivant.
    """
    idx = [n for n, ln in enumerate(lines) if ln.startswith(title)]
    if not idx:
        return []
    k = idx[0] + 1
    while k < len(lines) and (lines[k] in ("?", "i") or lines[k].endswith("ou plus")):
        k += 1
    out, team = [], None
    while k < len(lines):
        ln = lines[k]
        if ln in END_MARKERS:
            # Chaque bloc d'équipe finit par ce bouton ; on continue si l'autre équipe suit
            if k + 1 < len(lines) and lines[k + 1] in teams:
                k += 1
                continue
            break
        if ln in teams:
            team, k = ln, k + 1
            continue
        if ODD.match(ln) or PCT.match(ln):
            k += 1
            continue
        nxt = lines[k + 1] if k + 1 < len(lines) else ""
        if nxt in ("?", "i"):  # titre de la section suivante
            break
        if ODD.match(nxt) and team:
            out.append((team, ln, _odd(nxt)))
            k += 2
            continue
        k += 1
    return out


def parse_page(path: str) -> Dict:
    """Une page -> {'home', 'away', 'saved', 'rows': [(market, team, player, odds)]}."""
    lines = page_lines(open(path, encoding="utf-8", errors="replace").read())
    title = lines[0].split("|")[0].strip()
    home, away = [t.strip() for t in title.split(" - ", 1)]
    rows = [("but", None, n, o) for n, o in parse_goalscorer(lines)]
    for market, head in (("ast", "Passes décisives du joueur"), ("pts", "Points du joueur")):
        rows += [(market, t, n, o) for t, n, o in parse_ladder(lines, head, (home, away))]
    return {"home": home, "away": away, "saved": datetime.fromtimestamp(os.path.getmtime(path)),
            "file": os.path.basename(path), "rows": rows}


def nhl_schedule(start: str, end: str) -> pd.DataFrame:
    """Matchs (date, gameId, domicile, extérieur, état, début UTC) entre deux dates (API NHL)."""
    import requests
    games, day = [], pd.Timestamp(start)
    while day <= pd.Timestamp(end):
        r = requests.get(f"https://api-web.nhle.com/v1/schedule/{day.date()}", timeout=15)
        r.raise_for_status()
        for gw in r.json().get("gameWeek", []):
            for g in gw["games"]:
                games.append({"date": gw["date"], "gameId": int(g["id"]), "home": g["homeTeam"]["abbrev"],
                              "away": g["awayTeam"]["abbrev"], "state": g.get("gameState"),
                              "start_utc": g.get("startTimeUTC"), "game_type": g.get("gameType")})
        day += pd.Timedelta(days=7)
    return pd.DataFrame(games).drop_duplicates("gameId")


def build(pages_dir: str = PAGES_DIR) -> pd.DataFrame:
    """Extrait toutes les pages, les rattache aux matchs NHL et contrôle la cohérence."""
    pages = [parse_page(p) for p in sorted(glob.glob(os.path.join(pages_dir, "*.htm")))]
    if not pages:
        raise FileNotFoundError(f"Aucune page .htm dans {pages_dir}")
    saved_max = max(p["saved"] for p in pages)
    sched = nhl_schedule((saved_max - timedelta(days=30)).strftime("%Y-%m-%d"), saved_max.strftime("%Y-%m-%d"))
    sched = sched[sched["state"].isin(["OFF", "FINAL"])]
    recs, anomalies, seen = [], [], set()
    for p in pages:
        h, a = team_abbr(p["home"]), team_abbr(p["away"])
        m = sched[(sched.home == h) & (sched.away == a) & (pd.to_datetime(sched.start_utc).dt.tz_localize(None) < p["saved"])]
        if m.empty:
            anomalies.append(f"{p['file']} : match {p['home']} - {p['away']} introuvable dans le calendrier")
            continue
        g = m.sort_values("start_utc").iloc[-1]
        if g["gameId"] in seen:
            anomalies.append(f"{p['file']} : doublon du match {g['gameId']} ({h}-{a}) ignoré")
            continue
        seen.add(g["gameId"])
        for market, team, player, odds in p["rows"]:
            if not 1.01 <= odds <= 100:
                anomalies.append(f"{p['file']} : cote hors bornes {player} {market} {odds}")
                continue
            recs.append({"gameId": int(g["gameId"]), "date": g["date"], "start_utc": g["start_utc"],
                         "home": h, "away": a, "market": market,
                         "team": team_abbr(team) if team else None, "player": clean_player(player),
                         "player_raw": player, "winamax": odds})
    df = pd.DataFrame(recs)
    dup = df.duplicated(["gameId", "market", "player"], keep=False)
    if dup.any():
        anomalies.append(f"{int(dup.sum())} doublons (match, marché, joueur) : premier conservé")
        df = df.drop_duplicates(["gameId", "market", "player"])
    for (gid, mk), sub in df.groupby(["gameId", "market"]):
        if mk == "but":
            if not 30 <= len(sub) <= 50:
                anomalies.append(f"match {gid} but : {len(sub)} joueurs (attendu 30-50)")
            continue
        h, a = sub["home"].iloc[0], sub["away"].iloc[0]
        for tm in (h, a):
            n = int((sub["team"] == tm).sum())
            if not 15 <= n <= 25:
                anomalies.append(f"match {gid} {mk} {tm} : {n} joueurs (attendu 15-25)")
    df.attrs["anomalies"] = anomalies
    return df


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=PAGES_DIR)
    a = ap.parse_args()
    df = build(a.dir)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    df.to_parquet(OUT, index=False)
    print(f"{df.gameId.nunique()} matchs, {len(df)} cotes -> {OUT}")
    print(df.groupby("market").size().to_string())
    for x in df.attrs.get("anomalies", []):
        print("  ⚠️", x)


if __name__ == "__main__":
    main()
