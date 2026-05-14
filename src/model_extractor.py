import os
import re
import time
import tensorflow as tf
import numpy as np

MODEL_PATH  = "models/incentive_model.keras"
LABELS_PATH = "models/labels.txt"

model  = None
labels = None

# Sentences must contain at least one of these to be worth classifying
INCENTIVE_KEYWORDS = [
    "happy hour", "discount", "deal", "special", "promo", "coupon",
    "free", "live music", "no cover", "% off", "half off",
    "early entry", "matinee", "early bird", "cover charge",
    "admission", "booking", "save ", " off", "weekly", "daily",
    "every ", "tonight", "monday", "tuesday", "wednesday", "thursday",
    "friday", "saturday", "sunday", "group", "unlimited", "twilight",
    "slurpee", "tasting", "wristband", "$",
]

# Phrases that mark nav / CTA / boilerplate — zero-score these sentences
_NAV_PHRASES = [
    "more info", "learn more", "click here", "contact us", "book now",
    "sign up", "subscribe", "privacy policy", "terms of use",
    "our events", "event calendar", "view all", "see all", "read more",
    "book your", "shop now", "order now", "find us", "get directions",
    "follow us", "join our", "join us on", "skip to", "back to top",
    "cookie policy", "all rights reserved",
    # Additional boilerplate / tagline patterns
    "link to", "click to", "perfect venue", "the ideal venue", "perfect place for",
    "host your", "private dining", "event space", "venue hire",
    "open for lunch", "open for dinner", "open daily for",
    "serving breakfast", "serving lunch", "serving dinner",
    "hours of operation", "business hours",
    "explore our", "discover our", "check out our",
]

# Regex patterns that signal a high-quality, specific incentive sentence
_QUALITY_BONUSES = [
    (r"\$\d",                                      0.20),  # dollar amount
    (r"\d+\s*%",                                   0.20),  # percentage
    (r"\d{1,2}(:\d{2})?\s*(am|pm)",               0.15),  # clock time
    (r"\b(mon|tue|wed|thu|fri|sat|sun)(day)?\b",   0.10),  # weekday name
    (r"\b(daily|weekly|every)\b",                  0.10),  # frequency word
    (r"\b(off|save|free|no cover|no charge)\b",    0.10),  # explicit offer word
]


def _sentence_quality(sentence: str) -> float:
    """
    Return a quality multiplier in [0, 1].
    Nav/CTA text → 0.0.  Specific incentive details → closer to 1.0.
    """
    lower = sentence.lower()

    # Hard disqualify: navigation / CTA text
    if any(phrase in lower for phrase in _NAV_PHRASES):
        return 0.0

    # Hard disqualify: "Open [days/time]" hours listings (not incentives)
    # Only fires on "open", not "hour/hours" to avoid killing happy-hour sentences
    if re.search(r"\bopen(ing)?\b.{0,40}\b\d{1,2}(:\d{2})?\s*(am|pm)", lower, re.IGNORECASE):
        return 0.0

    # Penalise heavily repeated words (nav lists like "Nightclub Party Nightclub")
    words = lower.split()
    if len(words) > 4 and len(set(words)) / len(words) < 0.60:
        return 0.15

    quality = 0.50  # baseline
    for pattern, bonus in _QUALITY_BONUSES:
        if re.search(pattern, lower, re.IGNORECASE):
            quality += bonus

    # Length sweet spot: 40–250 chars
    n = len(sentence)
    if 40 <= n <= 250:
        quality += 0.10
    elif n < 30:
        quality -= 0.20

    return min(max(quality, 0.05), 1.0)


def load_model():
    global model, labels
    if model is None:
        if not os.path.exists(MODEL_PATH):
            raise FileNotFoundError(f"Model not found at {MODEL_PATH}")
        model = tf.keras.models.load_model(MODEL_PATH)

        if not os.path.exists(LABELS_PATH):
            raise FileNotFoundError(f"Labels not found at {LABELS_PATH}")
        with open(LABELS_PATH) as f:
            labels = [line.strip() for line in f]


def _has_incentive_keywords(sentence: str) -> bool:
    lower = sentence.lower()
    return any(kw in lower for kw in INCENTIVE_KEYWORDS)


