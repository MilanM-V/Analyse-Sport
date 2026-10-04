"""
dash/api.py — Données NHL pour le dashboard (API publique api-web.nhle.com).

Deux couches :
- `get_json(path)` : seul point d'accès réseau (remplacé par des données de test dans tests/) ;
- fonctions de transformation pures (JSON -> DataFrame), testables sans réseau.
"""
import logging
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

import pandas as pd
import requests

logger = logging.getLogger("NHL.Dashboard")
BASE = "https://api-web.nhle.com/v1"
POSITIONS = {"C": "Centre", "L": "Ailier gauche", "R": "Ailier droit", "D": "Défenseur", "G": "Gardien"}


class NHLApiError(RuntimeError):
    """Réponse invalide de l'API NHL."""


def get_json(path: str, timeout: int = 20) -> Dict[str, Any]:
    """GET {BASE}/{path} -> JSON. Lève NHLApiError si l'API ne répond pas correctement."""
    try:
        r = requests.get(f"{BASE}/{path}", timeout=timeout)
    except requests.RequestException as e:
        raise NHLApiError(f"API NHL injoignable ({path}) : {e}") from e
    if r.status_code != 200:
        raise NHLApiError(f"API NHL {r.status_code} pour {path}")
    return r.json()


def _mmss(seconds: Optional[float]) -> str:
    """Secondes -> 'mm:ss' (temps de glace)."""
    if seconds is None or seconds != seconds:
        return ""
    return f"{int(seconds // 60)}:{int(round(seconds % 60)):02d}"


def _pct(x: Optional[float]) -> Optional[float]:
    """Fraction -> pourcentage arrondi (0.1667 -> 16.7)."""
    return None if x is None else round(100 * float(x), 1)


def _name(d: Optional[dict]) -> str:
    return (d or {}).get("default", "") if isinstance(d, dict) else str(d or "")


# ─────────────────────────────────────────────────────────────────────────────
# Classement, leaders, résultats, calendrier
# ─────────────────────────────────────────────────────────────────────────────
def standings(data: Dict[str, Any]) -> pd.DataFrame:
    """JSON `standings/now` -> une ligne par équipe."""
    rows = []
    for t in data.get("standings", []):
        rows.append({
            "Rang": t.get("leagueSequence"), "Équipe": _name(t.get("teamName")), "abbrev": _name(t.get("teamAbbrev")),
            "logo": t.get("teamLogo"), "Conférence": t.get("conferenceName"), "Division": t.get("divisionName"),
            "MJ": t.get("gamesPlayed"), "V": t.get("wins"), "D": t.get("losses"), "DP": t.get("otLosses"),
            "Pts": t.get("points"), "% Pts": t.get("pointPctg"), "BP": t.get("goalFor"), "BC": t.get("goalAgainst"),
            "Diff": t.get("goalDifferential"), "Série": f"{t.get('streakCode', '')}{t.get('streakCount', '')}",
            "10 derniers": f"{t.get('l10Wins', 0)}-{t.get('l10Losses', 0)}-{t.get('l10OtLosses', 0)}",
            "Domicile": f"{t.get('homeWins', 0)}-{t.get('homeLosses', 0)}-{t.get('homeOtLosses', 0)}",
            "Extérieur": f"{t.get('roadWins', 0)}-{t.get('roadLosses', 0)}-{t.get('roadOtLosses', 0)}",
        })
    return pd.DataFrame(rows).sort_values("Rang").reset_index(drop=True) if rows else pd.DataFrame()


def leaders(data: Dict[str, Any], category: str) -> pd.DataFrame:
    """JSON `skater-stats-leaders` -> classement d'une catégorie (goals, assists, points)."""
    rows = [{"Rang": i + 1, "playerId": p["id"],
             "Joueur": f"{_name(p.get('firstName'))} {_name(p.get('lastName'))}".strip(),
             "Équipe": p.get("teamAbbrev"), "Poste": POSITIONS.get(p.get("position"), p.get("position")),
             "Valeur": p.get("value"), "photo": p.get("headshot"), "logo": p.get("teamLogo")}
            for i, p in enumerate(data.get(category, []))]
    return pd.DataFrame(rows)


def scores(data: Dict[str, Any]) -> pd.DataFrame:
    """JSON `score/{date}` -> un match par ligne (score, tirs, état, buteurs)."""
    rows = []
    for g in data.get("games", []):
        h, a = g.get("homeTeam", {}), g.get("awayTeam", {})
        scorers = [f"{_name(x.get('name'))} ({x.get('teamAbbrev')})" for x in g.get("goals", []) or []]
        rows.append({"gameId": g.get("id"), "Début (UTC)": g.get("startTimeUTC"), "État": g.get("gameState"),
                     "Extérieur": a.get("abbrev"), "Score ext.": a.get("score"), "Score dom.": h.get("score"),
                     "Domicile": h.get("abbrev"), "Tirs ext.": a.get("sog"), "Tirs dom.": h.get("sog"),
                     "Fin": (g.get("gameOutcome") or {}).get("lastPeriodType", ""),
                     "logo_ext": a.get("logo"), "logo_dom": h.get("logo"), "Buteurs": ", ".join(scorers)})
    return pd.DataFrame(rows)


