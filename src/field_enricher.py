import re


def enrich_fields(place, website_text, incentive):
    text = website_text.lower() if website_text else ""
    business_type = (place.get("type") or "").lower()

    return {
        "Cuisine / Experience Category": infer_experience_category(text, business_type),
        "Days / Timing Restrictions": choose_best_value(
            incentive.get("timing"),
            extract_timing(text),
        ),
        "Group Friendly?": infer_group_friendly(text),
        "Psychological Motivator Type": choose_best_value(
            incentive.get("motivator"),
            infer_motivator(text),
        ),
        "Estimated Perceived Value ($ range)": choose_best_value(
            incentive.get("value"),
            extract_value(text),
        ),
        "Expiration / Ongoing": choose_best_value(
            incentive.get("status"),
            infer_expiration(text),
        ),
    }


def choose_best_value(primary, fallback):
    if primary and primary != "Unknown":
        return primary

    if fallback and fallback != "Unknown":
        return fallback

    return "Unknown"


def infer_experience_category(text, business_type):
    if "live music" in text or "dj" in text or "karaoke" in text:
        return "Live Music"

    if "happy hour" in text:
        return "Happy Hour"

    if "breakfast" in business_type or "brunch" in text:
        return "Brunch"

    if "seafood" in business_type:
        return "Seafood"

    if "pizza" in business_type or "pizza" in text:
        return "Pizza"

    if "bar" in business_type or "cocktail" in text or "beer" in text:
        return "Bar"

    # fallback from Google Places business type
    if "_restaurant" in business_type:
        return business_type.replace("_restaurant", "").replace("_", " ").title()

    if business_type:
        return business_type.replace("_", " ").title()

    return "Unknown"


def extract_timing(text):
    patterns = [
        r"\bmon[-–]\s?fri\b",
        r"\bfri[-–]\s?sun\b",
        r"\b(mon|tue|wed|thu|fri|sat|sun)(day)?\s*[-–]\s*(mon|tue|wed|thu|fri|sat|sun)(day)?\b",
        r"\b(mon|tue|wed|thu|fri|sat|sun)(day)?\b",
        r"\b\d{1,2}(:\d{2})?\s?(am|pm)\s*[-–]\s*\d{1,2}(:\d{2})?\s?(am|pm)\b",
        r"\b\d{1,2}(:\d{2})?\s?[-–]\s?\d{1,2}(:\d{2})?\s?(am|pm)\b",
        r"\b\d{1,2}(:\d{2})?\s?(am|pm)\b",
        r"\bdaily\b",
        r"\bevery day\b",
        r"\bweekdays\b",
        r"\bweekends\b",
        r"\btonight\b",
        r"\btoday\b",
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


def infer_group_friendly(text):
    strong_signals = [
        "private dining",
        "large parties",
        "large party",
        "group dining",
        "banquet",
        "party room",
        "event space",
        "private events",
    ]

    weak_signals = [
        "reservations",
        "reservation",
        "book",
        "table",
        "dining",
        "event",
        "events",
        "party",
        "parties",
        "group",
        "catering",
    ]

    for signal in strong_signals:
        if signal in text:
            return "Yes"

    for signal in weak_signals:
        if signal in text:
            return "Likely"

    return "Unknown"


def infer_motivator(text):
    if "free" in text or "no cover" in text:
        return "Free"

    if "happy hour" in text or "live music" in text or "dj" in text or "karaoke" in text:
        return "Social"

    if "discount" in text or "% off" in text or "deal" in text or "special" in text or "promo" in text:
        return "Savings"

    if "limited time" in text or "tonight only" in text or "today only" in text:
        return "Urgency"

    return "Unknown"


def extract_value(text):
    patterns = [
        r"\d+% off",
        r"\$\d+ off",
        r"\$\d+",
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


def infer_expiration(text):
    if "ongoing" in text:
        return "Ongoing"

    if "daily" in text or "every day" in text or "weekly" in text or "every week" in text:
        return "Ongoing"

    if "limited time" in text or "while supplies last" in text or "today only" in text or "tonight only" in text:
        return "Limited Time"

    return "Unknown"