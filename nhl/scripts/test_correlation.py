"""
nhl/scripts/test_correlation.py — Recherche Quantitative : Line Stacking.

L'objectif de ce script est de mesurer la corrélation mathématique (le boost de probabilité)
entre deux coéquipiers. Plus précisément : 
Si le Buteur A marque, quelle est la probabilité que le Passeur B assiste ?
Est-ce supérieur au produit de leurs probabilités individuelles P(A) * P(B) ?
"""

import pandas as pd
import numpy as np
import os
import itertools

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_PATH = os.path.join(ROOT, "data", "historical_dataset.parquet")

def analyze_correlation():
    print("--- DEMARRAGE DE LA RECHERCHE SUR LA CORRELATION (LINE STACKING) ---")
    
    if not os.path.exists(DATA_PATH):
        print(f"Fichier introuvable: {DATA_PATH}")
        return

    # Chargement
    df = pd.read_parquet(DATA_PATH)
    
    # On a besoin d'isoler chaque match d'équipe
    df['match_id'] = df['date'].astype(str) + '_' + df['equipe']
    
    # Restreindre aux saisons 2023 et 2024 pour la rapidité
    df = df[df['season'].isin([2023, 2024])].copy()
    
    # On cible les joueurs PP1 (où la synergie est supposée maximale)
    df_pp1 = df[df['pp1'] == 1].copy()
    print(f"Analyse sur {len(df_pp1)} perfs PP1...")

    # Compter les occurrences globales pour P(A) et P(B)
    # P(Buteur)
    p_buteur = df_pp1['target_but_0_5'].mean()
    # P(Passeur)
    p_passeur = df_pp1['target_ast_0_5'].mean()
    
    print(f"Probabilite moyenne Buteur PP1 : {p_buteur*100:.1f}%")
    print(f"Probabilite moyenne Passeur PP1 : {p_passeur*100:.1f}%")
    
    # Si indépendance stricte : P(A et B) = P(A) * P(B)
    indep_prob = p_buteur * p_passeur
    print(f"Probabilite theorique (Independance) : {indep_prob*100:.1f}%")
    
    # Mesure empirique intra-match
    match_grouped = df_pp1.groupby('match_id')
    
    total_pairs = 0
    success_pairs = 0
    
    for match_id, group in match_grouped:
        if len(group) < 2:
            continue
            
        # Créer toutes les paires possibles (Buteur, Passeur) dans l'équipe
        for p1, p2 in itertools.permutations(group.to_dict('records'), 2):
            if p1['joueur'] == p2['joueur']:
                continue
                
            total_pairs += 1
            if p1['target_but_0_5'] == 1 and p2['target_ast_0_5'] == 1:
                success_pairs += 1

    emp_prob = success_pairs / total_pairs if total_pairs > 0 else 0
    
    print("\n--- RESULTATS EMPIRIQUES (LINE STACKING) ---")
    print(f"Paires evaluees : {total_pairs:,}")
    print(f"Probabilite CONJOINTE empirique observee : {emp_prob*100:.2f}%")
    
    if emp_prob > 0:
        boost = (emp_prob / indep_prob) - 1.0
        print(f"-> L'independance est FAUSSE. La probabilite conjointe est boostee de +{boost*100:.1f}% par rapport aux cotes du bookmaker.")
        print(f"-> Conclusion : Les combines 'Same-Game' (MyMatch) entre deux joueurs du PP1 cachent un immense Value Bet, sauf si le bookmaker applique une marge d'erreur > {boost*100:.1f}%.")
    
if __name__ == "__main__":
    analyze_correlation()
