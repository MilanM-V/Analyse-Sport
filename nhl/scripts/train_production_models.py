"""
scripts/train_production_models.py
Entraîne les modèles NHLEnsembleClassifier pour Buteur et Passeur (Over 0.5)
en utilisant des features ciblées pour réduire le bruit, et les sauvegarde pour la production.
"""
import os
import sys
import joblib
import pandas as pd

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, os.path.dirname(ROOT_DIR))

from nhl.core.ensemble_model import NHLEnsembleClassifier

# Features réduites pour limiter le bruit (Data Leakage Fix & Feature Selection)
FEATURES_BUT = [
    'ixg_l10', 'sog_l10', 'atoi_l10', 'season_g', 'sog_x_atoi', 'ixg_x_hdcf',
    'ga_g', 'pp1', 'is_home', 'is_b2b', 'opp_is_b2b', 'opp_goalie_gsax_60',
    'consec_goals', 'ixg_x_ga', 'prior_g60', 'prior_sog60', 'prior_sh_pct',
    'implied_prob', 'goalie_weakness', 'is_top6', 'hot_streak_ixg', 'split_l10_g'
]

FEATURES_AST = [
    'hdcf_l10', 'atoi_l10', 'season_a', 'ixg_x_hdcf',
    'ga_g', 'hdca_g', 'pp1', 'is_home', 'is_b2b', 'opp_is_b2b', 'opp_goalie_gsax_60',
    'linemate_synergy', 'team_scoring_env', 'prior_a60',
    'implied_prob', 'goalie_weakness', 'is_top6', 'hot_streak_ixg', 'split_l10_g'
]

def train_models():
    parquet_path = os.path.join(ROOT_DIR, "data", "historical_dataset.parquet")
    print(f"Chargement des données : {parquet_path}")
    df = pd.read_parquet(parquet_path)
    
    # Remplacer les NaN par 0.0 au cas où
    df = df.fillna(0.0)

    # Assurer qu'implied_prob est disponible (si absent dans dataset direct)
    if 'implied_prob' not in df.columns:
        df['implied_prob'] = 0.35 # Valeur neutre
    if 'goalie_weakness' not in df.columns:
        df['goalie_weakness'] = 0.08
        
    models_dir = os.path.join(ROOT_DIR, "models")
    os.makedirs(models_dir, exist_ok=True)

    print(f"\n--- Entraînement Modèle BUTEUR (Over 0.5) ---")
    df_but = df[df['position'] != 'D'].copy()
    X_but = df_but[FEATURES_BUT].values
    y_but = df_but['target_but_0_5'].values
    
    print(f"Taille: {len(X_but)} (Positifs: {sum(y_but)}) | Features: {len(FEATURES_BUT)}")
    model_but = NHLEnsembleClassifier(market='but_0_5', mode='ensemble', n_splits=3)
    model_but.fit(X_but, y_but)
    
    dict_but = {
        'model': model_but,
        'features': FEATURES_BUT
    }
    path_but = os.path.join(models_dir, "ensemble_but.joblib")
    joblib.dump(dict_but, path_but)
    print(f"-> Sauvegardé dans {path_but}")

    print(f"\n--- Entraînement Modèle PASSEUR (Over 0.5) ---")
    df_ast = df.copy()
    X_ast = df_ast[FEATURES_AST].values
    y_ast = df_ast['target_ast_0_5'].values
    
    print(f"Taille: {len(X_ast)} (Positifs: {sum(y_ast)}) | Features: {len(FEATURES_AST)}")
    model_ast = NHLEnsembleClassifier(market='ast_0_5', mode='ensemble', n_splits=3)
    model_ast.fit(X_ast, y_ast)
    
    dict_ast = {
        'model': model_ast,
        'features': FEATURES_AST
    }
    path_ast = os.path.join(models_dir, "ensemble_ast.joblib")
    joblib.dump(dict_ast, path_ast)
    print(f"-> Sauvegardé dans {path_ast}")
    
    print("\n✅ Terminé avec succès.")

if __name__ == "__main__":
    train_models()
