import requests
import pandas as pd

# adjust this path if your results folder is somewhere else relative to here
RESULTS_PATH = "../results/processed_features.csv"

df = pd.read_csv(RESULTS_PATH)
# keep only numeric columns (auto-excludes label/source/subject_id and any
# other text/id columns like trial_id, whatever they happen to be named)
numeric_df = df.select_dtypes(include="number")
feature_cols = [c for c in numeric_df.columns if c != "label"]
print("using", len(feature_cols), "feature columns:", feature_cols)

sample_row = df.iloc[0]
raw_features = sample_row[feature_cols].tolist()
true_label = int(sample_row["label"])

print("sending raw features:", raw_features)
print("true label was:", true_label, "(1 = fall, 0 = no fall)")

response = requests.post("http://localhost:8000/predict", json={"features": raw_features})
print("status code:", response.status_code)
print("response:", response.json())

health = requests.get("http://localhost:8000/")
print("health check:", health.json())
