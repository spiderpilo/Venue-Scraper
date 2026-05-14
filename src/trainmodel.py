import os
import json
import numpy as np
import pandas as pd
import tensorflow as tf
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder
from sklearn.utils.class_weight import compute_class_weight
from sklearn.metrics import classification_report

FILTERED_PATH = "data/processed/sentence_dataset_filtered.csv"
RAW_PATH      = "data/processed/sentence_dataset.csv"
COMPANY_PATH  = "data/processed/company_training_dataset.csv"
PRESPLIT_PATH = "data/processed/json_batches_combined_presplit.json"
MODEL_PATH    = "models/incentive_model.keras"
LABELS_PATH   = "models/labels.txt"

MAX_TOKENS = 15000
SEQ_LEN    = 80
EMBED_DIM  = 128
LSTM_UNITS = 64
EPOCHS     = 40
BATCH_SIZE = 16

# ── 8 expanded model labels ───────────────────────────────────────────────────
MODEL_LABELS = {
    "No Incentive", "Live Music", "Early Entry", "Group Booking",
    "Matinee Deal", "Happy Hour", "Free", "Discount",
}

# Fine-grained presplit categories → model label
PRESPLIT_MAP = {
    # Live Music
    "Live Music": "Live Music", "Free Live Music": "Live Music",
    "Live Music Nights": "Live Music", "Summer Concert Series": "Live Music",
    "Free Concert Series": "Live Music", "Free Concert Nights": "Live Music",
    "Free Entertainment": "Live Music", "Free Music": "Live Music",
    "Free Show Entry": "Live Music", "Happy Hour Show": "Live Music",
    "Live Music Happy Hour": "Live Music", "Free Street Events": "Live Music",
    # Early Entry
    "Early Entry": "Early Entry", "Early Entry + Drink": "Early Entry",
    # Group Booking
    "Group Booking": "Group Booking", "Group Discount": "Group Booking",
    "Group Rental": "Group Booking", "Group Tour": "Group Booking",
    "Group Dive": "Group Booking", "Group Deal": "Group Booking",
    "Group Charter": "Group Booking",
    # Matinee Deal
    "Matinee Deal": "Matinee Deal", "Twilight Ticket": "Matinee Deal",
    "Twilight Admission": "Matinee Deal", "Twilight Deal": "Matinee Deal",
    # Happy Hour
    "Happy Hour": "Happy Hour", "Taco Tuesday": "Happy Hour",
    "Lunch Special": "Happy Hour", "Lunch Bento": "Happy Hour",
    "Afternoon Deal": "Happy Hour", "Early Bird Dining": "Happy Hour",
    "Lunch Bowl Deal": "Happy Hour", "Lunch Combo": "Happy Hour",
    "Early Bird Dinner": "Happy Hour",
    # Free
    "Free Day": "Free", "Free Hot Dog Day": "Free",
    "Free Root Beer Float Day": "Free", "Pay What You Can": "Free",
    "Slurpee Deal": "Free", "Family Deal": "Free",
    "Free Events": "Free", "Free Community Event": "Free",
    "Free Tour Day": "Free", "Free Entry": "Free",
    # Discount
    "Early Bird Ticket": "Discount", "Early Bird": "Discount",
    "Combo Deal": "Discount", "Night Strike": "Discount",
    "Discount Days": "Discount", "Unlimited Bowling": "Discount",
    "Tasting Deal": "Discount", "Unlimited Play": "Discount",
    "After Hours": "Discount", "Player Reward": "Discount",
    "Day Pass": "Discount", "First Time Discount": "Discount",
    "24-Hour Access": "Discount", "Military Discount": "Discount",
    "After 3 PM Deal": "Discount", "Ride Wristband": "Discount",
    "Student Discount": "Discount", "Hiking Deal": "Discount",
    "Night Strike + Food": "Discount", "Unlimited Play Package": "Discount",
    "Secret Menu Deal": "Discount", "Unlimited Jump": "Discount",
}

# Old sentence_dataset labels → model label
OLD_LABEL_MAP = {
    "Free": "Free", "Discount": "Discount",
    "Group Friendly": "Group Booking",
    "Happy Hour": "Happy Hour", "Live Music": "Live Music",
}


def load_presplit_rows():
    with open(PRESPLIT_PATH) as f:
        records = json.load(f)
    rows = []
    for r in records:
        mapped = PRESPLIT_MAP.get(r.get("Incentive Category", ""))
        if not mapped:
            continue
        desc   = str(r.get("Full Incentive Description") or "").strip()
        teaser = str(r.get("Incentive Teaser") or "").strip()
        text   = desc if len(desc) >= len(teaser) else teaser
        if len(text) >= 10:
            rows.append({"text": text, "label": mapped})
    return pd.DataFrame(rows)


