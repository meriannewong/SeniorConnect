import pandas as pd

splits = pd.read_csv("../results/subject_splits.csv")

print("columns:", list(splits.columns))
print()
print("split value counts:")
print(splits["split"].value_counts())
print()
print(splits.head(10))
