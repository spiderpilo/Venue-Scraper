KEYWORDS = [
    "happy hour",
    "discount",
    "deal",
    "special",
    "promo",
    "coupon",
    "free",
    "10% off",
    "20% off",
    "live music",
    "no cover",
    "student discount",
    "kids eat free"
]


def extract_incentive(text):
    if not text:
        return {
            "category": "Unknown",
            "teaser": "Needs extraction",
            "description": "No website text found",
            "timing": "Unknown",
            "motivator": "Unknown",
            "value": "Unknown",
            "status": "Unknown",
            "notes": "Could not scrape source"
        }

    lower_text = text.lower()

    found_keywords = []

    for keyword in KEYWORDS:
        if keyword in lower_text:
            found_keywords.append(keyword)

    if not found_keywords:
        return {
            "category": "Unknown",
            "teaser": "No obvious incentive found",
            "description": "No incentive keywords detected on homepage",
            "timing": "Unknown",
            "motivator": "Unknown",
            "value": "Unknown",
            "status": "Unknown",
            "notes": "Needs manual verification"
        }

    first_keyword = found_keywords[0]

    return {
        "category": first_keyword.title(),
        "teaser": first_keyword.title(),
        "description": f"Detected possible incentive keyword(s): {', '.join(found_keywords)}",
        "timing": "Unknown",
        "motivator": classify_motivator(found_keywords),
        "value": estimate_value(found_keywords),
        "status": "Unknown",
        "notes": "Keyword detected from official website homepage"
    }


def classify_motivator(keywords):
    discount_words = ["discount", "deal", "promo", "coupon", "10% off", "20% off"]
    free_words = ["free", "no cover", "kids eat free"]
    social_words = ["happy hour", "live music"]

    for keyword in keywords:
        if keyword in discount_words:
            return "Discount"
        if keyword in free_words:
            return "Free"
        if keyword in social_words:
            return "Social"

    return "Unknown"


def estimate_value(keywords):
    for keyword in keywords:
        if keyword in ["10% off", "20% off"]:
            return keyword

    if "free" in keywords or "no cover" in keywords:
        return "$0"

    return "Unknown"