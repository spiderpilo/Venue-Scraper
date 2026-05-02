import re
import pandas as pd


KEYWORDS = [
    "happy hour",
    "discount",
    "deal",
    "special",
    "promo",
    "coupon",
    "free",
    "live music",
    "no cover",
    "% off",
    "half off",
    "private dining",
    "large parties",
    "group",
    "reservation",
    "event",
]


def split_into_sentences(text):
    if not text:
        return []

    sentences = re.split(r"[.!?\n]", text)
    cleaned = []

    for sentence in sentences:
        sentence = sentence.strip()

        if len(sentence) < 25:
            continue

        cleaned.append(sentence)

    return cleaned


def is_candidate_sentence(sentence):
    lower = sentence.lower()
    return any(keyword in lower for keyword in KEYWORDS)


def build_sentence_dataset(places_with_text):
    rows = []

    for place in places_with_text:
        sentences = split_into_sentences(place.get("website_text", ""))

        for sentence in sentences:
            if is_candidate_sentence(sentence):
                rows.append({
                    "venue_id": place.get("venue_id"),
                    "venue_name": place.get("venue_name"),
                    "source_url": place.get("source_url"),
                    "sentence": sentence,
                    "label": "UNLABELED"
                })

    return pd.DataFrame(rows)


def save_sentence_dataset(df, filename="data/processed/sentence_dataset.csv"):
    df.to_csv(filename, index=False)
    print(f"Saved sentence dataset to {filename}")