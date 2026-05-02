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
]


def extract_incentive(text):
    if not text:
        return empty_result("Could not scrape source")

    sentences = re.split(r'[.!?]', text)
    matches = []

    for sentence in sentences:
        lower = sentence.lower()

        for keyword in KEYWORDS:
            if keyword in lower:
                matches.append(sentence.strip())

    if not matches:
        return empty_result("Needs manual verification")

    best = matches[0]

    return {
        "category": infer_category(best),
        "teaser": shorten(best),
        "description": best,
        "timing": extract_time(best),
        "motivator": infer_motivator(best),
        "value": extract_value(best),
        "status": "Unknown",
        "notes": "Extracted from website text"
    }


def empty_result(note):
    return {
        "category": "Unknown",
        "teaser": "Needs extraction",
        "description": "No incentive found",
        "timing": "Unknown",
        "motivator": "Unknown",
        "value": "Unknown",
        "status": "Unknown",
        "notes": note
    }


def shorten(text):
    return text[:60]


def infer_category(text):
    text = text.lower()
    if "happy hour" in text:
        return "Happy Hour"
    if "live music" in text:
        return "Live Music"
    if "discount" in text or "off" in text:
        return "Discount"
    return "General"


def infer_motivator(text):
    text = text.lower()
    if "free" in text:
        return "Free"
    if "happy hour" in text or "music" in text:
        return "Social"
    if "discount" in text:
        return "Discount"
    return "Unknown"


def extract_time(text):
    match = re.search(r'\b\d{1,2}(:\d{2})?\s?(am|pm)\b', text.lower())
    return match.group() if match else "Unknown"


def extract_value(text):
    match = re.search(r'\d+% off', text.lower())
    if match:
        return match.group()
    if "free" in text.lower():
        return "$0"
    return "Unknown"