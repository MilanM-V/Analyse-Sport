"""
nhl/scripts/lstm_research.py — Recherche Quantitative : Deep Learning (LSTM) vs XGBoost

Objectif : 
Prendre la série temporelle brute des performances d'un joueur et voir si un RNN (LSTM)
peut capturer des patterns complexes de forme physique/confiance que XGBoost (qui utilise des moyennes) rate.
"""

import pandas as pd
import numpy as np
import os
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader, TensorDataset
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import train_test_split
import xgboost as xgb
import warnings
warnings.filterwarnings('ignore')

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_PATH = os.path.join(ROOT, "data", "historical_dataset.parquet")

SEQ_LENGTH = 5 # On regarde les 5 derniers matchs pour predire le 6eme
FEATURES = ['I_F_xGoals', 'I_F_shotsOnGoal', 'icetime', 'is_home', 'pp1', 'opp_xga_60']
TARGET = 'target_but_0_5'

class PlayerLSTM(nn.Module):
    def __init__(self, input_size, hidden_size=32, num_layers=1):
        super(PlayerLSTM, self).__init__()
        self.lstm = nn.LSTM(input_size, hidden_size, num_layers, batch_first=True)
        self.fc = nn.Linear(hidden_size, 1)
        self.sigmoid = nn.Sigmoid()

    def forward(self, x):
        out, _ = self.lstm(x)
        out = out[:, -1, :] # Prendre le dernier state de la sequence
        out = self.fc(out)
        return self.sigmoid(out)

def create_sequences(df):
    print("Creation des sequences temporelles...")
    X, y, X_flat = [], [], []
    
    # Remplir les Nans
    df[FEATURES] = df[FEATURES].fillna(0)
    
    for _, group in df.groupby('playerId'):
        group = group.sort_values('date')
        if len(group) < SEQ_LENGTH + 1:
            continue
            
        vals = group[FEATURES].values
        targets = group[TARGET].values
        
        for i in range(len(group) - SEQ_LENGTH):
            seq = vals[i : i + SEQ_LENGTH]
            target = targets[i + SEQ_LENGTH]
            
            # Pour XGBoost, on aplatit la sequence (ex: moyenne des 5 matchs)
            flat_features = np.mean(seq, axis=0)
            
            X.append(seq)
            y.append(target)
            X_flat.append(flat_features)
            
    return np.array(X), np.array(y), np.array(X_flat)

def run_research():
    print("--- RECHERCHE DEEP LEARNING (LSTM) vs XGBOOST ---")
    
    if not os.path.exists(DATA_PATH):
        print("Dataset introuvable.")
        return

    df = pd.read_parquet(DATA_PATH)
    # Prendre un echantillon pour la vitesse (2 saisons max)
    df = df[df['season'].isin([2022, 2023])]
    
    X, y, X_flat = create_sequences(df)
    print(f"Dataset : {len(X)} sequences generees.")
    
    # Train / Test split temporel (ou random pour ce POC)
    X_train, X_test, y_train, y_test, Xf_train, Xf_test = train_test_split(X, y, X_flat, test_size=0.2, random_state=42)
    
    # ==========================
    # 1. Baseline : XGBoost
    # ==========================
    print("\n--- Entrainement de la Baseline (XGBoost) ---")
    xgb_model = xgb.XGBClassifier(n_estimators=100, learning_rate=0.05, max_depth=3, eval_metric='logloss')
    xgb_model.fit(Xf_train, y_train)
    
    xgb_preds = xgb_model.predict_proba(Xf_test)[:, 1]
    xgb_auc = roc_auc_score(y_test, xgb_preds)
    print(f"-> AUC XGBoost (Moyennes lissees) : {xgb_auc:.4f}")
    
    # ==========================
    # 2. Deep Learning : LSTM
    # ==========================
    print("\n--- Entrainement du Deep Learning (LSTM) ---")
    
    X_train_t = torch.tensor(X_train, dtype=torch.float32)
    y_train_t = torch.tensor(y_train, dtype=torch.float32).view(-1, 1)
    X_test_t = torch.tensor(X_test, dtype=torch.float32)
    y_test_t = torch.tensor(y_test, dtype=torch.float32).view(-1, 1)
    
    dataset = TensorDataset(X_train_t, y_train_t)
    loader = DataLoader(dataset, batch_size=256, shuffle=True)
    
    model = PlayerLSTM(input_size=len(FEATURES), hidden_size=32)
    criterion = nn.BCELoss()
    optimizer = optim.Adam(model.parameters(), lr=0.01)
    
    epochs = 10
    for epoch in range(epochs):
        model.train()
        epoch_loss = 0
        for batch_X, batch_y in loader:
            optimizer.zero_grad()
            outputs = model(batch_X)
            loss = criterion(outputs, batch_y)
            loss.backward()
            optimizer.step()
            epoch_loss += loss.item()
            
    # Evaluation
    model.eval()
    with torch.no_grad():
        lstm_preds = model(X_test_t).numpy().flatten()
        
    lstm_auc = roc_auc_score(y_test, lstm_preds)
    print(f"-> AUC LSTM (Sequences temporelles) : {lstm_auc:.4f}")
    
    # ==========================
    # 3. Conclusion
    # ==========================
    print("\n--- CONCLUSION ---")
    diff = lstm_auc - xgb_auc
    if diff > 0.02:
        print(f"-> VICTOIRE DU DEEP LEARNING ! L'AUC est superieur de +{diff:.4f}. Cela justifie la complexite des reseaux de neurones.")
    else:
        print(f"-> LE DEEP LEARNING A ECHOUE A BATTRE XGBOOST SIGNIFICATIVEMENT (Diff: {diff:+.4f}).")
        print("=> Raison theorique : La variance dans le sport est trop forte. Lisser les stats (comme XGBoost) empeche l'overfitting. Les LSTM overfittent le bruit.")
        
if __name__ == "__main__":
    run_research()
