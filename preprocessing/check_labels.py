import pandas as pd

df = pd.read_csv("../results/processed_features.csv")
print(df.groupby(["source", "label"]).size())