def schedule_week(data: Dict[str, Any]) -> pd.DataFrame:
    """JSON `schedule/{date}` -> les matchs de la semaine."""
    rows = []
    for day in data.get("gameWeek", []):
        for g in day.get("games", []):
            rows.append({"Date": day.get("date"), "gameId": g.get("id"), "Début (UTC)": g.get("startTimeUTC"),
                         "Extérieur": g.get("awayTeam", {}).get("abbrev"), "Domicile": g.get("homeTeam", {}).get("abbrev"),
                         "Score ext.": g.get("awayTeam", {}).get("score"), "Score dom.": g.get("homeTeam", {}).get("score"),
                         "État": g.get("gameState"), "Type": {1: "Présaison", 2: "Saison", 3: "Séries"}.get(g.get("gameType"), "")})
    return pd.DataFrame(rows)


def team_schedule(data: Dict[str, Any], team: str) -> pd.DataFrame:
    """JSON `club-schedule-season/{team}/{season}` -> matchs de l'équipe avec résultat."""
    rows = []
    for g in data.get("games", []):
        if g.get("gameType") != 2:
            continue
        h, a = g.get("homeTeam", {}), g.get("awayTeam", {})
        home = h.get("abbrev") == team
        gf, ga = (h.get("score"), a.get("score")) if home else (a.get("score"), h.get("score"))
        res = ""
        if gf is not None and ga is not None and g.get("gameState") in ("OFF", "FINAL"):
            res = "V" if gf > ga else ("DP" if (g.get("gameOutcome") or {}).get("lastPeriodType") in ("OT", "SO") else "D")
        rows.append({"Date": g.get("gameDate"), "Adversaire": a.get("abbrev") if home else h.get("abbrev"),
                     "Lieu": "Domicile" if home else "Extérieur", "BP": gf, "BC": ga, "Résultat": res,
                     "État": g.get("gameState")})
    return pd.DataFrame(rows)


# ─────────────────────────────────────────────────────────────────────────────
# Équipe et joueur
# ─────────────────────────────────────────────────────────────────────────────
def roster(data: Dict[str, Any]) -> pd.DataFrame:
    """JSON `roster/{team}/current` -> effectif avec poste en clair."""
    rows = []
    for group in ("forwards", "defensemen", "goalies"):
        for p in data.get(group, []):
            rows.append({"playerId": p.get("id"), "N°": p.get("sweaterNumber"),
                         "Joueur": f"{_name(p.get('firstName'))} {_name(p.get('lastName'))}".strip(),
                         "Poste": POSITIONS.get(p.get("positionCode"), p.get("positionCode")),
                         "code": p.get("positionCode"), "Tir": p.get("shootsCatches"),
                         "Taille (cm)": p.get("heightInCentimeters"), "Poids (kg)": p.get("weightInKilograms"),
                         "Naissance": p.get("birthDate"), "Pays": p.get("birthCountry"), "photo": p.get("headshot")})
    order = {"C": 0, "L": 1, "R": 2, "D": 3, "G": 4}
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    return df.sort_values(["code", "N°"], key=lambda s: s.map(order) if s.name == "code" else s).reset_index(drop=True)


def club_stats(data: Dict[str, Any]) -> Dict[str, pd.DataFrame]:
    """JSON `club-stats/{team}/now` -> {'skaters', 'goalies'}."""
    sk = [{"playerId": p.get("playerId"), "Joueur": f"{_name(p.get('firstName'))} {_name(p.get('lastName'))}".strip(),
           "Poste": POSITIONS.get(p.get("positionCode"), p.get("positionCode")), "MJ": p.get("gamesPlayed"),
           "B": p.get("goals"), "A": p.get("assists"), "Pts": p.get("points"), "+/-": p.get("plusMinus"),
           "Tirs": p.get("shots"), "% tir": _pct(p.get("shootingPctg")), "BAN": p.get("powerPlayGoals"),
           "TG moy.": _mmss(p.get("avgTimeOnIcePerGame"))} for p in data.get("skaters", [])]
    gk = [{"playerId": p.get("playerId"), "Gardien": f"{_name(p.get('firstName'))} {_name(p.get('lastName'))}".strip(),
           "MJ": p.get("gamesPlayed"), "V": p.get("wins"), "D": p.get("losses"), "% arrêts": p.get("savePercentage"),
           "Moy. buts contre": p.get("goalsAgainstAverage"), "Blanchissages": p.get("shutouts")}
          for p in data.get("goalies", [])]
    return {"skaters": pd.DataFrame(sk).sort_values("Pts", ascending=False) if sk else pd.DataFrame(),
            "goalies": pd.DataFrame(gk)}


