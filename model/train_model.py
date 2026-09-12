import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, confusion_matrix
import joblib
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RESULTS_DIR = os.path.join(BASE_DIR, "..", "results")

print("reading from", os.path.join(RESULTS_DIR, "processed_features.csv"))
df = pd.read_csv(os.path.join(RESULTS_DIR, "processed_features.csv"))
print("loaded", len(df), "rows")

print(df["label"].value_counts())
print(df["source"].value_counts())

# train/test split now comes from make_splits.py, shared across all models
# so everyone compares on the exact same subjects (run make_splits.py first)
splits_df = pd.read_csv(os.path.join(RESULTS_DIR, "subject_splits.csv"))
train_subjects = set(splits_df[splits_df["split"] == "train"]["subject_id"])
test_subjects = set(splits_df[splits_df["split"] == "test"]["subject_id"])

train_df = df[df["subject_id"].isin(train_subjects)]
test_df = df[df["subject_id"].isin(test_subjects)]

print("train size:", len(train_df), "test size:", len(test_df))
print("train subjects:", train_df["subject_id"].nunique(), "test subjects:", test_df["subject_id"].nunique())

numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
feature_cols = [c for c in numeric_cols if c != "label"]
print("using", len(feature_cols), "features:", feature_cols)

X_train = train_df[feature_cols].values
y_train = train_df["label"].values
X_test = test_df[feature_cols].values
y_test = test_df["label"].values
source_test = test_df["source"].values

model = RandomForestClassifier(n_estimators=100, class_weight="balanced", random_state=42)
model.fit(X_train, y_train)

y_pred = model.predict(X_test)

print("accuracy:", (y_pred == y_test).mean())
print(classification_report(y_test, y_pred, target_names=["not fall", "fall"]))
print("confusion matrix:")
print(confusion_matrix(y_test, y_pred))

print("accuracy by data source:")
for src in df["source"].unique():
    mask = source_test == src
    if mask.sum() == 0:
        continue
    acc = (y_pred[mask] == y_test[mask]).mean()
    fall_mask = mask & (y_test == 1)
    recall = (y_pred[fall_mask] == 1).mean() if fall_mask.sum() > 0 else float("nan")
    print(f"  {src}: accuracy={acc}, n={mask.sum()}, fall_recall={recall}")

importances = pd.Series(model.feature_importances_, index=feature_cols).sort_values(ascending=False)
print("top 5 most important features:")
print(importances.head(5))

SAVED_MODELS_DIR = os.path.join(BASE_DIR, "saved_models")
os.makedirs(SAVED_MODELS_DIR, exist_ok=True)
joblib.dump(model, os.path.join(SAVED_MODELS_DIR, "fall_model.pkl"))
print("model saved to", os.path.join(SAVED_MODELS_DIR, "fall_model.pkl"))
