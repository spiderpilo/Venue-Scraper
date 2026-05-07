"""
Train the TensorFlow incentive classifier using the company-provided JSON dataset.

Input:  data/processed/json_batches_combined_presplit.json
Output: models/incentive_model.keras
        models/labels.txt
        data/processed/company_training_dataset.csv
"""

import json
import os
import time
import numpy as np
import pandas as pd
import tensorflow as tf
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder

# ---------------------------------------------------------------------------
# 1. Paths
# ---------------------------------------------------------------------------
JSON_PATH   = "data/processed/json_batches_combined_presplit.json"
MODEL_PATH  = "models/incentive_model.keras"
LABELS_PATH = "models/labels.txt"
CSV_OUT     = "data/processed/company_training_dataset.csv"

os.makedirs("models", exist_ok=True)
os.makedirs("data/processed", exist_ok=True)

# ---------------------------------------------------------------------------
# 2. Map granular Incentive Category values → the 5 canonical model labels.
#    The company JSON uses specific subcategory names (e.g. "Early Entry",
#    "Group Booking") that we collapse into the labels the pipeline expects.
# ---------------------------------------------------------------------------
LABEL_MAP = {
    # Live Music
    "Live Music":           "Live Music",
    "Free Live Music":      "Live Music",
    "Live Music Nights":    "Live Music",
    "Summer Concert Series":"Live Music",
    "Free Concert Series":  "Live Music",
    "Free Concert Nights":  "Live Music",
    "Free Music":           "Live Music",
    "Live Music Happy Hour":"Live Music",

    # Happy Hour
    "Happy Hour":           "Happy Hour",
    "Happy Hour Show":      "Happy Hour",

    # Free  (giveaway / no-cost events)
    "Free Day":             "Free",
    "Free Hot Dog Day":     "Free",
    "Free Root Beer Float Day": "Free",
    "Free Events":          "Free",
    "Free Entertainment":   "Free",
    "Free Tour Day":        "Free",
    "Free Community Event": "Free",
    "Free Entry":           "Free",
    "Free Street Events":   "Free",
    "Free Show Entry":      "Free",
    "Slurpee Deal":         "Free",

    # Group Friendly
    "Group Booking":        "Group Friendly",
    "Group Discount":       "Group Friendly",
    "Group Rental":         "Group Friendly",
    "Group Tour":           "Group Friendly",
    "Group Deal":           "Group Friendly",
    "Group Dive":           "Group Friendly",
    "Group Charter":        "Group Friendly",
    "Family Deal":          "Group Friendly",

    # Discount  (time-based, bundle, or reduced-price deals)
    "Early Entry":          "Discount",
    "Early Entry + Drink":  "Discount",
    "Matinee Deal":         "Discount",
    "Early Bird Ticket":    "Discount",
    "Early Bird":           "Discount",
    "Early Bird Dinner":    "Discount",
    "Early Bird Dining":    "Discount",
    "Night Strike":         "Discount",
    "Night Strike + Food":  "Discount",
    "Discount Days":        "Discount",
    "Pay What You Can":     "Discount",
    "Lunch Special":        "Discount",
    "Lunch Bento":          "Discount",
    "Lunch Bowl Deal":      "Discount",
    "Lunch Combo":          "Discount",
    "Tasting Deal":         "Discount",
    "Twilight Ticket":      "Discount",
    "Twilight Deal":        "Discount",
    "Twilight Admission":   "Discount",
    "Combo Deal":           "Discount",
    "After Hours":          "Discount",
    "After 3 PM Deal":      "Discount",
    "Afternoon Deal":       "Discount",
    "Unlimited Bowling":    "Discount",
    "Unlimited Play":       "Discount",
    "Unlimited Jump":       "Discount",
    "Unlimited Play Package":"Discount",
    "Day Pass":             "Discount",
    "First Time Discount":  "Discount",
    "Military Discount":    "Discount",
    "Student Discount":     "Discount",
    "Taco Tuesday":         "Discount",
    "Ride Wristband":       "Discount",
    "Secret Menu Deal":     "Discount",
    "Hiking Deal":          "Discount",
    "Player Reward":        "Discount",
    "24-Hour Access":       "Discount",
}

# ---------------------------------------------------------------------------
# 3. Load the JSON file
# ---------------------------------------------------------------------------
print(f"\n[1/6] Loading JSON from {JSON_PATH} ...")
t0 = time.time()

with open(JSON_PATH, "r") as f:
    raw = json.load(f)

# Flatten if nested (handle both list-of-dicts and dict-of-lists)
if isinstance(raw, dict):
    rows = []
    for val in raw.values():
        if isinstance(val, list):
            rows.extend(val)
        else:
            rows.append(val)
else:
    rows = raw

print(f"  Raw records loaded: {len(rows)}  ({time.time() - t0:.2f}s)")

# ---------------------------------------------------------------------------
# 4. Convert to DataFrame; select and combine text fields
# ---------------------------------------------------------------------------
print(f"\n[2/6] Building and cleaning dataset ...")
t0 = time.time()

df = pd.DataFrame(rows)
rows_before = len(df)
print(f"  Rows before cleaning: {rows_before}")

# Helper to safely retrieve a column as strings (returns "" if absent)
def safe_col(frame, col):
    return frame[col].astype(str).str.strip() if col in frame.columns else pd.Series([""] * len(frame))

