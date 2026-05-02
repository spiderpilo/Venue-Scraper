import re


def enrich_fields(place, website_text, incentive):
    text = website_text.lower() if website_text else ""
    business_type = (place.get("type") or "").lower()

    return {
        "Cuisine / Experience Category": infer_experience_category(text, business_type),
        "Days / Timing Restrictions": extract_timing(text),
        "Group Friendly?": infer_group_friendly(text),
        "Psychological Motivator Type": infer_motivator(text, incentive),
        "Estimated Perceived Value ($ range)": extract_value(text),
        "Expiration / Ongoing": infer_expiration(text),
    }


def infer_experience_category(text, business_type):
    if "live music" in text or "dj" in text:
        return "Live Music"

    if "happy hour" in text:
        return "Happy Hour"

    if "brunch" in text or "breakfast" in business_type:
        return "Brunch"

    if "seafood" in business_type:
        return "Seafood"

    if "american" in business_type:
        return "American"

    if "bar" in business_type or "cocktail" in text or "beer" in text:
        return "Bar"

    if "pizza" in text or "pizza" in business_type:
        return "Pizza"

    return "Unknown"


def extract_timing(text):
    patterns = [
        r"\b(mon|tue|wed|thu|fri|sat|sun)(day)?\s*[-–&to]+\s*(mon|tue|wed|thu|fri|sat|sun)(day)?\b",
        r"\b(mon|tue|wed|thu|fri|sat|sun)(day)?\b",
        r"\b\d{1,2}(:\d{2})?\s?(am|pm)\s*[-–to]+\s*\d{1,2}(:\d{2})?\s?(am|pm)\b",
        r"\b\d{1,2}(:\d{2})?\s?(am|pm)\b",
        r"\bdaily\b",
        r"\bweekdays\b",
        r"\bweekends\b",
    ]

    matches = []

    for pattern in patterns:
        found = re.findall(pattern, text, re.IGNORECASE)

        for item in found:
            if isinstance(item, tuple):
                cleaned = " ".join([part for part in item if part])
            else:
                cleaned = item

            if cleaned and cleaned not in matches:
                matches.append(cleaned)

    if not matches:
        return "Unknown"

    return ", ".join(matches[:3])


def infer_group_friendly(text):
    signals = [
        "group",
        "large party",
        "large parties",
        "private dining",
        "events",
        "catering",
        "reservations",
        "banquet",
        "party room",
    ]

    for signal in signals:
        if signal in text:
            return "Likely"

    return "Unknown"


def infer_motivator(text, incentive):
    combined = text + " " + str(incentive).lower()

    if "free" in combined or "no cover" in combined:
        return "Free"

    if "happy hour" in combined or "live music" in combined or "dj" in combined:
        return "Social"

    if "discount" in combined or "% off" in combined or "deal" in combined or "special" in combined:
        return "Savings"

    if "limited time" in combined or "tonight only" in combined or "today only" in combined:
        return "Urgency"

    return "Unknown"


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
            value = match.group()

            if value.lower() in ["free", "no cover"]:
                return "$0"

            if value.lower() == "half off":
                return "50% off"

            return value

    return "Unknown"


def infer_expiration(text):
    if "ongoing" in text:
        return "Ongoing"

    if "limited time" in text or "while supplies last" in text:
        return "Limited Time"

    if "daily" in text or "every" in text or "weekly" in text:
        return "Ongoing"

    return "Unknown"