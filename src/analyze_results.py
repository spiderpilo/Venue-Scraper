import pandas as pd

df = pd.read_json("data/processed/venues.json")

print("Preview:")
print(df.head())

print("\n--- Unknown counts ---")
print((df == "Unknown").sum())

print("\n--- Incentive categories ---")
print(df["Incentive Category"].value_counts())