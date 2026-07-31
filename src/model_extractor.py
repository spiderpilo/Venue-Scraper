import os
import re
import time
import numpy as np

MODEL_PATH   = "models/incentive_model.keras"
LABELS_CAT   = "models/labels_category.txt"
LABELS_MOT   = "models/labels_motivator.txt"
LABELS_CUI   = "models/labels_cuisine.txt"
BTYPE_VOCAB  = "models/btype_vocab.txt"

model      = None
lbl_cat    = None
lbl_mot    = None
lbl_cui    = None
_tf        = None


def _load_tf():
    global _tf
    if _tf is None:
        import tensorflow as tf
        _tf = tf
    return _tf


STRONG_KEYWORDS = [
    "happy hour", "discount", "% off", "half off", "half price", "half-price",
    "no cover", "no charge", "complimentary", "on us",
    "early entry", "early bird", "matinee", "twilight",
    "cover charge", "free before", "free admission",
    "drink special", "drink deal", "cocktail special", "beer special",
    "wine special", "well drink", "well shot", "rail drink",
    "shot special", "2 for 1", "two for one", "bogo", "open bar",
    "live music", "live band", "live entertainment", "live performance",
    "performing live", "open mic", "dj night", "karaoke",
    "free show", "free concert", "entertainment night",
    "music night", "band night", "show tonight",
    "doors open", "guest list", "guestlist", "vip entry",
    "reduced cover", "early admission", "skip the line",
    "group rate", "group ticket", "group pricing", "group minimum",
    "birthday package", "book your group",
    "season pass", "annual pass", "day pass",
    "promo", "coupon", "save ", "bogo",
    "summer special", "lunch special", "dinner special", "weekly special",
    "today's special", "chef's special", "daily special",
    "available now", "limited time", "while supplies last",
    "$",
]

WEAK_KEYWORDS = [
    "special", "deal", "free", "offer", "sale", "reward",
    "admission", "ticket", "wristband", "pass",
    "domestic", "house wine", "draft beer", "craft beer",
    "margarita", "bucket", "pitcher",
    "acoustic", "concert", "performing",
    "arrive early", "line pass",
    "party of", "private event", "corporate event",
    "team outing", "large party",
    "daily", "weekly", "every ", "tonight", "nightly",
    "monday", "tuesday", "wednesday", "thursday",
    "friday", "saturday", "sunday",
    " off", "per person", "per game", "per lane", "pricing",
    "unlimited", "booking", "tasting", "slurpee",
    "student", "senior", "military",
]

INCENTIVE_KEYWORDS = STRONG_KEYWORDS + WEAK_KEYWORDS

_BOILERPLATE = [
    "start your free trial", "copyright", "all rights reserved",
    "privacy policy", "terms of use", "terms of service", "cookie policy",
    "share its core values", "what this site has to offer",
    "story behind the business", "focus on the value this business",
    "describe what this site", "excellent place to share",
    "powered by wix", "powered by squarespace", "powered by wordpress",
    "built with", "website builder", "create your website",
    "sign up for free", "log in to your account",
    "subscribe to our newsletter", "join our mailing list",
    "membership", "member sign", "member login", "become a member",
    "join as a member", "membership plan", "membership fee",
    "monthly membership", "annual membership", "member benefits",
    "members only", "member exclusive", "member pricing",
    "membership required", "membership includes",
]

