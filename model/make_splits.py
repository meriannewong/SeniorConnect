import pandas as pd
from sklearn.model_selection import GroupShuffleSplit
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RESULTS_DIR = os.path.join(BASE_DIR, "..", "results")

df = pd.read_csv(os.path.join(RESULTS_DIR, "processed_features.csv"))
print("loaded", len(df), "rows,", df["subject_id"].nunique(), "subjects")

# step 1: split off test set (30%), held out until final evaluation
gss1 = GroupShuffleSplit(n_splits=1, test_size=0.3, random_state=42)
trainval_idx, test_idx = next(gss1.split(df, groups=df["subject_id"]))
trainval_df = df.iloc[trainval_idx]
test_df = df.iloc[test_idx]

# step 2: from the remaining 70%, split off a validation set (20% of that)
# used only to pick the MLP's decision threshold
gss2 = GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=42)
train_idx, val_idx = next(gss2.split(trainval_df, groups=trainval_df["subject_id"]))
train_df = trainval_df.iloc[train_idx]
val_df = trainval_df.iloc[val_idx]

print("train subjects:", train_df["subject_id"].nunique(), "rows:", len(train_df))
print("val subjects:", val_df["subject_id"].nunique(), "rows:", len(val_df))
print("test subjects:", test_df["subject_id"].nunique(), "rows:", len(test_df))

rows = []
for subj in train_df["subject_id"].unique():
    rows.append({"subject_id": subj, "split": "train"})
for subj in val_df["subject_id"].unique():
    rows.append({"subject_id": subj, "split": "val"})
for subj in test_df["subject_id"].unique():
    rows.append({"subject_id": subj, "split": "test"})

splits_df = pd.DataFrame(rows)
splits_df.to_csv(os.path.join(RESULTS_DIR, "subject_splits.csv"), index=False)
print("saved to", os.path.join(RESULTS_DIR, "subject_splits.csv"))
