"""
nhl/scripts/test_injury_impact.py — Recherche Quantitative : Injury Impact (Defenseurs).

Objectif : 
1. Identifier le meilleur defenseur (Top ATOI) de chaque equipe par saison.
2. Isoler les matchs où ce defenseur est absent (blessure / scratch).
3. Comparer les Buts Encaisses (Goals Against) et Expected Goals Against (xGA) de l'equipe 
   avec et sans ce defenseur pour voir s'il y a une augmentation statistiquement exploitable.
"""

import pandas as pd
import numpy as np
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_PATH = os.path.join(ROOT, "data", "historical_dataset.parquet")

def analyze_injury_impact():
    print("--- DEMARRAGE RECHERCHE : IMPACT DES BLESSURES (DEFENSEURS ELITE) ---")
    
    if not os.path.exists(DATA_PATH):
        print(f"Fichier introuvable: {DATA_PATH}")
        return

    # Chargement
    df = pd.read_parquet(DATA_PATH)
    
    # Restreindre aux saisons 2023 et 2024 pour un echantillon recent
    df = df[df['season'].isin([2023, 2024])].copy()
    
    print("Calcul du temps de jeu moyen (ATOI) par joueur...")
    
    # Identifier les defenseurs (on suppose que les plus gros ATOI sont des defenseurs top pairing)
    # Dans notre dataset, on a 'atoi' (en minutes)
    season_stats = df.groupby(['season', 'equipe', 'joueur']).agg({
        'atoi': 'mean',
        'date': 'count' # nombre de matchs joues
    }).reset_index()
    
    # Filtrer les joueurs ayant joue au moins 20 matchs pour la solidite stat
    season_stats = season_stats[season_stats['date'] >= 20]
    
    # Trouver le Top 1 ATOI par equipe par saison
    idx = season_stats.groupby(['season', 'equipe'])['atoi'].idxmax()
    top_defenders = season_stats.loc[idx]
    
    print(f"Identifie {len(top_defenders)} defenseurs elites (Top ATOI par equipe par saison).")
    
    # Creer un set des (saison, equipe, date) complet
    all_team_games = df[['season', 'equipe', 'date']].drop_duplicates()
    
    results = []
    
    # Pour chaque saison-equipe
    for _, row in top_defenders.iterrows():
        s = row['season']
        t = row['equipe']
        elite_player = row['joueur']
        
        # Tous les matchs de l'equipe
        team_games = all_team_games[(all_team_games['season'] == s) & (all_team_games['equipe'] == t)]
        
        # Matchs joues par l'elite
        elite_games = df[(df['season'] == s) & (df['equipe'] == t) & (df['joueur'] == elite_player)]['date'].unique()
        
        team_games_with_elite = team_games[team_games['date'].isin(elite_games)]
        team_games_without_elite = team_games[~team_games['date'].isin(elite_games)]
        
        if len(team_games_without_elite) < 3:
            continue # Pas assez de matchs sans lui pour avoir une stat fiable
            
        # Maintenant, on calcule le 'ga_g' (Goals Against par match) moyen de l'equipe
        # Dans notre dataset, chaque ligne d'un joueur d'une equipe contient le ga_g de l'equipe pour ce match.
        # Donc on peut juste prendre la moyenne d'un seul joueur de l'equipe par match.
        
        def get_team_ga_xga(dates):
            games_df = df[(df['season'] == s) & (df['equipe'] == t) & (df['date'].isin(dates))]
            # Groupby date and take the first row for team-level stats (ga_g, hdca_g)
            team_stats = games_df.groupby('date').first()
            return team_stats['ga_g'].mean(), team_stats['hdca_g'].mean()
            
        ga_with, hdca_with = get_team_ga_xga(team_games_with_elite['date'])
        ga_without, hdca_without = get_team_ga_xga(team_games_without_elite['date'])
        
        results.append({
            'equipe': t,
            'joueur': elite_player,
            'matchs_sans': len(team_games_without_elite),
            'ga_avec': ga_with,
            'ga_sans': ga_without,
            'diff_ga': ga_without - ga_with
        })
        
    res_df = pd.DataFrame(results)
    
    if len(res_df) == 0:
        print("Pas assez de donnees de blessures.")
        return
        
    print("\n--- RESULTATS EMPIRIQUES (INJURY IMPACT) ---")
    avg_diff = res_df['diff_ga'].mean()
    print(f"Lorsqu'un Defenseur #1 est absent, l'equipe encaisse en moyenne : {avg_diff:+.2f} Buts/Match")
    
    print("\nTop 5 des pires impacts d'absence (les equipes qui sombrent sans leur star) :")
    top_impacts = res_df.sort_values('diff_ga', ascending=False).head(5)
    for _, r in top_impacts.iterrows():
        print(f"- {r['equipe']} sans {r['joueur']} ({r['matchs_sans']} matchs) : {r['ga_sans']:.2f} GA (vs {r['ga_avec']:.2f} GA habituellement) -> Diff: +{r['diff_ga']:.2f} GA")
        
    if avg_diff > 0.25:
        print(f"\n-> Conclusion : L'absence du Defenseur #1 augmente les buts encaisses de {avg_diff:+.2f}. C'est une feature MAJEURE à scraper chaque jour via RotoWire !")
    else:
        print(f"\n-> Conclusion : L'impact n'est pas assez fort au global (+{avg_diff:+.2f}). Mieux vaut utiliser l'absence du Gardien Titulaire.")

if __name__ == "__main__":
    analyze_injury_impact()
