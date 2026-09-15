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

def git_commit_and_push():
    """Push data.json to GitHub."""
    logger.info("Committing data.json to Git...")
    try:
        # Check if there are changes
        status = subprocess.run(["git", "status", "--porcelain", "dashboard/data.json"], cwd=_REPO_ROOT, capture_output=True, text=True)
        if not status.stdout.strip():
            logger.info("No changes in data.json. Skipping push.")
            return

        subprocess.run(["git", "add", "dashboard/data.json"], cwd=_REPO_ROOT, check=True)
        subprocess.run(["git", "commit", "-m", "chore: update dashboard data [skip ci]"], cwd=_REPO_ROOT, check=True)
        
        # Determine branch
        branch_proc = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=_REPO_ROOT, capture_output=True, text=True, check=True)
        branch = branch_proc.stdout.strip()
        
        # Determine remote name (default to origin, fallback to Analyse-Nhl if it exists)
        remote = "origin"
        remotes_proc = subprocess.run(["git", "remote"], cwd=_REPO_ROOT, capture_output=True, text=True)
        if "Analyse-Nhl" in remotes_proc.stdout.split():
            remote = "Analyse-Nhl"
            
        logger.info(f"Pushing to {remote} {branch}...")
        subprocess.run(["git", "push", remote, branch], cwd=_REPO_ROOT, check=True)
        logger.info("Successfully pushed to GitHub.")
    except subprocess.CalledProcessError as e:
        logger.error(f"Git command failed: {e.stderr if e.stderr else e}")
    except Exception as e:
        logger.error(f"Error during git push: {e}")

if __name__ == "__main__":
    export_data()
    git_commit_and_push()
