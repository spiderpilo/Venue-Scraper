# ─────────────────────────────────────────────────────────────────────────────
# keyword_bank.py — Shared keyword lists used across the scraping pipeline
#
# These are NOT used directly inside the spider yet — they're a reference bank
# your teammate is building out for future filtering and scoring logic.
# ─────────────────────────────────────────────────────────────────────────────

# INCENTIVE_KEYWORDS: words/phrases that signal a promotional offer exists.
# If any of these appear in scraped text, the content is worth examining further.
INCENTIVE_KEYWORDS = [
    "happy hour",
    "discount",
    "deal",
    "deals",
    "special",
    "specials",
    "promo",
    "promotion",
    "offer",
    "offers",
    "coupon",
    "free",
    "no cover",
    "no charge",
    "complimentary",
    "half off",
    "half price",
    "% off",
    "save",
    "bogo",
    "2 for 1",
    "two for one",
    "early bird",
    "early entry",
    "matinee",
    "twilight",
    "admission",
    "cover charge",
    "ticket",
    "tickets",
    "wristband",
    "live music",
    "live band",
    "live entertainment",
    "open mic",
    "karaoke",
    "dj night",
    "concert",
    "group rate",
    "group pricing",
    "group discount",
    "party package",
    "birthday package",
    "private event",
    "unlimited",
    "tasting",
    "student",
    "senior",
    "military",
    "member",
    "loyalty",
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
    "$",
]

# LINK_KEYWORDS: URL path fragments that suggest a page is worth crawling.
# e.g. a link to "/specials" or "/happy-hour" is more likely to have offer
# content than a link to "/about". Used for link prioritization when crawling
# multi-page sites.
LINK_KEYWORDS = [
    "happy-hour",
    "happyhour",
    "happy_hour",
    "specials",
    "special",
    "deals",
    "deal",
    "promo",
    "promotion",
    "offers",
    "offer",
    "discount",
    "coupons",
    "menu",
    "drinks",
    "drink",
    "bar",
    "events",
    "event",
    "live-music",
    "live-entertainment",
    "music",
    "shows",
    "tickets",
    "admission",
    "pricing",
    "packages",
    "groups",
    "party",
    "birthday",
]

# NOISE_PHRASES: phrases that look like content but aren't useful offer data.
# If a scraped block only contains these, it should be discarded.
# Mostly footer/nav boilerplate that appears on every page of a site.
NOISE_PHRASES = [
    "privacy policy",
    "terms of use",
    "cookie policy",
    "all rights reserved",
    "sign up",
    "subscribe",
    "follow us",
    "contact us",
    "get directions",
    "read more",
    "learn more",
    "view all",
    "book now",
    "order now",
]

# MENU_FOOD_WORDS: food item words that suggest a block is menu content, not
# an offer. A block mentioning "burger", "taco", "salad" is probably a menu
# description — useful for filtering out menu noise from offer candidates.
MENU_FOOD_WORDS = [
    "burger",
    "pizza",
    "taco",
    "tacos",
    "salad",
    "soup",
    "steak",
    "chicken",
    "pasta",
    "sushi",
    "fries",
    "dessert",
    "appetizer",
    "entree",
    "gluten free",
    "vegetarian",
    "vegan",
]