def load_no_incentive_rows():
    if not os.path.exists(RAW_PATH):
        return pd.DataFrame(columns=["text", "label"])
    df = pd.read_csv(RAW_PATH)
    ni = df[df["label"] == "No Incentive"][["sentence"]].rename(columns={"sentence": "text"})
    ni["label"] = "No Incentive"
    return ni[ni["text"].str.len() >= 10]


def load_combined_dataset():
    frames = []

    # Legacy filtered sentences — remap labels
    if os.path.exists(FILTERED_PATH):
        df = pd.read_csv(FILTERED_PATH)[["sentence", "label"]].rename(columns={"sentence": "text"})
        df["label"] = df["label"].map(OLD_LABEL_MAP)
        frames.append(df.dropna(subset=["label"]))

    # Company training data — remap labels
    if os.path.exists(COMPANY_PATH):
        df = pd.read_csv(COMPANY_PATH)[["text", "label"]]
        df["label"] = df["label"].map(OLD_LABEL_MAP)
        frames.append(df.dropna(subset=["label"]))

    frames.append(load_presplit_rows())
    frames.append(load_no_incentive_rows())

    combined = pd.concat(frames, ignore_index=True)
    combined = combined.dropna(subset=["text", "label"])
    combined = combined[combined["label"].isin(MODEL_LABELS)]
    combined["text"] = combined["text"].astype(str).str.strip()
    combined = combined[combined["text"].str.len() >= 10]
    return combined


def main():
    df = load_combined_dataset()

    print(f"Combined dataset: {len(df)} rows")
    print("Label distribution:")
    print(df["label"].value_counts().to_string())
    print()

    texts  = df["text"].tolist()
    labels = df["label"].tolist()

    label_encoder = LabelEncoder()
    y = label_encoder.fit_transform(labels).astype("int32")
    num_classes = len(label_encoder.classes_)
    print("Classes:", list(label_encoder.classes_))

    X_train, X_test, y_train, y_test = train_test_split(
        texts, y, test_size=0.2, random_state=42, stratify=y,
    )

    weights = compute_class_weight("balanced", classes=np.arange(num_classes), y=y_train)
    class_weight_dict = dict(enumerate(weights))
    print("Class weights:", {label_encoder.classes_[k]: round(v, 2) for k, v in class_weight_dict.items()})
    print()

    train_ds = tf.data.Dataset.from_tensor_slices((X_train, y_train)).batch(BATCH_SIZE)
    test_ds  = tf.data.Dataset.from_tensor_slices((X_test,  y_test )).batch(BATCH_SIZE)

    vectorizer = tf.keras.layers.TextVectorization(
        max_tokens=MAX_TOKENS, output_mode="int", output_sequence_length=SEQ_LEN,
    )
    vectorizer.adapt(train_ds.map(lambda t, l: t))

    model = tf.keras.Sequential([
        vectorizer,
        tf.keras.layers.Embedding(input_dim=MAX_TOKENS, output_dim=EMBED_DIM, mask_zero=True),
        tf.keras.layers.Bidirectional(tf.keras.layers.LSTM(LSTM_UNITS, return_sequences=True)),
        tf.keras.layers.Bidirectional(tf.keras.layers.LSTM(LSTM_UNITS // 2)),
        tf.keras.layers.Dense(64, activation="relu"),
        tf.keras.layers.Dropout(0.4),
        tf.keras.layers.Dense(num_classes, activation="softmax"),
    ])

    model.compile(
        optimizer=tf.keras.optimizers.Adam(1e-3),
        loss="sparse_categorical_crossentropy",
        metrics=["accuracy"],
    )

    model.fit(
        train_ds, epochs=EPOCHS, validation_data=test_ds,
        class_weight=class_weight_dict,
        callbacks=[
            tf.keras.callbacks.EarlyStopping(
                monitor="val_loss", patience=6, restore_best_weights=True,
            ),
            tf.keras.callbacks.ReduceLROnPlateau(
                monitor="val_loss", factor=0.5, patience=3, min_lr=1e-5,
            ),
        ],
        verbose=1,
    )

    loss, acc = model.evaluate(test_ds, verbose=0)
    print(f"\nTest loss: {loss:.4f}  |  Test accuracy: {acc:.2%}")

    y_pred = np.argmax(
        model.predict(tf.data.Dataset.from_tensor_slices(X_test).batch(BATCH_SIZE), verbose=0),
        axis=1,
    )
    print("\nClassification report:")
    print(classification_report(y_test, y_pred, target_names=label_encoder.classes_))

    os.makedirs("models", exist_ok=True)
    model.save(MODEL_PATH)
    with open(LABELS_PATH, "w") as f:
        for lbl in label_encoder.classes_:
            f.write(lbl + "\n")

    print(f"Model saved  → {MODEL_PATH}")
    print(f"Labels saved → {LABELS_PATH}")


if __name__ == "__main__":
    main()
