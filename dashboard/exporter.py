"""
dashboard/exporter.py — Données du dashboard Vercel (site statique dashboard/), publiées chaque soir.

Fichiers écrits dans dashboard/ puis poussés sur la branche `dashboard-data` :
- data.json : portefeuille (format historique, gardé pour compatibilité) ;
- bot.json  : picks, KPIs (mode normal et mode découverte), gain cumulé, projection simulée, bankroll ;
- db.json   : toutes les tables des bases du bot (lecture seule, lignes les plus récentes).
"""
import os
import sqlite3
import json
import logging
import math
import subprocess
from datetime import datetime, timezone
from typing import Any, Dict, List

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("Exporter")

# Paths
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_SCRIPT_DIR)
PORTFOLIO_DB = os.path.join(_REPO_ROOT, "portfolio.db")
OUTPUT_JSON = os.path.join(_SCRIPT_DIR, "data.json")
BOT_JSON = os.path.join(_SCRIPT_DIR, "bot.json")
DB_JSON = os.path.join(_SCRIPT_DIR, "db.json")
SCENARIOS_JSON = os.path.join(_REPO_ROOT, "nhl", "reports", "config_scenarios.json")
DB_MAX_ROWS = 3000  # par table (les plus récentes) : garde db.json léger pour le navigateur

def get_portfolio_data():
    if not os.path.exists(PORTFOLIO_DB):
        return {"error": "portfolio.db not found"}
        
    conn = sqlite3.connect(PORTFOLIO_DB)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    # All bets
    c.execute("SELECT * FROM portfolio ORDER BY timestamp DESC")
    all_bets = [dict(row) for row in c.fetchall()]
    
    # Calculate KPIs
    initial_bankroll = 100.0
    current_balance = initial_bankroll
    
    resolved_bets = [b for b in all_bets if b['resolved'] == 1]
    pending_bets = [b for b in all_bets if b['resolved'] == 0]
    
    total_profit = sum(b['gain'] for b in resolved_bets if b['gain'] is not None)
    current_balance += total_profit
    
    wins = len([b for b in resolved_bets if b['gain'] > 0])
    losses = len([b for b in resolved_bets if b['gain'] < 0])
    total_resolved = wins + losses
    winrate = (wins / total_resolved * 100) if total_resolved > 0 else 0.0
    
    total_staked = sum(b['mise'] for b in resolved_bets if b['mise'] is not None)
    roi = (total_profit / total_staked * 100) if total_staked > 0 else 0.0
    
    # Evolution (Group by Day)
    evolution_data = []
    current_sim_balance = initial_bankroll
    
    # Sort resolved bets by oldest first to calculate chart
    resolved_bets_asc = sorted(resolved_bets, key=lambda x: x['timestamp'])
    
    # Seed with initial balance on first date if available
    if resolved_bets_asc:
        first_date = resolved_bets_asc[0]['timestamp'].split(" ")[0]
        # We start the chart slightly before the first bet
        evolution_data.append({"date": first_date + " 00:00:00", "balance": current_sim_balance})
        
    for bet in resolved_bets_asc:
        current_sim_balance += bet['gain']
        evolution_data.append({
            "date": bet['timestamp'],
            "balance": current_sim_balance
        })
    
    conn.close()
    
    return {
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "kpis": {
            "current_balance": round(current_balance, 2),
            "total_profit": round(total_profit, 2),
            "winrate": round(winrate, 1),
            "roi": round(roi, 1),
            "total_bets": total_resolved,
            "pending_exposure": sum(b['mise'] for b in pending_bets)
        },
        "pending_bets": pending_bets,
        "history": resolved_bets, # Newest first
        "evolution": evolution_data
    }

def _clean(v: Any) -> Any:
    """Valeur sérialisable en JSON strict (NaN/inf -> null, dates -> texte ISO)."""
    if v is None:
        return None
    if hasattr(v, "item"):  # scalaires numpy
        v = v.item()
    if isinstance(v, float) and not math.isfinite(v):
        return None
    if hasattr(v, "isoformat"):
        return v.isoformat()
    return v