def player_profile(data: Dict[str, Any]) -> Dict[str, Any]:
    """JSON `player/{id}/landing` -> fiche (identité) + historique NHL saison régulière par saison."""
    hist = []
    for s in data.get("seasonTotals", []):
        if s.get("leagueAbbrev") != "NHL" or s.get("gameTypeId") != 2:
            continue
        season = str(s.get("season"))
        hist.append({"Saison": f"{season[:4]}-{season[6:]}", "Équipe": _name(s.get("teamName")),
                     "MJ": s.get("gamesPlayed"), "B": s.get("goals"), "A": s.get("assists"), "Pts": s.get("points"),
                     "+/-": s.get("plusMinus"), "Tirs": s.get("shots"), "% tir": s.get("shootingPctg"),
                     "BAN": s.get("powerPlayGoals"), "TG moy.": s.get("avgToi"),
                     "% arrêts (G)": s.get("savePctg"), "Moy. contre (G)": s.get("goalsAgainstAvg")})
    h = pd.DataFrame(hist)
    if not h.empty:
        # Saison jouée dans deux équipes : une ligne par équipe, on ajoute le total de la saison
        h = h.groupby("Saison", as_index=False).agg({
            "Équipe": lambda x: " / ".join(dict.fromkeys(x)), "MJ": "sum", "B": "sum", "A": "sum", "Pts": "sum",
            "+/-": "sum", "Tirs": "sum", "BAN": "sum", "% tir": "mean", "TG moy.": "last",
            "% arrêts (G)": "mean", "Moy. contre (G)": "mean"})
        h["Pts / match"] = (h["Pts"] / h["MJ"].where(h["MJ"] > 0)).round(2)
    return {
        "id": data.get("playerId"), "nom": f"{_name(data.get('firstName'))} {_name(data.get('lastName'))}".strip(),
        "equipe": data.get("currentTeamAbbrev"), "equipe_nom": _name(data.get("fullTeamName")),
        "poste": POSITIONS.get(data.get("position"), data.get("position")), "numero": data.get("sweaterNumber"),
        "naissance": data.get("birthDate"), "lieu": f"{_name(data.get('birthCity'))}, {data.get('birthCountry', '')}",
        "taille": data.get("heightInCentimeters"), "poids": data.get("weightInKilograms"),
        "tir": data.get("shootsCatches"), "photo": data.get("headshot"), "logo": data.get("teamLogo"),
        "draft": data.get("draftDetails") or {}, "historique": h,
        "carriere": ((data.get("careerTotals") or {}).get("regularSeason") or {}),
    }


def player_gamelog(data: Dict[str, Any]) -> pd.DataFrame:
    """JSON `player/{id}/game-log/now` -> matchs de la saison en cours (le plus ancien en premier)."""
    rows = [{"Date": g.get("gameDate"), "Adversaire": g.get("opponentAbbrev"),
             "Lieu": "Dom." if g.get("homeRoadFlag") == "H" else "Ext.", "B": g.get("goals", 0),
             "A": g.get("assists", 0), "Pts": g.get("points", 0), "+/-": g.get("plusMinus", 0),
             "Tirs": g.get("shots", 0), "TG": g.get("toi"), "BAN": g.get("powerPlayGoals", 0)}
            for g in data.get("gameLog", [])]
    df = pd.DataFrame(rows)
    return df.sort_values("Date").reset_index(drop=True) if not df.empty else df


def season_id(today: Optional[date] = None) -> str:
    """Identifiant de saison NHL en cours, ex. '20262027' (bascule au 1er août)."""
    today = today or date.today()
    y = today.year if today.month >= 8 else today.year - 1
    return f"{y}{y + 1}"


def week_start(d: date) -> date:
    """Lundi de la semaine de `d`."""
    return d - timedelta(days=d.weekday())


TEAMS: List[str] = ["ANA", "BOS", "BUF", "CAR", "CBJ", "CGY", "CHI", "COL", "DAL", "DET", "EDM", "FLA", "LAK", "MIN",
                    "MTL", "NJD", "NSH", "NYI", "NYR", "OTT", "PHI", "PIT", "SEA", "SJS", "STL", "TBL", "TOR", "UTA",
                    "VAN", "VGK", "WPG", "WSH"]


def team_logo(abbrev: str) -> str:
    """URL du logo officiel d'une équipe."""
    return f"https://assets.nhle.com/logos/nhl/svg/{abbrev}_light.svg"
