import pandas as pd
import numpy as np
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import classification_report, confusion_matrix
import tensorflow as tf
from tensorflow import keras
import joblib
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RESULTS_DIR = os.path.join(BASE_DIR, "..", "results")

print("reading from", os.path.join(RESULTS_DIR, "processed_features.csv"))
df = pd.read_csv(os.path.join(RESULTS_DIR, "processed_features.csv"))

print(df["label"].value_counts())
print(df["source"].value_counts())

# three-way split from make_splits.py (run that first) - val is used to pick
# the decision threshold, test is only evaluated once at the end with that
# threshold fixed, so the final numbers aren't tuned on the test set itself
splits_df = pd.read_csv(os.path.join(RESULTS_DIR, "subject_splits.csv"))
train_subjects = set(splits_df[splits_df["split"] == "train"]["subject_id"])
val_subjects = set(splits_df[splits_df["split"] == "val"]["subject_id"])
test_subjects = set(splits_df[splits_df["split"] == "test"]["subject_id"])

train_df = df[df["subject_id"].isin(train_subjects)]
val_df = df[df["subject_id"].isin(val_subjects)]
test_df = df[df["subject_id"].isin(test_subjects)]

print("train size:", len(train_df), "val size:", len(val_df), "test size:", len(test_df))
print("train subjects:", train_df["subject_id"].nunique(),
      "val subjects:", val_df["subject_id"].nunique(),
      "test subjects:", test_df["subject_id"].nunique())

numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
feature_cols = [c for c in numeric_cols if c != "label"]
print("using", len(feature_cols), "features:", feature_cols)

X_train = train_df[feature_cols].values
y_train = train_df["label"].values
X_val = val_df[feature_cols].values
y_val = val_df["label"].values
X_test = test_df[feature_cols].values
y_test = test_df["label"].values
source_test = test_df["source"].values

# MLP needs scaled features (RF didn't care about this, neural nets do)
scaler = StandardScaler()
X_train = scaler.fit_transform(X_train)
X_val = scaler.transform(X_val)
X_test = scaler.transform(X_test)

model = keras.Sequential([
    keras.layers.Input(shape=(X_train.shape[1],)),
    keras.layers.Dense(32, activation="relu"),
    keras.layers.Dense(16, activation="relu"),
    keras.layers.Dense(1, activation="sigmoid"),
])

model.compile(optimizer="adam", loss="binary_crossentropy", metrics=["accuracy"])
model.summary()

# match RF's class_weight="balanced" so the comparison is fair -
# without this the MLP naturally favors the majority class (not fall, ~64%)
n_not_fall = (y_train == 0).sum()
n_fall = (y_train == 1).sum()
total = n_not_fall + n_fall
class_weight = {
    0: total / (2 * n_not_fall),
    1: total / (2 * n_fall),
}
print("class weights:", class_weight)

model.fit(
    X_train, y_train,
    epochs=30, batch_size=64, validation_split=0.1,
    class_weight=class_weight,
    verbose=1,
)

y_val_prob = model.predict(X_val).flatten()

print()
print("threshold sweep on VAL set (used to pick the threshold, not test)")
print(f"{'threshold':>10} {'accuracy':>10} {'fall_recall':>12} {'fall_precision':>15}")
for t in [0.5, 0.45, 0.4, 0.35, 0.3, 0.25, 0.2]:
    yp = (y_val_prob > t).astype(int)
    acc = (yp == y_val).mean()
    tp = ((yp == 1) & (y_val == 1)).sum()
    fp = ((yp == 1) & (y_val == 0)).sum()
    fn = ((yp == 0) & (y_val == 1)).sum()
    recall = tp / (tp + fn) if (tp + fn) > 0 else float("nan")
    precision = tp / (tp + fp) if (tp + fp) > 0 else float("nan")
    print(f"{t:>10} {acc:>10.4f} {recall:>12.4f} {precision:>15.4f}")

# pick the threshold here based on the val sweep printed above, then run once
# on test - do not re-tune this by looking at test results
FINAL_THRESHOLD = 0.35

y_pred_prob = model.predict(X_test)
y_pred = (y_pred_prob > FINAL_THRESHOLD).astype(int).flatten()

print()
print("FINAL test set results at threshold =", FINAL_THRESHOLD)

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

SAVED_MODELS_DIR = os.path.join(BASE_DIR, "saved_models")
os.makedirs(SAVED_MODELS_DIR, exist_ok=True)
model.save(os.path.join(SAVED_MODELS_DIR, "fall_mlp.keras"))
joblib.dump(scaler, os.path.join(SAVED_MODELS_DIR, "mlp_scaler.pkl"))
print("model saved to", os.path.join(SAVED_MODELS_DIR, "fall_mlp.keras"))
print("scaler saved to saved_models/mlp_scaler.pkl")
