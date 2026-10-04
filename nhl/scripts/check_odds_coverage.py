"""
scripts/check_odds_coverage.py — Diagnostic : quels books cotent les props NHL dans The Odds API ?

Question clé pour la prod : les books FR où l'on parie (settings.toml [betting] exec_books)
cotent-ils les marchés buteur / passeur ? Sinon `nhl.core.odds.fetch_nhl_odds` ne renvoie aucune cote
d'exécution et le bot ne peut parier sur rien.

Coût : 1 crédit (liste des matchs) + ~4 crédits par match testé (1 par marché × région).
Les props ne sont souvent publiées que la veille / le jour du match : relancer à ce moment-là
si le rapport indique « aucune prop ».

Usage:
    python nhl/scripts/check_odds_coverage.py [--events 3]
"""
import argparse
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Tuple

import requests
from dotenv import load_dotenv

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
load_dotenv(os.path.join(ROOT, ".env"))

from nhl.config.settings import cfg  # noqa: E402

BASE = "https://api.the-odds-api.com/v4/sports/icehockey_nhl"
MARKETS = ["player_goal_scorer_anytime", "player_assists", "player_points", "player_shots_on_goal"]
REGIONS = "eu,fr,uk,us"
REPORT_DIR = os.path.join(ROOT, "nhl", "reports")


def api_get(path: str, **params) -> Tuple[object, str]:
    """Appel GET à The Odds API ; renvoie (json, crédits restants)."""
    params["apiKey"] = os.getenv("api_odds")
    r = requests.get(f"{BASE}{path}", params=params, timeout=20)
    remaining = r.headers.get("x-requests-remaining", "?")
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code} sur {path} : {r.text[:200]}")
    return r.json(), remaining


def upcoming_events(days: int = 7) -> List[dict]:
    events, _ = api_get("/events")
    horizon = datetime.now(timezone.utc) + timedelta(days=days)
    out = [e for e in events if datetime.fromisoformat(e["commence_time"].replace("Z", "+00:00")) <= horizon]
    return sorted(out, key=lambda e: e["commence_time"])


def event_coverage(event_id: str) -> Tuple[Dict[str, Counter], str]:
    """Nombre de cotes par (marché, book) pour un match."""
    data, remaining = api_get(f"/events/{event_id}/odds", regions=REGIONS, markets=",".join(MARKETS),
                              oddsFormat="decimal")
    cov: Dict[str, Counter] = defaultdict(Counter)
    for bm in data.get("bookmakers", []):
        for mk in bm.get("markets", []):
            cov[mk["key"]][bm["key"]] += len(mk.get("outcomes", []))
    return cov, remaining


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--events", type=int, default=3)
    a = ap.parse_args()
    if not os.getenv("api_odds"):
        sys.exit("Clé `api_odds` absente du .env")
    exec_books = list(getattr(cfg.betting, "exec_books", ["winamax_fr"]))
    events = upcoming_events()
    print(f"{len(events)} match(s) NHL dans les 7 prochains jours")
    total: Dict[str, Counter] = defaultdict(Counter)
    lines, remaining = [], "?"
    for e in events[:a.events]:
        cov, remaining = event_coverage(e["id"])
        label = f"{e['away_team']} @ {e['home_team']} ({e['commence_time']})"
        print(f"\n{label}")
        lines.append(f"\n### {label}\n")
        if not cov:
            print("  aucune prop cotée pour l'instant")
            lines.append("Aucune prop cotée pour l'instant.\n")
        for mk, books in cov.items():
            total[mk].update(books)
            txt = ", ".join(f"{b}={n}" for b, n in books.most_common())
            print(f"  {mk:28s} {txt}")
            lines.append(f"- `{mk}` : {txt}")

    all_books = sorted({b for c in total.values() for b in c})
    fr_found = sorted(b for b in all_books if b in exec_books)
    verdict = (f"Books d'exécution présents : {fr_found}" if fr_found else
               f"**AUCUN book d'exécution ({exec_books}) ne cote ces props** : en prod, aucune cote "
               "d'exécution → aucun pari possible via The Odds API.")
    if not total:
        verdict = "Aucune prop cotée sur les matchs testés (trop tôt ?). Relancer la veille d'un match."
    print(f"\n{verdict}\nCrédits restants : {remaining}")

    os.makedirs(REPORT_DIR, exist_ok=True)
    day = datetime.now().strftime("%Y-%m-%d")
    path = os.path.join(REPORT_DIR, f"odds_coverage_{day}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"# Couverture des props NHL — The Odds API ({day})\n\n")
        f.write(f"Régions demandées : `{REGIONS}`. Books d'exécution configurés : `{exec_books}`.\n\n")
        f.write(f"**Verdict :** {verdict}\n\nBooks vus : {', '.join(all_books) or 'aucun'}\n")
        f.write("\n".join(lines) + f"\n\nCrédits restants : {remaining}\n")
    print(f"écrit : {path}")


if __name__ == "__main__":
    main()