# Maps strong keywords → most likely incentive category.
# Used to confirm or boost borderline ML predictions (conf 0.5–0.75).
CATEGORY_HINTS = {
    # Live Music
    "live music":          "Live Music",
    "live band":           "Live Music",
    "live entertainment":  "Live Music",
    "performing live":     "Live Music",
    "open mic":            "Live Music",
    "acoustic":            "Live Music",
    "dj night":            "Live Music",
    "free show":           "Live Music",
    "free concert":        "Live Music",
    "music night":         "Live Music",
    "band night":          "Live Music",
    "entertainment night": "Live Music",
    # Early Entry
    "doors open":          "Early Entry",
    "guest list":          "Early Entry",
    "guestlist":           "Early Entry",
    "early admission":     "Early Entry",
    "reduced cover":       "Early Entry",
    "cover charge":        "Early Entry",
    "free before":         "Early Entry",
    "skip the line":       "Early Entry",
    "vip entry":           "Early Entry",
    # Happy Hour
    "happy hour":          "Happy Hour",
    "drink special":       "Happy Hour",
    "cocktail special":    "Happy Hour",
    "beer special":        "Happy Hour",
    "wine special":        "Happy Hour",
    "well drink":          "Happy Hour",
    "2 for 1":             "Happy Hour",
    "two for one":         "Happy Hour",
    "bogo":                "Happy Hour",
    "half price":          "Happy Hour",
    "open bar":            "Happy Hour",
    "margarita":           "Happy Hour",
    "draft beer":          "Happy Hour",
    # Group Booking
    "group rate":          "Group Booking",
    "group ticket":        "Group Booking",
    "group pricing":       "Group Booking",
    "private event":       "Group Booking",
    "corporate event":     "Group Booking",
    "book your group":     "Group Booking",
    "birthday package":    "Group Booking",
    # Matinee Deal
    "matinee":             "Matinee Deal",
    "twilight":            "Matinee Deal",
    "early show":          "Matinee Deal",
    "daytime rate":        "Matinee Deal",
    "per game":            "Matinee Deal",
    "per lane":            "Matinee Deal",
    # Free
    "no cover":            "Free",
    "no charge":           "Free",
    "free admission":      "Free",
    "complimentary":       "Free",
    # Discount
    "season pass":         "Discount",
    "annual pass":         "Discount",
    "day pass":            "Discount",
    "student":             "Discount",
    "military":            "Discount",
    "senior":              "Discount",
}

_NAV_PHRASES = [
    "more info", "learn more", "click here", "contact us", "book now",
    "sign up", "subscribe", "privacy policy", "terms of use",
    "our events", "event calendar", "view all", "see all", "read more",
    "book your", "shop now", "order now", "find us", "get directions",
    "follow us", "join our", "join us on", "skip to", "back to top",
    "cookie policy", "all rights reserved",
    "link to", "click to", "perfect venue", "the ideal venue", "perfect place for",
    "host your", "private dining", "event space", "venue hire",
    "open for lunch", "open for dinner", "open daily for",
    "serving breakfast", "serving lunch", "serving dinner",
    "hours of operation", "business hours",
    "explore our", "discover our", "check out our",
]

_QUALITY_BONUSES = [
    (r"\$\d",                                      0.20),
    (r"\d+\s*%",                                   0.20),
    (r"\d{1,2}(:\d{2})?\s*(am|pm)",               0.15),
    (r"\b(mon|tue|wed|thu|fri|sat|sun)(day)?\b",   0.10),
    (r"\b(daily|weekly|every)\b",                  0.10),
    (r"\b(off|save|free|no cover|no charge)\b",    0.10),
]

# Maps raw Business Type strings to the same vocab the model was trained on
_VENUE_TYPE_MAP = {
    "Live Music Venue": "Live Music", "Live Music & Dining": "Live Music",
    "Live Music & Bar": "Live Music", "American / Live Music": "Live Music",
    "Live Music / American": "Live Music", "Live Music / Bar": "Live Music",
    "Live Music": "Live Music",
    "Nightclub": "Nightclub", "Nightclub & Dining": "Nightclub",
    "Nightclub / Bar": "Nightclub", "Dining & Nightclub": "Nightclub",
    "Theater": "Theater", "Theater & Dining": "Theater",
    "Entertainment": "Entertainment", "Entertainment Venue": "Entertainment",
    "Outdoor Entertainment": "Entertainment",
    "Outdoor Entertainment & Dining": "Entertainment",
    "Garden / Entertainment": "Entertainment",
    "Bowling": "Bowling", "Bowling & Dining": "Bowling",
    "Museum": "Museum",
    "Movie Theater": "Movie Theater", "Movie Theater & Dining": "Movie Theater",
    "Aquarium": "Aquarium",
    "Comedy Club": "Comedy Club",
    "Casino": "Casino",
    "Dining": "Dining", "Dining & Bar": "Dining",
    "Dining & Live Music": "Dining", "bar": "Dining",
    "restaurant": "Dining", "Bar": "Dining",
}
_VENUE_DEFAULT = "Other"


