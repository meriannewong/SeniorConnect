import pandas as pd
import numpy as np
import joblib
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RESULTS_DIR = os.path.join(BASE_DIR, "..", "results")
SAVED_MODELS_DIR = os.path.join(BASE_DIR, "saved_models")

df = pd.read_csv(os.path.join(RESULTS_DIR, "processed_features.csv"))
splits_df = pd.read_csv(os.path.join(RESULTS_DIR, "subject_splits.csv"))
test_subjects = set(splits_df[splits_df["split"] == "test"]["subject_id"])
test_df = df[df["subject_id"].isin(test_subjects)]

numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
feature_cols = [c for c in numeric_cols if c != "label"]

scaler = joblib.load(os.path.join(SAVED_MODELS_DIR, "mlp_scaler.pkl"))
X_test_scaled = scaler.transform(test_df[feature_cols].values).astype(np.float32)
y_test = test_df["label"].values.astype(np.int64)
source_test = test_df["source"].values

out_path = os.path.join(SAVED_MODELS_DIR, "test_data.npz")
np.savez(out_path, X_test=X_test_scaled, y_test=y_test, source_test=source_test)
print("saved test data:", X_test_scaled.shape, "to", out_path)
