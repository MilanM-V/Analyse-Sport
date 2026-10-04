import os
import sqlite3
import json
import logging
import subprocess
from datetime import datetime, timezone

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("Exporter")

# Paths
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_SCRIPT_DIR)
PORTFOLIO_DB = os.path.join(_REPO_ROOT, "portfolio.db")
OUTPUT_JSON = os.path.join(_SCRIPT_DIR, "data.json")

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

def export_data():
    logger.info("Exporting data to JSON...")
    data = get_portfolio_data()
    
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    logger.info(f"Data exported successfully to {OUTPUT_JSON}.")

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
        with open(OUTPUT_JSON, encoding="utf-8") as src, open(os.path.join(repo_dir, "data.json"), "w", encoding="utf-8") as dst:
            dst.write(src.read())
        _git(["add", "data.json"], repo_dir)
        if not _git(["status", "--porcelain"], repo_dir).stdout.strip():
            logger.info("data.json inchangé : rien à publier.")
            return False
        _git(["-c", "user.name=BetEngine", "-c", "user.email=bot@betengine.local",
              "commit", "-q", "-m", "chore: update dashboard data"], repo_dir)
        _git(["push", "-q", "origin", f"HEAD:{branch}"], repo_dir)
        logger.info(f"data.json publié sur {branch}.")
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Publication du dashboard échouée ({' '.join(e.cmd)}) : {e.stderr}")
    except OSError as e:
        logger.error(f"Publication du dashboard échouée : {e}")
    return False


if __name__ == "__main__":
    export_data()
    git_commit_and_push()