def _map_venue_type(raw: str) -> str:
    return _VENUE_TYPE_MAP.get(str(raw or "").strip(), _VENUE_DEFAULT)


def _sentence_quality(sentence: str) -> float:
    lower = sentence.lower()
    if any(phrase in lower for phrase in _NAV_PHRASES):
        return 0.0
    if re.search(r"\bopen(ing)?\b.{0,40}\b\d{1,2}(:\d{2})?\s*(am|pm)", lower, re.IGNORECASE):
        return 0.0
    words = lower.split()
    if len(words) > 4 and len(set(words)) / len(words) < 0.60:
        return 0.15
    quality = 0.50
    for pattern, bonus in _QUALITY_BONUSES:
        if re.search(pattern, lower, re.IGNORECASE):
            quality += bonus
    n = len(sentence)
    if 40 <= n <= 250:
        quality += 0.10
    elif n < 30:
        quality -= 0.20
    return min(max(quality, 0.05), 1.0)


def model_available() -> bool:
    return (
        os.path.exists(MODEL_PATH) and
        os.path.exists(LABELS_CAT) and
        os.path.exists(LABELS_MOT) and
        os.path.exists(LABELS_CUI)
    )


def load_model():
    global model, lbl_cat, lbl_mot, lbl_cui
    if model is not None:
        return
    tf = _load_tf()
    if not os.path.exists(MODEL_PATH):
        raise FileNotFoundError(f"Model not found at {MODEL_PATH}")
    model = tf.keras.models.load_model(MODEL_PATH)

    def _read(path):
        with open(path) as f:
            return [l.strip() for l in f if l.strip()]

    lbl_cat = _read(LABELS_CAT)
    lbl_mot = _read(LABELS_MOT)
    lbl_cui = _read(LABELS_CUI)


def _is_boilerplate(sentence: str) -> bool:
    lower = sentence.lower()
    return any(bp in lower for bp in _BOILERPLATE)


def _has_incentive_keywords(sentence: str) -> bool:
    lower = sentence.lower()
    if _is_boilerplate(lower):
        return False
    if any(kw in lower for kw in STRONG_KEYWORDS):
        return True
    weak_hits = sum(1 for kw in WEAK_KEYWORDS if kw in lower)
    return weak_hits >= 2


def _category_hint(sentence: str) -> str | None:
    """Return the most specific category hint found in the sentence, or None."""
    lower = sentence.lower()
    # Longer/more specific phrases take priority over shorter ones
    for kw in sorted(CATEGORY_HINTS, key=len, reverse=True):
        if kw in lower:
            return CATEGORY_HINTS[kw]
    return None


# Business types where nightclub/entry patterns should override Happy Hour
_NIGHTCLUB_TYPES = {"Nightclub", "Bar", "Entertainment", "Casino"}
_LIVE_MUSIC_TYPES = {"Live Music"}

_EARLY_ENTRY_SIGNALS = re.compile(
    r"\b(cover charge|no cover|free before|doors open|guest list|"
    r"guestlist|early admission|vip entry|skip the line|reduced cover|"
    r"wristband|tickets? (at|are) \$|buy tickets?)\b",
    re.IGNORECASE,
)
_LIVE_MUSIC_SIGNALS = re.compile(
    r"\b(live (music|band|entertainment|show|performance)|performing live|"
    r"open mic|acoustic (set|night)|dj set|dj night|music night|"
    r"band night|concert|touring artist)\b",
    re.IGNORECASE,
)


