import re

BUSINESS_TYPE_MAP = {
    "american_restaurant": "American",
    "bar": "Bar",
    "bar_and_grill": "Bar & Grill",
    "barbecue_restaurant": "BBQ",
    "breakfast_restaurant": "Breakfast",
    "brunch_restaurant": "Brunch",
    "burger_restaurant": "Burgers",
    "cafe": "Cafe",
    "chinese_restaurant": "Chinese",
    "coffee_shop": "Coffee",
    "fast_food_restaurant": "Fast Food",
    "fine_dining_restaurant": "Fine Dining",
    "greek_restaurant": "Greek",
    "indian_restaurant": "Indian",
    "italian_restaurant": "Italian",
    "japanese_restaurant": "Japanese",
    "korean_restaurant": "Korean",
    "mediterranean_restaurant": "Mediterranean",
    "mexican_restaurant": "Mexican",
    "middle_eastern_restaurant": "Middle Eastern",
    "pizza_restaurant": "Pizza",
    "pub": "Pub",
    "ramen_restaurant": "Ramen",
    "restaurant": "Restaurant",
    "seafood_restaurant": "Seafood",
    "steak_house": "Steakhouse",
    "sushi_restaurant": "Sushi",
    "thai_restaurant": "Thai",
    "vegan_restaurant": "Vegan",
    "vegetarian_restaurant": "Vegetarian",
    "wine_bar": "Wine Bar",
}

GROUP_SIGNALS = [
    "group", "party", "parties", "event", "events", "private",
    "reservation", "catering", "large", "corporate", "celebration",
    "gather", "gathering", "venue hire",
]

GROUP_NEGATIVE = [
    "no reservations", "walk-in only", "counter service",
]


def enrich_fields(place: dict, text: str, incentive: dict) -> dict:
    business_type = place.get("type", "")
    text_lower = text.lower() if text else ""

    return {
        "Cuisine / Experience Category": _cuisine_category(business_type, text_lower, incentive),
        "Days / Timing Restrictions": incentive.get("timing", "Unknown"),
        "Group Friendly?": _group_friendly(text_lower),
        "Psychological Motivator Type": incentive.get("motivator", "Unknown"),
        "Estimated Perceived Value ($ range)": incentive.get("value", "Unknown"),
        "Expiration / Ongoing": incentive.get("status", "Unknown"),
    }


def _cuisine_category(business_type: str, text_lower: str, incentive: dict) -> str:
    # If the incentive category is experience-based, use that
    inc_cat = incentive.get("category", "")
    if inc_cat in ("Happy Hour", "Live Music"):
        return inc_cat

    # Map business type
    mapped = BUSINESS_TYPE_MAP.get(business_type)
    if mapped:
        return mapped

    # Infer from text keywords
    keyword_map = [
        ("pizza", "Pizza"),
        ("sushi", "Sushi"),
        ("ramen", "Ramen"),
        ("taco", "Mexican"),
        ("burrito", "Mexican"),
        ("burger", "Burgers"),
        ("bbq", "BBQ"),
        ("barbecue", "BBQ"),
        ("seafood", "Seafood"),
        ("steak", "Steakhouse"),
        ("wine bar", "Wine Bar"),
        ("coffee", "Coffee"),
        ("cocktail", "Bar"),
        ("craft beer", "Bar"),
        ("brunch", "Brunch"),
        ("breakfast", "Breakfast"),
    ]
    for keyword, label in keyword_map:
        if keyword in text_lower:
            return label

    return "Restaurant"


def _group_friendly(text_lower: str) -> str:
    if any(neg in text_lower for neg in GROUP_NEGATIVE):
        return "No"
    if any(sig in text_lower for sig in GROUP_SIGNALS):
        return "Likely"
    return "Unknown"
