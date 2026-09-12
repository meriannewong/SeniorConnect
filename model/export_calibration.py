import pandas as pd
import numpy as np
import joblib
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RESULTS_DIR = os.path.join(BASE_DIR, "..", "results")
SAVED_MODELS_DIR = os.path.join(BASE_DIR, "saved_models")

df = pd.read_csv(os.path.join(RESULTS_DIR, "processed_features.csv"))
splits_df = pd.read_csv(os.path.join(RESULTS_DIR, "subject_splits.csv"))
train_subjects = set(splits_df[splits_df["split"] == "train"]["subject_id"])
train_df = df[df["subject_id"].isin(train_subjects)]

numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
feature_cols = [c for c in numeric_cols if c != "label"]

scaler = joblib.load(os.path.join(SAVED_MODELS_DIR, "mlp_scaler.pkl"))
scaled = scaler.transform(train_df[feature_cols].values).astype(np.float32)

# a few hundred representative rows is enough for calibration
rng = np.random.default_rng(42)
idx = rng.choice(len(scaled), size=min(500, len(scaled)), replace=False)
calibration_data = scaled[idx]

out_path = os.path.join(SAVED_MODELS_DIR, "calibration_data.npy")
np.save(out_path, calibration_data)
print("saved calibration data:", calibration_data.shape, "to", out_path)