def _apply_btype_prior(result: dict, raw_btype: str) -> dict:
    """
    Post-processing correction: fix the most common structural misclassification
    where Happy Hour is predicted for venues whose primary draw is Early Entry
    or Live Music.

    Scans ALL candidate sentences (stored in all_predictions), not just the best
    one — the early-entry or live-music signal is often in a lower-ranked sentence.
    """
    pred  = result.get("category", "")
    btype = _map_venue_type(raw_btype)

    if pred != "Happy Hour":
        return result

    # Build a combined text from all scored sentences for signal scanning
    all_preds   = result.get("all_predictions", [])
    all_text    = " ".join(p.get("sentence", "") for p in all_preds) if all_preds else result.get("description", "")
    best_desc   = result.get("description", "")

    # Nightclub/Bar + early entry signals in ANY candidate → reclassify
    if btype in _NIGHTCLUB_TYPES and _EARLY_ENTRY_SIGNALS.search(all_text):
        # Find the highest-quality early-entry sentence to use as description
        ee_sent = best_desc
        for p in sorted(all_preds, key=lambda x: -x.get("quality", 0)):
            if _EARLY_ENTRY_SIGNALS.search(p.get("sentence", "")):
                ee_sent = p["sentence"]
                break
        result = dict(result)
        result["category"] = "Early Entry"
        result["description"] = ee_sent
        result["teaser"]    = shorten(ee_sent)
        result["motivator"] = derive_motivator("Early Entry", ee_sent)
        result["notes"]     = result.get("notes", "") + " [btype-prior: Early Entry]"
        return result

    # Live Music venue + live music signals in ANY candidate → reclassify
    if btype in _LIVE_MUSIC_TYPES and _LIVE_MUSIC_SIGNALS.search(all_text):
        lm_sent = best_desc
        for p in sorted(all_preds, key=lambda x: -x.get("quality", 0)):
            if _LIVE_MUSIC_SIGNALS.search(p.get("sentence", "")):
                lm_sent = p["sentence"]
                break
        result = dict(result)
        result["category"] = "Live Music"
        result["description"] = lm_sent
        result["teaser"]    = shorten(lm_sent)
        result["motivator"] = derive_motivator("Live Music", lm_sent)
        result["notes"]     = result.get("notes", "") + " [btype-prior: Live Music]"
        return result

    return result


_MEMBERSHIP_PHRASES = [
    "membership", "become a member", "member sign", "member login",
    "members only", "member exclusive", "membership plan",
    "membership fee", "monthly membership", "annual membership",
    "membership required", "membership includes", "member benefits",
    "join as a member", "member pricing",
]


def _is_membership(result: dict) -> bool:
    text = (result.get("description", "") + " " + result.get("teaser", "")).lower()
    return any(p in text for p in _MEMBERSHIP_PHRASES)


def extract_incentive_with_model(text: str, business_type: str = "", timing_metrics=None) -> dict:
    start_time = time.time()
    if timing_metrics is not None:
        pass  # start_time already set above

    if not text:
        if timing_metrics is not None:
            timing_metrics["model_inference_time"] = 0.0
        return empty_result("Could not scrape source")

    raw_sentences = re.split(r"[.!?\n]", text)
    seen = set()
    candidates = []
    for s in raw_sentences:
        s = s.strip()
        if len(s) >= 10 and _has_incentive_keywords(s) and s not in seen:
            seen.add(s)
            candidates.append(s)

    if not candidates:
        if timing_metrics is not None:
            timing_metrics["model_inference_time"] = 0.0
        return empty_result("No incentive keywords found on page")

    btype = _map_venue_type(business_type)

    # ── ML model (fast path) ──────────────────────────────────────────────────
    ml_result = None
    if model_available():
        ml_result = _run_ml_model(candidates, btype, timing_metrics, start_time)
        #^ Add a temporary print inside this function

    if ml_result and ml_result["model_confidence"] >= 0.75:
        if _is_membership(ml_result):
            return empty_result("Membership-based incentive — skipped")
        ml_result["source"] = "ml_model"
        ml_result = _apply_btype_prior(ml_result, business_type)
        if timing_metrics is not None:
            timing_metrics["model_inference_time"] = time.time() - start_time
        return ml_result

    # ── Keyword-hint boost (0.50–0.74 confidence) ─────────────────────────────
    # If the best ML sentence contains a strong category-confirming keyword,
    # trust the ML prediction without calling Claude.
    if ml_result and ml_result["model_confidence"] >= 0.50:
        if _is_membership(ml_result):
            return empty_result("Membership-based incentive — skipped")
        hint = _category_hint(ml_result["description"])
        if hint and hint == ml_result["category"]:
            ml_result["model_confidence"] = min(ml_result["model_confidence"] + 0.15, 0.95)
            ml_result["source"] = "ml_model_hinted"
            if timing_metrics is not None:
                timing_metrics["model_inference_time"] = time.time() - start_time
            return ml_result

    # ── Claude fallback ───────────────────────────────────────────────────────
    from src.claude_extractor import extract_with_claude
    claude = extract_with_claude(" ".join(candidates[:20]), business_type=business_type)

    if timing_metrics is not None:
        timing_metrics["model_inference_time"] = time.time() - start_time

    if claude.get("category", "No Incentive") == "No Incentive":
        if ml_result and ml_result["category"] != "No Incentive":
            if _is_membership(ml_result):
                return empty_result("Membership-based incentive — skipped")
            ml_result["source"] = "ml_model_fallback"
            return ml_result
        return empty_result(claude.get("error", "No incentive detected"))

    claude_result = {
        "category":         claude["category"],
        "teaser":           claude.get("teaser") or shorten(claude.get("description", "")),
        "description":      claude.get("description", ""),
        "timing":           claude.get("timing", "Unknown"),
        "motivator":        claude.get("motivator") or _ml_motivator(ml_result),
        "cuisine":          claude.get("cuisine")   or _ml_cuisine(ml_result),
        "value":            claude.get("value", "Unknown"),
        "status":           infer_status(claude.get("description", "")),
        "notes":            "Claude extraction",
        "model_confidence": 1.0 if ml_result is None else ml_result.get("model_confidence", 0.0),
        "all_predictions":  [],
        "source":           "claude",
    }

    if _is_membership(claude_result):
        return empty_result("Membership-based incentive — skipped")

    return claude_result


