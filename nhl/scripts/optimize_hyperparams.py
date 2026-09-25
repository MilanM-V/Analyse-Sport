"""
scripts/optimize_hyperparams.py
Utilise Optuna pour optimiser les hyperparamètres de XGBoost, LightGBM et CatBoost 
spécifiquement pour nos datasets 'Buteur' et 'Passeur'.
"""
import os
import sys
import json
import optuna
import pandas as pd
import numpy as np
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import brier_score_loss

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, os.path.dirname(ROOT_DIR))

from xgboost import XGBClassifier
from lightgbm import LGBMClassifier
from catboost import CatBoostClassifier

# Import des features définies dans le script d'entraînement de prod
from nhl.scripts.train_production_models import FEATURES_BUT, FEATURES_AST

# On supprime temporairement les logs optuna massifs
optuna.logging.set_verbosity(optuna.logging.WARNING)

def objective(trial, algo_name, X, y):
    n_samples = len(y)
    n_pos = int(sum(y))
    n_neg = int(n_samples - n_pos)
    scale_pos = n_neg / max(1, n_pos)
    
    tscv = TimeSeriesSplit(n_splits=3)
    
    if algo_name == 'XGBoost':
        params = {
            'n_estimators': trial.suggest_int('n_estimators', 50, 300),
            'max_depth': trial.suggest_int('max_depth', 2, 7),
            'learning_rate': trial.suggest_float('learning_rate', 0.01, 0.2, log=True),
            'subsample': trial.suggest_float('subsample', 0.5, 1.0),
            'colsample_bytree': trial.suggest_float('colsample_bytree', 0.5, 1.0),
            'scale_pos_weight': scale_pos,
            'eval_metric': 'logloss',
            'verbosity': 0,
            'n_jobs': -1
        }
        model = XGBClassifier(**params)
        
    elif algo_name == 'LightGBM':
        params = {
            'n_estimators': trial.suggest_int('n_estimators', 50, 300),
            'max_depth': trial.suggest_int('max_depth', 2, 7),
            'num_leaves': trial.suggest_int('num_leaves', 7, 127),
            'learning_rate': trial.suggest_float('learning_rate', 0.01, 0.2, log=True),
            'subsample': trial.suggest_float('subsample', 0.5, 1.0),
            'colsample_bytree': trial.suggest_float('colsample_bytree', 0.5, 1.0),
            'scale_pos_weight': scale_pos,
            'verbose': -1,
            'n_jobs': -1
        }
        model = LGBMClassifier(**params)
        
    elif algo_name == 'CatBoost':
        params = {
            'iterations': trial.suggest_int('iterations', 50, 300),
            'depth': trial.suggest_int('depth', 2, 7),
            'learning_rate': trial.suggest_float('learning_rate', 0.01, 0.2, log=True),
            'l2_leaf_reg': trial.suggest_float('l2_leaf_reg', 1, 10, log=True),
            'scale_pos_weight': scale_pos,
            'verbose': False,
            'thread_count': -1
        }
        model = CatBoostClassifier(**params)

    brier_scores = []
    
    for train_idx, val_idx in tscv.split(X):
        X_train, y_train = X[train_idx], y[train_idx]
        X_val, y_val = X[val_idx], y[val_idx]
        
        model.fit(X_train, y_train)
        
        # Calibration non nécessaire pendant Optuna (trop lent), 
        # on veut juste le meilleur pouvoir discriminant brut
        preds = model.predict_proba(X_val)[:, 1]
        
        brier = brier_score_loss(y_val, preds)
        brier_scores.append(brier)
        
    return np.mean(brier_scores)

def optimize_market(market_name, df, features, target_col, n_trials=30):
    print(f"\n--- Lancement de l'optimisation Optuna pour {market_name.upper()} ---")
    X = df[features].values
    y = df[target_col].values
    
    best_params_market = {}
    algos = ['LightGBM', 'XGBoost', 'CatBoost']
    
    for algo in algos:
        print(f"-> Optimisation de {algo}...")
        study = optuna.create_study(direction='minimize')
        study.optimize(lambda trial: objective(trial, algo, X, y), n_trials=n_trials)
        best_params_market[algo] = study.best_params
        print(f"   Meilleur Brier Score {algo}: {study.best_value:.4f}")
        
    return best_params_market

def main():
    parquet_path = os.path.join(ROOT_DIR, "data", "historical_dataset.parquet")
    print(f"Chargement des données : {parquet_path}")
    df = pd.read_parquet(parquet_path).fillna(0.0)
    
    if 'implied_prob' not in df.columns: df['implied_prob'] = 0.35
    if 'goalie_weakness' not in df.columns: df['goalie_weakness'] = 0.08
    
    df_but = df[df['position'] != 'D'].copy()
    
    # Run optimization (10 trials to be fast but useful)
    best_params_but = optimize_market('Buteur', df_but, FEATURES_BUT, 'target_but_0_5', n_trials=10)
    best_params_ast = optimize_market('Passeur', df, FEATURES_AST, 'target_ast_0_5', n_trials=10)
    
    final_dict = {
        'but_0_5': best_params_but,
        'ast_0_5': best_params_ast
    }
    
    cfg_path = os.path.join(ROOT_DIR, "config", "optimal_hyperparams.json")
    os.makedirs(os.path.dirname(cfg_path), exist_ok=True)
    with open(cfg_path, 'w', encoding='utf-8') as f:
        json.dump(final_dict, f, indent=4)
        
    print(f"\n[OK] Optimisation terminee ! Hyperparametres sauvegardes dans {cfg_path}")

if __name__ == "__main__":
    main()