def _records(df) -> List[Dict[str, Any]]:
    return [{k: _clean(v) for k, v in row.items()} for row in df.to_dict("records")]


def get_bot_data() -> Dict[str, Any]:
    """Contenu de bot.json : picks, KPIs, gain cumulé, détail par marché, projection simulée, bankroll."""
    from dashboard import botdata
    from nhl.config.settings import cfg
    p = botdata.picks()
    out: Dict[str, Any] = {
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "mode": {"paper": bool(cfg.mode.paper_trading), "go_live_min_bets": int(getattr(cfg.mode, "go_live_min_bets", 300)),
                 "strategy": "Équilibré, 1 pari / match"},
        "early": {k: _clean(getattr(cfg.early_season, k)) for k in ("enabled", "ev_min", "stake_mult")}
        if hasattr(cfg, "early_season") else None,
        "picks": [], "summary": None, "summary_early": None, "cumulative": [], "by_market": [], "projection": None,
        "bankroll": None,
    }
    bank = botdata.bankroll()
    out["bankroll"] = {"initial": _clean(bank["initial"]), "balance": _clean(bank["balance"]),
                       "pending": {k: _clean(v) for k, v in bank["pending"].items()},
                       "stats": {k: _clean(v) for k, v in bank["stats"].items()} if bank["stats"] else None,
                       "events": [{k: _clean(v) for k, v in r.items()} for r in bank["events"]],
                       "daily": [{k: _clean(v) for k, v in r.items()} for r in bank["daily"]]}
    if not p.empty:
        q = p.copy()
        q["date"] = q["date"].dt.strftime("%Y-%m-%d")
        out["picks"] = _records(q)
        normal, early = p[p["phase"] != "early"], p[p["phase"] == "early"]
        out["summary"] = {k: _clean(v) for k, v in botdata.summary(normal).items()} if len(normal) else None
        out["summary_early"] = {k: _clean(v) for k, v in botdata.summary(early).items()} if len(early) else None
        cum = botdata.cumulative(p)
        if not cum.empty:
            cum["date"] = cum["date"].dt.strftime("%Y-%m-%d")
            out["cumulative"] = _records(cum[["date", "marche", "gain_cumule"]])
        played = p[p["statut"].isin(["gagné", "perdu"])]
        if len(played):
            by = played.groupby("marche").agg(paris=("ref", "size"), gain=("profit", "sum"), mise=("mise", "sum")).reset_index()
            by["roi"] = by["gain"] / by["mise"]
            out["by_market"] = _records(by)
    if os.path.exists(SCENARIOS_JSON):
        with open(SCENARIOS_JSON, encoding="utf-8") as f:
            sc = json.load(f).get("scenarios", {}).get("actuelle")
        if sc:
            keep = ("n", "per_game", "profit_season", "roi", "max_dd", "ev_pin")
            out["projection"] = {k: {m: _clean(sc[k].get(m)) for m in keep} for k in ("val", "ctl")}
    return out


def get_db_data() -> Dict[str, Any]:
    """Contenu de db.json : {base: {table: {columns, rows, total}}} (colonnes *_json exclues)."""
    from dashboard import botdata
    out: Dict[str, Any] = {}
    for name, path in (("bot_database.db", botdata.BOT_DB), ("portfolio.db", botdata.PORTFOLIO_DB)):
        tables = {}
        for table, total in botdata.list_tables(path).items():
            df = botdata.read_table(table, path, limit=DB_MAX_ROWS)
            df = df[[c for c in df.columns if not c.endswith("_json")]]
            tables[table] = {"columns": list(df.columns), "total": int(total),
                             "rows": [[_clean(v) for v in r] for r in df.itertuples(index=False, name=None)]}
        out[name] = tables
    return out