def _run_ml_model(candidates: list, btype: str, timing_metrics, start_time) -> dict | None:
    try:
        tf = _load_tf()
        load_model()
    except Exception:
        return None

    # Filter by quality first, then batch-predict all at once
    filtered = [(s, _sentence_quality(s)) for s in candidates]
    filtered = [(s, q) for s, q in filtered if q > 0.0]

    sentence_predictions = []
    if not filtered:
        return None

    texts_batch  = [s for s, _ in filtered]
    quality_map  = {s: q for s, q in filtered}

    tf = _load_tf()
    ds = tf.data.Dataset.from_tensor_slices(
        {"text": texts_batch, "business_type": [btype] * len(texts_batch)}
    ).batch(32)
    preds = model.predict(ds, verbose=0)

    for i, sentence in enumerate(texts_batch):
        cat_idx    = int(np.argmax(preds["category"][i]))
        cat_lbl    = lbl_cat[cat_idx]
        confidence = float(preds["category"][i][cat_idx])

        if cat_lbl == "No Incentive" or confidence <= 0.3:
            continue

        mot_idx = int(np.argmax(preds["motivator"][i]))
        cui_idx = int(np.argmax(preds["cuisine"][i]))
        quality = quality_map[sentence]

        sentence_predictions.append({
            "sentence":   sentence,
            "label":      cat_lbl,
            "motivator":  lbl_mot[mot_idx],
            "cuisine":    lbl_cui[cui_idx],
            "confidence": confidence,
            "quality":    quality,
            "score":      confidence * quality,
        })
        #^ See if there arer any wrong outputs:
        """
        for p in result["all_predictions"]:
            print(p["score"], p["confidence"], p["quality"], p["label"], p["sentence"][:200])
        """

    if not sentence_predictions:
        return None

    best = max(sentence_predictions, key=lambda x: x["score"])
    description = best["sentence"]

    # Extract value and timing from ALL candidate sentences, not just the best.
    # The price or time info is often in a different sentence than the one that
    # scored highest confidence (e.g. best = tagline, price = separate line).
    all_sentences = [p["sentence"] for p in sentence_predictions]
    all_text = " ".join(all_sentences)

    timing = extract_time(description)
    if timing == "Unknown":
        timing = extract_time(all_text)

    value = extract_value(description)
    if value == "Unknown":
        # Scan individual sentences so we don't merge context across sentences
        for s in all_sentences:
            v = extract_value(s)
            if v != "Unknown":
                value = v
                break
    # Widen: scan ALL incentive-keyword candidates, not just the ML-classified ones.
    # A sentence with a price (e.g. "$5 well drinks") may score below ML threshold
    # but still contains extractable value.
    if value == "Unknown":
        for s in candidates:
            v = extract_value(s)
            if v != "Unknown":
                value = v
                break

    category = best["label"]
    return {
        "category":         category,
        "motivator":        derive_motivator(category, description),
        "cuisine":          best["cuisine"],
        "teaser":           shorten(description),
        "description":      description,
        "timing":           timing,
        "value":            value,
        "status":           infer_status(all_text),
        "notes":            f"Model prediction (confidence: {best['confidence']:.2f})",
        "model_confidence": best["confidence"],
        "all_predictions":  sentence_predictions,
    }