# Build the text input: primary signal first, then supporting context
df["text"] = (
    safe_col(df, "Full Incentive Description") + " " +
    safe_col(df, "Incentive Teaser")           + " " +
    safe_col(df, "Incentive Category")         + " " +
    safe_col(df, "Cuisine / Experience Category") + " " +
    safe_col(df, "Business Type")              + " " +
    safe_col(df, "Notes")
).str.replace(r"\s+", " ", regex=True).str.strip()

# Map granular category → canonical label (unmapped rows become NaN)
df["label"] = safe_col(df, "Incentive Category").map(LABEL_MAP)

# ---------------------------------------------------------------------------
# 5. Clean the dataset
# ---------------------------------------------------------------------------
# Drop rows with empty text
df = df[df["text"].str.len() > 0]

# Drop rows whose mapped label is null (unmapped category or originally missing)
df = df[df["label"].notna()]

# Drop placeholder / junk label values
junk = {"", "unknown", "needs extraction", "nan", "none"}
df = df[~df["label"].str.lower().isin(junk)]

# Strip whitespace on both columns
df["text"]  = df["text"].str.strip()
df["label"] = df["label"].str.strip()

# Remove exact duplicate (text, label) pairs
df = df.drop_duplicates(subset=["text", "label"])

# Cap at 2000 rows so training stays fast during development
df = df.head(2000)

print(f"  Rows after cleaning:  {len(df)}  (dropped {rows_before - len(df)} rows)  ({time.time() - t0:.2f}s)")

# ---------------------------------------------------------------------------
# 6. Print label distribution
# ---------------------------------------------------------------------------
print(f"\n[3/6] Label distribution:")
dist = df["label"].value_counts()
for label, count in dist.items():
    print(f"  {label:<20} {count}")

# ---------------------------------------------------------------------------
# 7. Encode labels as integers
# ---------------------------------------------------------------------------
le = LabelEncoder()
df["label_id"] = le.fit_transform(df["label"])
classes = list(le.classes_)

print(f"\n  Classes ({len(classes)}): {classes}")
print(f"  Total rows for training: {len(df)}")

# ---------------------------------------------------------------------------
# 8. Save the cleaned dataset for inspection / auditing
# ---------------------------------------------------------------------------
df[["text", "label"]].to_csv(CSV_OUT, index=False)
print(f"\n  Cleaned training data saved → {CSV_OUT}")

# ---------------------------------------------------------------------------
# 9. Train / test split  (stratified when possible)
# ---------------------------------------------------------------------------
print(f"\n[4/6] Splitting dataset ...")
X = df["text"].values
y = df["label_id"].values

try:
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )
    print("  Stratified split succeeded.")
except ValueError as e:
    print(f"  Stratify failed ({e}); falling back to random split.")
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42
    )

print(f"  Train: {len(X_train)}  |  Test: {len(X_test)}")

# Convert to plain Python string lists so TensorFlow accepts them
X_train = [str(x) for x in X_train]
X_test  = [str(x) for x in X_test]

# Ensure labels are int32 numpy arrays
y_train = np.array(y_train, dtype="int32")
y_test  = np.array(y_test,  dtype="int32")

# Build tf.data datasets for clean batching
train_ds = tf.data.Dataset.from_tensor_slices((X_train, y_train)).batch(8)
test_ds  = tf.data.Dataset.from_tensor_slices((X_test,  y_test )).batch(8)

# ---------------------------------------------------------------------------
# 10. Build the TensorFlow text classification model
# ---------------------------------------------------------------------------
print(f"\n[5/6] Building model and adapting vectorizer ...")
t0 = time.time()

VOCAB_SIZE  = 10_000
MAX_LEN     = 100
EMBED_DIM   = 64
NUM_CLASSES = len(classes)

# Adapt the vectorizer on training text only (no data leakage)
vectorizer = tf.keras.layers.TextVectorization(
    max_tokens=VOCAB_SIZE,
    output_mode="int",
    output_sequence_length=MAX_LEN,
)
text_only_ds = train_ds.map(lambda text, label: text)
vectorizer.adapt(text_only_ds)
print(f"  Vectorizer adapted  ({time.time() - t0:.2f}s)")

model = tf.keras.Sequential([
    vectorizer,
    tf.keras.layers.Embedding(VOCAB_SIZE, EMBED_DIM, mask_zero=True),
    tf.keras.layers.GlobalAveragePooling1D(),
    tf.keras.layers.Dense(64, activation="relu"),
    tf.keras.layers.Dropout(0.3),
    tf.keras.layers.Dense(NUM_CLASSES, activation="softmax"),
])

model.compile(
    optimizer="adam",
    loss="sparse_categorical_crossentropy",
    metrics=["accuracy"],
)

model.summary()

# ---------------------------------------------------------------------------
# 11. Train
# ---------------------------------------------------------------------------
print(f"\n[6/6] Training model (20 epochs) ...\n")
t0 = time.time()

model.fit(train_ds, epochs=20, validation_data=test_ds)

print(f"\n  Training complete  ({time.time() - t0:.2f}s)")

# ---------------------------------------------------------------------------
# 12. Evaluate and print final accuracy
# ---------------------------------------------------------------------------
loss, accuracy = model.evaluate(test_ds, verbose=0)
print(f"\nFinal test accuracy: {accuracy:.4f}  |  loss: {loss:.4f}")

# ---------------------------------------------------------------------------
# 13. Save model and labels
# ---------------------------------------------------------------------------
model.save(MODEL_PATH)
print(f"Model saved → {MODEL_PATH}")

with open(LABELS_PATH, "w") as f:
    f.write("\n".join(classes))
print(f"Labels saved → {LABELS_PATH}")
print(f"\nLabels: {classes}")
print("\nDone.")