def _write(path: str, data: Dict[str, Any]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def export_data():
    logger.info("Exporting data to JSON...")
    data = get_portfolio_data()
    
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    _write(BOT_JSON, get_bot_data())
    _write(DB_JSON, get_db_data())

    logger.info(f"Data exported successfully to {_SCRIPT_DIR} (data.json, bot.json, db.json).")

DASHBOARD_BRANCH = "dashboard-data"


def _git(args: list, cwd: str) -> subprocess.CompletedProcess:
    """Commande git qui lève CalledProcessError avec stderr en cas d'échec."""
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True)


def _remote_url() -> str:
    """URL du remote du dépôt de code (Analyse-Nhl prioritaire, sinon origin)."""
    remotes = _git(["remote"], _REPO_ROOT).stdout.split()
    remote = "Analyse-Nhl" if "Analyse-Nhl" in remotes else "origin"
    return _git(["remote", "get-url", remote], _REPO_ROOT).stdout.strip()


def git_commit_and_push(repo_dir: str = None, remote_url: str = None, branch: str = DASHBOARD_BRANCH) -> bool:
    """Publie data.json sur une branche dédiée, via un clone SÉPARÉ du dépôt de code.

    Avant (audit 2026-10-04) : le bot committait dans le dépôt que le watchdog réinitialise
    (`git reset --hard`) ; un conflit pouvait bloquer le déploiement ou perdre l'export.

    Args:
        repo_dir: clone de publication (défaut : env DASHBOARD_REPO_DIR, sinon ../bet2-dashboard).
        remote_url: dépôt distant (défaut : celui du dépôt de code).
        branch: branche de publication.

    Returns:
        True si un commit a été poussé.
    """
    repo_dir = repo_dir or os.getenv("DASHBOARD_REPO_DIR") or os.path.join(os.path.dirname(_REPO_ROOT), "bet2-dashboard")
    try:
        remote_url = remote_url or _remote_url()
        if not os.path.isdir(os.path.join(repo_dir, ".git")):
            logger.info(f"Création du clone de publication {repo_dir} ({branch})...")
            os.makedirs(repo_dir, exist_ok=True)
            _git(["init", "-q"], repo_dir)
            _git(["remote", "add", "origin", remote_url], repo_dir)
            exists = _git(["ls-remote", "--heads", "origin", branch], repo_dir).stdout.strip()
            if exists:
                _git(["fetch", "-q", "origin", branch], repo_dir)
                _git(["checkout", "-q", "-b", branch, f"origin/{branch}"], repo_dir)
            else:
                _git(["checkout", "-q", "--orphan", branch], repo_dir)
        else:
            _git(["fetch", "-q", "origin", branch], repo_dir)
            _git(["reset", "-q", "--hard", f"origin/{branch}"], repo_dir)
        names = []
        for path in (OUTPUT_JSON, BOT_JSON, DB_JSON):
            if not os.path.exists(path):
                continue
            with open(path, encoding="utf-8") as src, open(os.path.join(repo_dir, os.path.basename(path)), "w", encoding="utf-8") as dst:
                dst.write(src.read())
            names.append(os.path.basename(path))
        _git(["add", *names], repo_dir)
        if not _git(["status", "--porcelain"], repo_dir).stdout.strip():
            logger.info("Données du dashboard inchangées : rien à publier.")
            return False
        _git(["-c", "user.name=BetEngine", "-c", "user.email=bot@betengine.local",
              "commit", "-q", "-m", "chore: update dashboard data"], repo_dir)
        _git(["push", "-q", "origin", f"HEAD:{branch}"], repo_dir)
        logger.info(f"Données du dashboard publiées sur {branch} ({', '.join(names)}).")
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Publication du dashboard échouée ({' '.join(e.cmd)}) : {e.stderr}")
    except OSError as e:
        logger.error(f"Publication du dashboard échouée : {e}")
    return False


if __name__ == "__main__":
    import sys
    if _REPO_ROOT not in sys.path:
        sys.path.insert(0, _REPO_ROOT)
    export_data()
    git_commit_and_push()