def _ml_motivator(ml_result) -> str:
    return ml_result["motivator"] if ml_result and "motivator" in ml_result else "Unknown"


def _ml_cuisine(ml_result) -> str:
    return ml_result["cuisine"] if ml_result and "cuisine" in ml_result else "Unknown"


def shorten(text):
    return text[:70].strip() + "..." if len(text) > 70 else text


def extract_time(text):
    """Extract all day/date/time references from text."""
    patterns = [
        # Day ranges: Mon-Fri, Monday through Friday, Fri & Sat
        r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)s?\s*(?:[-–&]|to|through)\s*(monday|tuesday|wednesday|thursday|friday|saturday|sunday)s?\b",
        r"\b(mon|tue|wed|thu|fri|sat|sun)\s*(?:[-–&]|to|through)\s*(mon|tue|wed|thu|fri|sat|sun)\b",
        # Individual day names — full name or 3-char abbreviation, singular or plural
        r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)s?\b",
        r"\b(mon|tue|wed|thu|fri|sat|sun)\b",
        # Time ranges: 4pm-7pm, 4:30 pm – 7 pm
        r"\b\d{1,2}(:\d{2})?\s?(am|pm)\s*[-–to]+\s*\d{1,2}(:\d{2})?\s?(am|pm)\b",
        r"\b\d{1,2}(:\d{2})?\s?(am|pm)\b",
        # 24-hour clock: 17:00, 22:30
        r"\b([01]\d|2[0-3]):[0-5]\d\b",
        # Named meal/time periods
        r"\b(noon|midnight|lunchtime?|brunch|dinner|happy hour|opening|closing)\b",
        r"\b(all day|all night|all week)\b",
        # Recurrence words — restrict "every/each" to time/day nouns only
        r"\b(daily|nightly|weekdays|weekends|weekly)\b",
        r"\b(every|each)\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday|week|weekend|weekday|night|day|month|hour|visit|show|game|event)\b",
        # Relative date words
        r"\b(tonight|today|this\s+(friday|saturday|sunday|weekend|week))\b",
        # Month + day: "Jan 15", "December 31"
        r"\b(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s+\d{1,2}\b",
    ]
    matches = []
    seen_spans = []
    for pattern in patterns:
        for m in re.finditer(pattern, text, re.IGNORECASE):
            start, end = m.start(), m.end()
            # Skip if this span overlaps an already-captured span
            if any(s <= start < e or s < end <= e for s, e in seen_spans):
                continue
            v = m.group().strip()
            if v and v.lower() not in [x.lower() for x in matches]:
                matches.append(v)
                seen_spans.append((start, end))
    return ", ".join(matches[:6]) if matches else "Unknown"


def extract_value(text):
    """Extract deal value — greedily capture ANY $ or % occurrence first."""
    lower = text.lower()

    # Free / no cover (most specific — check before $ scan)
    if re.search(r"\b(free admission|free entry|no cover|no charge|complimentary)\b", lower):
        return "$0 (free)"
    if re.search(r"\bfree\b", lower) and not re.search(r"\bfree (parking|wifi|shipping)\b", lower):
        return "$0 (free)"

    # Open bar
    if re.search(r"\bopen bar\b", lower):
        return "Open bar"

    # Half price / BOGO — qualitative but well-known
    if re.search(r"\bhalf[- ]?(price|off)\b", lower):
        return "50% off"
    if re.search(r"\b(2[\s-]?for[\s-]?1|two[\s-]?for[\s-]?one|bogo)\b", lower):
        return "2 for 1"

    # ── ANY percent mention ──────────────────────────────────────────────────
    # Prefer "X% off" pattern; fall back to any bare "X%"
    m = re.search(r"(\d+)\s*%\s*off", text, re.IGNORECASE)
    if m:
        return f"{m.group(1)}% off"
    m = re.search(r"(\d+)\s*%", text, re.IGNORECASE)
    if m:
        return f"{m.group(1)}%"

    # ── ANY dollar amount ────────────────────────────────────────────────────
    # Try dollar + qualifier first for context
    m = re.search(
        r"\$\s*(\d+(?:\.\d{1,2})?)\s*"
        r"(off|discount|cover|admission|tickets?|beers?|drinks?|cocktails?|shots?|wines?|specials?)?",
        text, re.IGNORECASE,
    )
    if m:
        amt = f"${m.group(1)}"
        qualifier = (m.group(2) or "").strip()
        return f"{amt} {qualifier}".strip() if qualifier else amt

    return "Unknown"


