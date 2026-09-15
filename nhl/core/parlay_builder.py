"""
nhl/core/parlay_builder.py — Générateur de combinés (Parlays) intelligents.

Apparie les meilleurs "Safe Picks" de la session en respectant :
1. Une corrélation nulle (joueurs dans des matchs différents).
2. Un EV combiné >= 0.30 et une Proba combinée >= 0.35.
"""

from typing import List, Dict, Any, Optional, Tuple

def build_best_parlay(picks_but: List[Dict[str, Any]], picks_ast: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """
    Trouve le meilleur combiné de 2 joueurs parmi la liste de paris.
    
    Returns:
        Dictionnaire contenant les infos du parlay ou None.
    """
    all_picks = picks_but + picks_ast
    
    if len(all_picks) < 2:
        return None
        
    # Trier par probabilité décroissante
    all_picks = sorted(all_picks, key=lambda x: x.get('Proba', 0), reverse=True)
    
    best_parlay = None
    best_ev = -1.0
    
    for i in range(len(all_picks)):
        for j in range(i + 1, len(all_picks)):
            p1 = all_picks[i]
            p2 = all_picks[j]
            
            # Vérifier que les cotes sont valides
            if not p1.get('Cote') or not p2.get('Cote'):
                continue
                
            # Règle stricte d'indépendance : Pas le même match
            # p1['Equipe'] et p1['Adversaire'] définissent le match de p1
            match_p1 = {p1['Equipe'], p1['Adversaire']}
            match_p2 = {p2['Equipe'], p2['Adversaire']}
            
            if match_p1.intersection(match_p2):
                # Ils jouent dans le même match (soit ensemble, soit l'un contre l'autre)
                continue
                
            p_joint = p1['Proba'] * p2['Proba']
            cote_joint = p1['Cote'] * p2['Cote']
            ev_joint = (p_joint * cote_joint) - 1.0
            
            # Seuils agressifs pour un parlay
            if p_joint >= 0.35 and ev_joint >= 0.30:
                if ev_joint > best_ev:
                    best_ev = ev_joint
                    best_parlay = {
                        "pick1": p1,
                        "pick2": p2,
                        "proba": p_joint,
                        "cote": cote_joint,
                        "ev": ev_joint
                    }
                    
    return best_parlay
