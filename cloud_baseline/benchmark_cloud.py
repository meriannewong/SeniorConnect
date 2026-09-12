import time
import numpy as np
import pandas as pd
import requests

AZURE_URL = "https://fallmlp-mewong3.azurewebsites.net/predict"

# same source + same column-selection logic as test_local.py, so the
# exact same real feature row is used for both the local and cloud tests
RESULTS_PATH = "../results/processed_features.csv"

N_RUNS = 50    # fewer than the edge test - network calls are slower and noisier, 50 is plenty
N_WARMUP = 5   # a few extra warmup calls - this is where Azure's cold start happens, not timed

print("loading a raw feature row")
df = pd.read_csv(RESULTS_PATH)
numeric_df = df.select_dtypes(include="number")
feature_cols = [c for c in numeric_df.columns if c != "label"]
single_row = df.iloc[0][feature_cols].tolist()
payload = {"features": single_row}

print("warming up (", N_WARMUP, "requests, not timed)")
for _ in range(N_WARMUP):
    r = requests.post(AZURE_URL, json=payload, timeout=30)
    print("warmup response:", r.json())

print("timing", N_RUNS, "requests")
times_ms = []
for _ in range(N_RUNS):
    start = time.perf_counter()
    r = requests.post(AZURE_URL, json=payload, timeout=30)
    end = time.perf_counter()
    times_ms.append((end - start) * 1000)

times_ms = np.array(times_ms)

print()
print("cloud round-trip latency (ms), n =", N_RUNS)
print("mean:  ", round(times_ms.mean(), 3))
print("median:", round(np.median(times_ms), 3))
print("min:   ", round(times_ms.min(), 3))
print("max:   ", round(times_ms.max(), 3))
print("p90:   ", round(np.percentile(times_ms, 90), 3))
print("p96:   ", round(np.percentile(times_ms, 96), 3))
print("p99:   ", round(np.percentile(times_ms, 99), 3))
print()
print("compare directly to latency_test.py's numbers - this cloud number")
print("includes the full network round trip, the edge number doesn't")
