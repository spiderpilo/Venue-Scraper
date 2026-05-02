import re


def enrich_fields(place, website_text, incentive):
    text = website_text.lower() if website_text else ""
    business_type = (place.get("type") or "").lower()
    incentive_text = str(incentive).lower()

    combined_text = text + " " + business_type + " " + incentive_text

    return {
        "Cuisine / Experience Category": infer_experience_category(combined_text, business_type),
        "Days / Timing Restrictions": extract_timing(combined_text),
        "Group Friendly?": infer_group_friendly(combined_text),
        "Psychological Motivator Type": infer_motivator(combined_text),
        "Estimated Perceived Value ($ range)": extract_value(combined_text),
        "Expiration / Ongoing": infer_expiration(combined_text),
    }


def infer_experience_category(text, business_type):
    category_rules = {
        "Live Music": ["live music", "dj", "band", "concert", "karaoke"],
        "Happy Hour": ["happy hour"],
        "Brunch": ["brunch", "breakfast", "breakfast_restaurant"],
        "Seafood": ["seafood", "seafood_restaurant", "fish", "oyster"],
        "American": ["american_restaurant", "burger", "steak", "sandwich"],
        "Bar": ["bar", "cocktail", "beer", "wine", "pub", "tavern"],
        "Pizza": ["pizza"],
        "Coffee": ["coffee", "cafe"],
        "Dessert": ["dessert", "ice cream", "bakery"],
    }

    for category, keywords in category_rules.items():
        for keyword in keywords:
            if keyword in text or keyword in business_type:
                return category

    return "Unknown"


def extract_timing(text):
    timing_patterns = [
        r"\b(mon|tue|wed|thu|fri|sat|sun)(day)?\s*[-–]\s*(mon|tue|wed|thu|fri|sat|sun)(day)?\b",
        r"\b(mon|tue|wed|thu|fri|sat|sun)(day)?\b",
        r"\b\d{1,2}(:\d{2})?\s?(am|pm)\s*[-–]\s*\d{1,2}(:\d{2})?\s?(am|pm)\b",
        r"\b\d{1,2}(:\d{2})?\s?(am|pm)\b",
        r"\bdaily\b",
        r"\bevery day\b",
        r"\bweekdays\b",
        r"\bweekends\b",
    ]

    matches = []

    for pattern in timing_patterns:
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
    ]

    weak_signals = [
        "reservations",
        "events",
        "catering",
        "parties",
        "book a table",
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
    value_patterns = [
        r"\d+% off",
        r"\$\d+ off",
        r"\$\d+",
        r"half off",
        r"free",
        r"no cover",
    ]

    for pattern in value_patterns:
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