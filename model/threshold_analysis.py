import pandas as pd
import numpy as np
from tensorflow import keras
import joblib
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RESULTS_DIR = os.path.join(BASE_DIR, "..", "results")
SAVED_MODELS_DIR = os.path.join(BASE_DIR, "saved_models")

df = pd.read_csv(os.path.join(RESULTS_DIR, "processed_features.csv"))
test_subjects_df = pd.read_csv(os.path.join(RESULTS_DIR, "test_subjects.csv"))
test_subjects = set(test_subjects_df["subject_id"])
test_mask = df["subject_id"].isin(test_subjects)
test_df = df[test_mask]

numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
feature_cols = [c for c in numeric_cols if c != "label"]

X_test = test_df[feature_cols].values
y_test = test_df["label"].values
source_test = test_df["source"].values

model = keras.models.load_model(os.path.join(SAVED_MODELS_DIR, "fall_mlp.keras"))
scaler = joblib.load(os.path.join(SAVED_MODELS_DIR, "mlp_scaler.pkl"))

X_test_scaled = scaler.transform(X_test)
y_pred_prob = model.predict(X_test_scaled).flatten()

print("threshold sweep (lower threshold = catch more falls, more false alarms)")
print(f"{'threshold':>10} {'accuracy':>10} {'fall_recall':>12} {'fall_precision':>15}")
for threshold in [0.5, 0.45, 0.4, 0.35, 0.3, 0.25, 0.2]:
    y_pred = (y_pred_prob > threshold).astype(int)
    acc = (y_pred == y_test).mean()
    tp = ((y_pred == 1) & (y_test == 1)).sum()
    fp = ((y_pred == 1) & (y_test == 0)).sum()
    fn = ((y_pred == 0) & (y_test == 1)).sum()
    recall = tp / (tp + fn) if (tp + fn) > 0 else float("nan")
    precision = tp / (tp + fp) if (tp + fp) > 0 else float("nan")
    print(f"{threshold:>10} {acc:>10.4f} {recall:>12.4f} {precision:>15.4f}")

# also show the same sweep per data source, at threshold=0.35 as an example
print()
print("per-source breakdown at threshold=0.35:")
example_threshold = 0.35
y_pred = (y_pred_prob > example_threshold).astype(int)
for src in df["source"].unique():
    mask = source_test == src
    if mask.sum() == 0:
        continue
    acc = (y_pred[mask] == y_test[mask]).mean()
    fall_mask = mask & (y_test == 1)
    recall = (y_pred[fall_mask] == 1).mean() if fall_mask.sum() > 0 else float("nan")
    print(f"  {src}: accuracy={acc:.4f}, n={mask.sum()}, fall_recall={recall:.4f}")
    