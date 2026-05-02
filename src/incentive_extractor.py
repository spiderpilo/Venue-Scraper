import re

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
]

BAD_PATTERNS = [
    "watch video",
    "click here",
    "learn more",
    "read more",
    "view menu",
    "order now",
    "subscribe",
    "sign up",
    "privacy policy",
    "terms of use",
]


def extract_incentive(text):
    if not text:
        return empty_result("Could not scrape source")

    sentences = re.split(r"[.!?\n]", text)
    matches = []

    for sentence in sentences:
        clean_sentence = sentence.strip()
        lower = clean_sentence.lower()

        if len(clean_sentence) < 25:
            continue

        if any(bad in lower for bad in BAD_PATTERNS):
            continue

        if any(keyword in lower for keyword in KEYWORDS):
            matches.append(clean_sentence)

    if not matches:
        return empty_result("Needs manual verification")

    best = max(matches, key=score_sentence)

    return {
        "category": infer_category(best),
        "teaser": shorten(best),
        "description": best,
        "timing": extract_time(best),
        "motivator": infer_motivator(best),
        "value": extract_value(best),
        "status": infer_status(best),
        "notes": "Extracted from website text",
    }


def score_sentence(sentence):
    score = 0
    lower = sentence.lower()

    if "happy hour" in lower:
        score += 5

    if "discount" in lower or "% off" in lower or "deal" in lower or "special" in lower:
        score += 4

    if "free" in lower or "no cover" in lower:
        score += 3

    if "live music" in lower or "dj" in lower or "karaoke" in lower:
        score += 3

    if any(time_word in lower for time_word in ["am", "pm", "daily", "friday", "saturday", "sunday", "mon", "tue", "wed", "thu", "fri", "sat", "sun"]):
        score += 3

    if 40 <= len(sentence) <= 250:
        score += 2

    return score


def empty_result(note):
    return {
        "category": "Unknown",
        "teaser": "Needs extraction",
        "description": "No incentive found",
        "timing": "Unknown",
        "motivator": "Unknown",
        "value": "Unknown",
        "status": "Unknown",
        "notes": note,
    }


def shorten(text):
    if len(text) <= 70:
        return text

    return text[:70].strip() + "..."


def infer_category(text):
    lower = text.lower()

    if "happy hour" in lower:
        return "Happy Hour"

    if "live music" in lower or "dj" in lower or "karaoke" in lower:
        return "Live Music"

    if "discount" in lower or "% off" in lower or "half off" in lower or "deal" in lower:
        return "Discount"

    if "free" in lower or "no cover" in lower:
        return "Free"

    if "special" in lower or "promo" in lower:
        return "Special"

    return "General"


def infer_motivator(text):
    lower = text.lower()

    if "free" in lower or "no cover" in lower:
        return "Free"

    if "happy hour" in lower or "live music" in lower or "dj" in lower or "karaoke" in lower:
        return "Social"

    if "discount" in lower or "% off" in lower or "deal" in lower or "special" in lower:
        return "Savings"

    if "limited time" in lower or "tonight only" in lower or "today only" in lower:
        return "Urgency"

    return "Unknown"


def extract_time(text):
    patterns = [
        r"\b(mon|tue|wed|thu|fri|sat|sun)(day)?\s*[-–]\s*(mon|tue|wed|thu|fri|sat|sun)(day)?\b",
        r"\b(mon|tue|wed|thu|fri|sat|sun)(day)?\b",
        r"\b\d{1,2}(:\d{2})?\s?(am|pm)\s*[-–]\s*\d{1,2}(:\d{2})?\s?(am|pm)\b",
        r"\b\d{1,2}(:\d{2})?\s?(am|pm)\b",
        r"\bdaily\b",
        r"\bweekdays\b",
        r"\bweekends\b",
    ]

    matches = []

    for pattern in patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            value = match.group().strip()

            if value and value not in matches:
                matches.append(value)

    if not matches:
        return "Unknown"

    return ", ".join(matches[:5])


def extract_value(text):
    patterns = [
        r"\d+% off",
        r"\$\d+ off",
        r"half off",
        r"free",
        r"no cover",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)

        if match:
            value = match.group().strip()

            if value.lower() in ["free", "no cover"]:
                return "$0"

            if value.lower() == "half off":
                return "50% off"

            return value

    return "Unknown"


def infer_status(text):
    lower = text.lower()

    if "daily" in lower or "weekly" in lower or "every" in lower:
        return "Ongoing"

    if "limited time" in lower or "while supplies last" in lower or "today only" in lower or "tonight only" in lower:
        return "Limited Time"

    return "Unknown"