import sqlite3
import json
import numpy as np
import os
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error

DB_PATH = os.path.expanduser("~/Documents/RuView/_Domian/demo/data/pose_training.db")

con = sqlite3.connect(DB_PATH)
cur = con.cursor()
cur.execute("SELECT pos_x_m, pos_y_m, csi_features FROM pose_pairs")
rows = cur.fetchall()
con.close()

print(f"Total registros: {len(rows)}")


def extraer_features_15(node_features_list):
    """Vector fijo: 4 nodos x 15 features = 60 dims (ceros si falta nodo)"""
    todos = []
    for nf in node_features_list:
        f = nf.get('features', {})
        clf = nf.get('classification', {})
        row = [
            float(f.get('mean_rssi', 0)),
            float(f.get('variance', 0)),
            float(f.get('motion_band_power', 0)),
            float(f.get('breathing_band_power', 0)),
            float(f.get('dominant_freq_hz', 0)),
            float(f.get('change_points', 0)),
            float(f.get('spectral_power', 0)),
            float(nf.get('rssi_dbm', 0)),
            float(nf.get('last_seen_ms', 0)),
            float(nf.get('frame_rate_hz', 0)),
            1.0 if nf.get('stale') else 0.0,
            1.0 if clf.get('presence') else 0.0,
            float(clf.get('confidence', 0)),
            float(nf.get('node_id', 0)),
            0.0
        ]
        todos.append((int(nf.get('node_id', 0)), row))

    vec = [0.0] * (4 * 15)
    for node_id, row in todos:
        if 1 <= node_id <= 4:
            idx_base = (node_id - 1) * 15
            vec[idx_base:idx_base + 15] = row
    return vec


X, y = [], []
for pos_x, pos_y, csi_json in rows:
    try:
        node_features = json.loads(csi_json)
        if not node_features:
            continue
        features = extraer_features_15(node_features)
        X.append(features)
        y.append([pos_x, pos_y])
    except Exception:
        continue

X = np.array(X)
y = np.array(y)
print(f"Dataset final: {X.shape[0]} muestras, {X.shape[1]} features")
print(f"Target shape: {y.shape}")

if X.shape[0] < 20:
    print("⚠️  Muy pocas muestras para entrenar de forma confiable")

# ── Entrenamiento ────────────────────────────────────────────────
X_train, X_val, y_train, y_val = train_test_split(
    X, y, test_size=0.2, random_state=42
)

scaler = StandardScaler()
X_train_n = scaler.fit_transform(X_train)
X_val_n = scaler.transform(X_val)

modelo = RandomForestRegressor(
    n_estimators=200,
    max_depth=10,
    random_state=42,
    n_jobs=-1
)
modelo.fit(X_train_n, y_train)

pred = modelo.predict(X_val_n)
mae_x = mean_absolute_error(y_val[:, 0], pred[:, 0])
mae_y = mean_absolute_error(y_val[:, 1], pred[:, 1])

print(f"\nTrain: {len(X_train)} muestras")
print(f"Val:   {len(X_val)} muestras")
print(f"\nError promedio X: {mae_x:.2f} metros")
print(f"Error promedio Y: {mae_y:.2f} metros")
print(f"Error promedio total: {(mae_x + mae_y) / 2:.2f} metros")

print("\nEjemplos de predicción vs real:")
for i in range(min(8, len(y_val))):
    print(f"  Real: ({y_val[i][0]:.2f}, {y_val[i][1]:.2f}) → "
          f"Predicho: ({pred[i][0]:.2f}, {pred[i][1]:.2f})")

# ── Guardar modelo ───────────────────────────────────────────────
import pickle

MODEL_OUT = os.path.expanduser("~/Documents/RuView/_Domian/demo/models/pose_position_model.pkl")
with open(MODEL_OUT, "wb") as f:
    pickle.dump({"modelo": modelo, "scaler": scaler}, f)

print(f"\n✅ Modelo guardado en: {MODEL_OUT}")