def extract_incentive_with_model(text, timing_metrics=None):
    if timing_metrics is not None:
        start_time = time.time()

    load_model()

    if not text:
        if timing_metrics is not None:
            timing_metrics["model_inference_time"] = 0.0
        return empty_result("Could not scrape source")

    # Split and pre-filter: only run the model on sentences that look incentive-related
    raw_sentences = re.split(r"[.!?\n]", text)
    candidates = []
    for s in raw_sentences:
        clean = s.strip()
        if len(clean) < 10:
            continue
        if _has_incentive_keywords(clean):
            candidates.append(clean)

    # If nothing passed the filter the page has no incentive content
    if not candidates:
        if timing_metrics is not None:
            timing_metrics["model_inference_time"] = 0.0
        return empty_result("No incentive keywords found on page")

    sentence_predictions = []
    for sentence in candidates:
        quality = _sentence_quality(sentence)
        if quality == 0.0:          # hard-disqualified nav text
            continue

        prediction = model.predict(tf.constant([sentence]), verbose=0)
        predicted_idx = np.argmax(prediction[0])
        predicted_label = labels[predicted_idx]
        confidence = float(prediction[0][predicted_idx])

        # Skip if model thinks it's No Incentive
        if predicted_label == "No Incentive":
            continue

        if confidence > 0.3:
            sentence_predictions.append({
                "sentence":   sentence,
                "label":      predicted_label,
                "confidence": confidence,
                "quality":    quality,
                "score":      confidence * quality,  # combined ranking key
            })

    if timing_metrics is not None:
        timing_metrics["model_inference_time"] = time.time() - start_time

    if not sentence_predictions:
        return empty_result("No incentive detected by model")

    best = max(sentence_predictions, key=lambda x: x["score"])
    category    = best["label"]
    description = best["sentence"]

    return {
        "category":         category,
        "teaser":           shorten(description),
        "description":      description,
        "timing":           extract_time(description),
        "motivator":        infer_motivator_from_category(category),
        "value":            extract_value(description),
        "status":           infer_status(description),
        "notes":            f"Model prediction (confidence: {best['confidence']:.2f})",
        "model_confidence": best["confidence"],
        "all_predictions":  sentence_predictions,
    }


def infer_motivator_from_category(category):
    return {
        "Free":           "Free",
        "Happy Hour":     "Social",
        "Live Music":     "Social",
        "Discount":       "Savings",
        "Group Friendly": "Social",
    }.get(category, "Unknown")


def shorten(text):
    return text[:70].strip() + "..." if len(text) > 70 else text


def extract_time(text):
    patterns = [
        r"\b(mon|tue|wed|thu|fri|sat|sun)(day)?\s*[-–]\s*(mon|tue|wed|thu|fri|sat|sun)(day)?\b",
        r"\b(mon|tue|wed|thu|fri|sat|sun)(day)?\b",
        r"\b\d{1,2}(:\d{2})?\s?(am|pm)\s*[-–]\s*\d{1,2}(:\d{2})?\s?(am|pm)\b",
        r"\b\d{1,2}(:\d{2})?\s?(am|pm)\b",
        r"\bdaily\b", r"\bweekdays\b", r"\bweekends\b",
    ]
    matches = []
    for pattern in patterns:
        for m in re.finditer(pattern, text, re.IGNORECASE):
            v = m.group().strip()
            if v and v not in matches:
                matches.append(v)
    return ", ".join(matches[:5]) if matches else "Unknown"


def extract_value(text):
    for pattern in [r"\d+% off", r"\$\d+ off", r"half off", r"free", r"no cover"]:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            v = m.group().strip().lower()
            if v in ("free", "no cover"):
                return "$0"
            if v == "half off":
                return "50% off"
            return m.group().strip()
    return "Unknown"


def infer_status(text):
    lower = text.lower()
    if any(w in lower for w in ("daily", "weekly", "every")):
        return "Ongoing"
    if any(w in lower for w in ("limited time", "while supplies last",
                                 "today only", "tonight only")):
        return "Limited Time"
    return "Unknown"


def empty_result(note):
    return {
        "category":         "No Incentive",
        "teaser":           "No incentive found",
        "description":      "No incentive found",
        "timing":           "Unknown",
        "motivator":        "Unknown",
        "value":            "Unknown",
        "status":           "Unknown",
        "notes":            note,
        "model_confidence": 0.0,
        "all_predictions":  [],
    }
