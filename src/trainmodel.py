import os
import pandas as pd
import tensorflow as tf
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder


DATA_PATH = "data/processed/sentence_dataset_filtered.csv"
MODEL_PATH = "models/incentive_model.keras"
LABELS_PATH = "models/labels.txt"


def main():
    df = pd.read_csv(DATA_PATH)

    df = df.dropna(subset=["sentence", "label"])
    df = df[df["label"] != "UNLABELED"]

    if len(df) < 10:
        raise ValueError("Not enough labeled rows to train.")

    texts = df["sentence"].astype(str).tolist()
    labels = df["label"].astype(str).tolist()

    label_encoder = LabelEncoder()
    y = label_encoder.fit_transform(labels).astype("int32")

    print("Training rows:", len(df))
    print("Labels:", list(label_encoder.classes_))

    X_train, X_test, y_train, y_test = train_test_split(
        texts,
        y,
        test_size=0.2,
        random_state=42,
        stratify=y
    )

    train_ds = tf.data.Dataset.from_tensor_slices((X_train, y_train)).batch(8)
    test_ds = tf.data.Dataset.from_tensor_slices((X_test, y_test)).batch(8)

    vectorizer = tf.keras.layers.TextVectorization(
        max_tokens=10000,
        output_mode="int",
        output_sequence_length=60
    )

    text_only_ds = train_ds.map(lambda text, label: text)
    vectorizer.adapt(text_only_ds)

    model = tf.keras.Sequential([
        vectorizer,
        tf.keras.layers.Embedding(input_dim=10000, output_dim=64),
        tf.keras.layers.GlobalAveragePooling1D(),
        tf.keras.layers.Dense(64, activation="relu"),
        tf.keras.layers.Dropout(0.3),
        tf.keras.layers.Dense(len(label_encoder.classes_), activation="softmax")
    ])

    model.compile(
        optimizer="adam",
        loss="sparse_categorical_crossentropy",
        metrics=["accuracy"]
    )

    model.fit(
        train_ds,
        epochs=15,
        validation_data=test_ds
    )

    loss, accuracy = model.evaluate(test_ds)
    print(f"\nTest Accuracy: {accuracy:.2f}")

    os.makedirs("models", exist_ok=True)

    model.save(MODEL_PATH)

    with open(LABELS_PATH, "w") as file:
        for label in label_encoder.classes_:
            file.write(label + "\n")

    print(f"Model saved to {MODEL_PATH}")
    print(f"Labels saved to {LABELS_PATH}")


if __name__ == "__main__":
    main()