def infer_status(text):
    """Infer whether the incentive is ongoing or limited time."""
    lower = text.lower()
    if any(w in lower for w in (
        "limited time", "while supplies last", "today only", "tonight only",
        "one night only", "expires", "ends soon", "last chance",
    )):
        return "Limited Time"
    if re.search(r"\b(daily|weekly|every|each|nightly|mon|tue|wed|thu|fri|sat|sun)(day)?\b", lower, re.IGNORECASE):
        return "Ongoing"
    # Venue deals without expiry language are almost always recurring
    if text.strip():
        return "Ongoing"
    return "Unknown"


# ── Psychological motivator derivation ──────────────────────────────────────
# Rules proven from 364-record gold standard (see DEVLOG [13]):
#   Early Entry  → Urgency  (100%, n=74)  — must arrive before time cutoff
#   Live Music   → Social   (96%,  n=77)  — shared live experience
#   Group Booking→ Social   (100%, n=24)  — bring a group
#   Happy Hour   → Value    (100%, n=21)  — price savings on drinks
#   Matinee Deal → Value    (100%, n=23)  — off-peak price reduction
#   Discount     → Value                  — price reduction
#   Free         → Free                   — zero cost
# Additional rule (user-specified): Discount/Happy Hour + explicit time frame → FOMO

_CATEGORY_MOTIVATOR = {
    "Happy Hour":    "Value",    # base: save money; upgrades to FOMO if time-bound
    "Discount":      "Value",    # base: save money; upgrades to FOMO if time-bound
    "Matinee Deal":  "Value",    # off-peak price reduction
    "Free":          "Free",     # zero cost, no financial risk
    "Early Entry":   "FOMO",     # must arrive before time cutoff (gold: Urgency 100%)
    "Live Music":    "Social",   # shared live experience (gold: Free/Social 96%)
    "Group Booking": "Social",   # designed for groups (gold: Group/Value 100%)
}

# Time-frame signals that upgrade Value → FOMO for discount-type categories
_TIME_FRAME_PATTERN = re.compile(
    r"\b(mon|tue|wed|thu|fri|sat|sun|daily|nightly|weekday|weekend|"
    r"\d{1,2}(:\d{2})?\s*(am|pm)|every\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday|week|night|day))\b",
    re.IGNORECASE,
)


def derive_motivator(category: str, text: str) -> str:
    """
    Return motivator label using gold-standard-proven category rules.
    Discounts/Happy Hours with an explicit time frame become FOMO —
    the deal only exists within a window, creating urgency to act.
    """
    lower = text.lower()

    # Explicit scarcity/urgency language always wins
    if re.search(r"\b(limited time|tonight only|today only|last chance|selling fast|few left|exclusive event)\b", lower):
        return "FOMO"

    base = _CATEGORY_MOTIVATOR.get(category, "Value")

    # Discount-type categories with a time frame → FOMO
    if base == "Value" and category in ("Happy Hour", "Discount", "Matinee Deal"):
        if _TIME_FRAME_PATTERN.search(text):
            return "FOMO"

    return base


def empty_result(note: str) -> dict:
    return {
        "category":         "No Incentive",
        "teaser":           "No incentive found",
        "description":      "No incentive found",
        "timing":           "Unknown",
        "motivator":        "Unknown",
        "cuisine":          "Unknown",
        "value":            "Unknown",
        "status":           "Unknown",
        "notes":            note,
        "model_confidence": 0.0,
        "all_predictions":  [],
        "source":           "no_result",
    }
