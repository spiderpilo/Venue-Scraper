import os
import re
import json
import numpy as np
import pandas as pd
import tensorflow as tf
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder
from sklearn.utils.class_weight import compute_class_weight
from sklearn.metrics import classification_report

PRESPLIT_PATH   = "data/processed/json_batches_combined_presplit.json"
PIPELINE_GLOB   = "data/model_output/*.json"
RELABELED_GLOB  = "data/relabeled/*.json"
MODEL_PATH      = "models/incentive_model.keras"
LABELS_CAT     = "models/labels_category.txt"
LABELS_MOT     = "models/labels_motivator.txt"
LABELS_CUI     = "models/labels_cuisine.txt"
BTYPE_VOCAB    = "models/btype_vocab.txt"

MAX_TOKENS = 15000
SEQ_LEN    = 80
EMBED_DIM  = 128
LSTM_UNITS = 64
EPOCHS     = 40
BATCH_SIZE = 16

# ── Label maps ────────────────────────────────────────────────────────────────

# Fine-grained Incentive Category → 8 broad labels
CATEGORY_MAP = {
    "Live Music": "Live Music", "Free Live Music": "Live Music",
    "Live Music Nights": "Live Music", "Summer Concert Series": "Live Music",
    "Free Concert Series": "Live Music", "Free Concert Nights": "Live Music",
    "Free Entertainment": "Live Music", "Free Music": "Live Music",
    "Free Show Entry": "Live Music", "Happy Hour Show": "Live Music",
    "Live Music Happy Hour": "Live Music", "Free Street Events": "Live Music",
    "Early Entry": "Early Entry", "Early Entry + Drink": "Early Entry",
    "Group Booking": "Group Booking", "Group Discount": "Group Booking",
    "Group Rental": "Group Booking", "Group Tour": "Group Booking",
    "Group Dive": "Group Booking", "Group Deal": "Group Booking",
    "Group Charter": "Group Booking",
    "Matinee Deal": "Matinee Deal", "Twilight Ticket": "Matinee Deal",
    "Twilight Admission": "Matinee Deal", "Twilight Deal": "Matinee Deal",
    "Happy Hour": "Happy Hour", "Taco Tuesday": "Happy Hour",
    "Lunch Special": "Happy Hour", "Lunch Bento": "Happy Hour",
    "Afternoon Deal": "Happy Hour", "Early Bird Dining": "Happy Hour",
    "Lunch Bowl Deal": "Happy Hour", "Lunch Combo": "Happy Hour",
    "Early Bird Dinner": "Happy Hour",
    "Free Day": "Free", "Free Hot Dog Day": "Free",
    "Free Root Beer Float Day": "Free", "Pay What You Can": "Free",
    "Slurpee Deal": "Free", "Family Deal": "Free",
    "Free Events": "Free", "Free Community Event": "Free",
    "Free Tour Day": "Free", "Free Entry": "Free",
    "Early Bird Ticket": "Discount", "Early Bird": "Discount",
    "Combo Deal": "Discount", "Night Strike": "Discount",
    "Discount Days": "Discount", "Unlimited Bowling": "Discount",
    "Tasting Deal": "Discount", "Unlimited Play": "Discount",
    "After Hours": "Discount", "Player Reward": "Discount",
    "Day Pass": "Discount", "First Time Discount": "Discount",
    "24-Hour Access": "Discount", "Military Discount": "Discount",
    "After 3 PM Deal": "Discount", "Ride Wristband": "Discount",
    "Student Discount": "Discount", "Hiking Deal": "Discount",
    "Night Strike + Food": "Discount", "Unlimited Play Package": "Discount",
    "Secret Menu Deal": "Discount", "Unlimited Jump": "Discount",
    "No Incentive": "No Incentive",
    # Pass-through for Claude-produced labels
    "Discount": "Discount", "Free": "Free",
    "Happy Hour": "Happy Hour", "Live Music": "Live Music",
    "Early Entry": "Early Entry", "Group Booking": "Group Booking",
    "Matinee Deal": "Matinee Deal",
}

# Psychological Motivator → 5 consolidated classes
# Value     — price-based savings (discounts, happy hours, matinee pricing)
# Free      — zero cost, no financial risk (free admission, no cover)
# Exclusivity — special access or status (early entry, VIP, guest list)
# Social    — group/shared experience (group bookings, live music events)
# FOMO      — urgency or scarcity (limited time, tonight only, last chance)
MOTIVATOR_MAP = {
    "Value": "Value",
    "Value / Social": "Value",
    "Value / Scarcity": "Value",
    "Free / Social": "Free",
    "Urgency": "FOMO",
    "Group / Value": "Social",
    "Free / Scarcity": "Free",
    # Claude-produced variants
    "Social": "Social",
    "Savings": "Value",
    "Free": "Free",
    "Exclusivity": "Exclusivity",
    "FOMO": "FOMO",
    "Unknown": None,
}

# Business Type / Cuisine → 12 consolidated classes (used as model input feature)
VENUE_TYPE_MAP = {
    "Live Music Venue": "Live Music", "Live Music & Dining": "Live Music",
    "Live Music & Bar": "Live Music", "American / Live Music": "Live Music",
    "Live Music / American": "Live Music", "Live Music / Bar": "Live Music",
    "Live Music": "Live Music",
    "Nightclub": "Nightclub", "Nightclub & Dining": "Nightclub",
    "Nightclub / Bar": "Nightclub", "Dining & Nightclub": "Nightclub",
    "Nightclub & Bar": "Nightclub",
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
    "Dining & Live Music": "Dining", "Dining & Nightclub": "Dining",
    "American / Bar": "Dining", "American / Lounge": "Dining",
    "Hawaiian / Poke": "Dining", "Pizza / Casual Dining": "Dining",
    "Sandwiches / Cafe": "Dining", "Korean / Fast Casual": "Dining",
}
_VENUE_DEFAULT = "Other"

VALID_CATEGORIES  = set(CATEGORY_MAP.values()) - {None}
VALID_MOTIVATORS  = set(MOTIVATOR_MAP.values()) - {None}


def _map_venue_type(raw: str) -> str:
    return VENUE_TYPE_MAP.get(str(raw or "").strip(), _VENUE_DEFAULT)


def _map_category(raw: str) -> str | None:
    return CATEGORY_MAP.get(str(raw or "").strip())


def _map_motivator(raw: str) -> str | None:
    return MOTIVATOR_MAP.get(str(raw or "").strip())


# ── Data loading ──────────────────────────────────────────────────────────────

def load_presplit() -> pd.DataFrame:
    with open(PRESPLIT_PATH) as f:
        records = json.load(f)

    rows = []
    for r in records:
        cat = _map_category(r.get("Incentive Category", ""))
        mot = _map_motivator(r.get("Psychological Motivator Type", ""))
        if not cat or not mot:
            continue

        desc   = str(r.get("Full Incentive Description") or "").strip()
        teaser = str(r.get("Incentive Teaser") or "").strip()
        text   = desc if len(desc) >= len(teaser) else teaser
        if len(text) < 10:
            continue

        cui = _map_venue_type(r.get("Cuisine / Experience Category", ""))
        btype = _map_venue_type(r.get("Business Type", ""))

        rows.append({
            "text":     text,
            "category": cat,
            "motivator": mot,
            "cuisine":  cui,
            "btype":    btype,
            "source":   "presplit",
        })
    return pd.DataFrame(rows)


_POSITIVE_SOURCES = {"claude", "ml_model", "ml_model_fallback"}

_MAX_PIPELINE_NEG = 60  # cap real-scraped negatives — too many floods No Incentive class

def load_pipeline_outputs() -> pd.DataFrame:
    """Load labeled scraped text from pipeline run files.

    Positive rows: extraction_source in {claude, ml_model, ml_model_fallback},
                   scraped_text present.
    Negative rows: extraction_source == 'no_result', scraped_text present
                   and text_chars > 200 (real page, genuinely no incentive).
                   Capped at _MAX_PIPELINE_NEG to avoid flooding No Incentive.
    """
    import glob
    pos_rows = []
    neg_rows = []
    for path in glob.glob(PIPELINE_GLOB):
        try:
            with open(path) as f:
                records = json.load(f)
        except Exception:
            continue

        for r in records:
            meta  = r.get("_meta", {})
            text  = meta.get("scraped_text", "")
            src   = meta.get("extraction_source", "")
            chars = meta.get("text_chars", 0)

            if not text or len(text) < 50:
                continue

            if src in _POSITIVE_SOURCES:
                cat = _map_category(r.get("Incentive Category", ""))
                mot = _map_motivator(r.get("Psychological Motivator Type", ""))
                if not cat or not mot:
                    continue
                pos_rows.append({
                    "text":     text[:2000],
                    "category": cat,
                    "motivator": mot,
                    "cuisine":  _map_venue_type(r.get("Cuisine / Experience Category", "")),
                    "btype":    _map_venue_type(r.get("Business Type", "")),
                    "source":   "pipeline",
                })

            elif src == "no_result" and chars > 200:
                neg_rows.append({
                    "text":     text[:2000],
                    "category": "No Incentive",
                    "motivator": "Value",
                    "cuisine":  _map_venue_type(r.get("Business Type", "")),
                    "btype":    _map_venue_type(r.get("Business Type", "")),
                    "source":   "pipeline_neg",
                })

    # Cap negatives to avoid class imbalance regression (v3 lesson)
    import random
    random.seed(42)
    if len(neg_rows) > _MAX_PIPELINE_NEG:
        neg_rows = random.sample(neg_rows, _MAX_PIPELINE_NEG)

    rows = pos_rows + neg_rows
    return pd.DataFrame(rows) if rows else pd.DataFrame(
        columns=["text", "category", "motivator", "cuisine", "btype", "source"]
    )


def _synthetic_no_incentive() -> pd.DataFrame:
    """Hand-written venue website snippets that contain zero incentive content.

    These cover common boilerplate patterns the model will encounter at
    inference time so it learns NOT to over-fire on generic venue text.
    """
    examples = [
        # Hours / location
        "We are open Monday through Friday 11am to 10pm and Saturday Sunday 10am to 11pm.",
        "Located at 450 Main Street downtown. Free parking available in the adjacent garage.",
        "Our doors open at 5pm Tuesday through Sunday. Closed on Mondays.",
        "Reservations recommended. Walk-ins welcome based on availability.",
        "Find us at the corner of Broadway and 5th. Validated parking in the structure next door.",
        "Hours vary by season. Please check our website or call ahead before visiting.",
        "We are closed on Thanksgiving Christmas and New Year's Day.",
        # About / mission
        "Family owned and operated since 1987 serving the local community with pride.",
        "Award-winning cuisine crafted from locally sourced seasonal ingredients.",
        "Our team of dedicated professionals is committed to exceptional guest experiences.",
        "We pride ourselves on warm hospitality and attention to every detail.",
        "Celebrating over 30 years of bringing people together through great food and atmosphere.",
        "Our chefs trained in classical technique bring a modern twist to every dish.",
        # Menu descriptions
        "Featuring an extensive menu of craft beers wines and handcrafted cocktails.",
        "Our menu changes seasonally to highlight the freshest local produce.",
        "Gluten-free and vegan options available upon request. Ask your server for details.",
        "Try our signature house burger topped with aged cheddar and caramelized onions.",
        "Brunch served every Saturday and Sunday from 10am to 3pm.",
        "Full bar service available. Ask your server about our wine list.",
        # Events / general
        "Private events and corporate bookings available. Contact us for pricing.",
        "We host birthday parties anniversaries and corporate events in our private dining room.",
        "Follow us on Instagram and Facebook for updates on new menu items.",
        "Gift cards available for purchase at the front desk or online.",
        "Check our website for upcoming events and live entertainment schedules.",
        "We are committed to providing a safe and welcoming environment for all guests.",
        # Generic attraction copy
        "Explore our collection of over 200 interactive exhibits for all ages.",
        "Guided tours available daily at 10am 1pm and 3pm.",
        "Accessible to guests with mobility needs. Please notify staff upon arrival.",
        "Group rates available for parties of 15 or more. Advance booking required.",
        "Educational programs available for school groups. Contact our education department.",
        "Our facility features state-of-the-art equipment and experienced instructors.",
        # Nightclub / bar boilerplate
        "Must be 21 or older to enter. Valid government-issued ID required.",
        "Dress code enforced. No athletic wear or open-toed shoes for men.",
        "Management reserves the right to refuse entry.",
        "Located in the heart of the entertainment district.",
        "VIP bottle service available. Contact our reservations team for details.",
        "Table reservations fill up fast. Book early to secure your spot.",
        # Bowling / entertainment
        "Bumper bowling available for children under 6. Shoe rentals included.",
        "Arcade games laser tag and mini golf available in addition to bowling lanes.",
        "Lane reservations recommended on weekends. Walk-ins available during weekdays.",
        "State-of-the-art automatic scoring system on all lanes.",
        # Spa / wellness
        "All services require advance booking. Cancellations within 24 hours may incur a fee.",
        "Gift certificates available in any denomination. Perfect for any occasion.",
        "Our licensed therapists specialize in deep tissue Swedish and hot stone massage.",
        # Museum / theater
        "Free admission for members. Membership starts at $50 per year.",
        "Advance tickets recommended for popular exhibitions. Purchase online to skip the line.",
        "Photography permitted in most galleries. Flash photography prohibited.",
        "Our box office is open one hour before each performance.",
        "Latecomers will be seated at suitable breaks in the performance.",
    ]

    rows = []
    for text in examples:
        rows.append({
            "text":     text,
            "category": "No Incentive",
            "motivator": "Value",
            "cuisine":  "Other",
            "btype":    "Other",
            "source":   "synthetic_neg",
        })
    return pd.DataFrame(rows)


def _synthetic_niche_positives() -> pd.DataFrame:
    """Hand-written incentive examples for underrepresented niche venue types.

    Museum, Movie Theater, Aquarium, Comedy Club, Casino, Theater are all
    low-count in the presplit and rarely appear in real scraped training data.
    These examples give the model enough signal to classify them correctly.
    """
    examples = [
        # ── Museum ────────────────────────────────────────────────────────────
        ("Free general admission every first Friday evening 5pm to 9pm.",
         "Free", "Free / Social", "Museum", "Museum"),
        ("Pay what you wish admission on select days throughout the year.",
         "Free", "Free / Social", "Museum", "Museum"),
        ("Members enjoy free unlimited admission plus 10% off in the gift shop.",
         "Discount", "Value", "Museum", "Museum"),
        ("Student and senior tickets available at half price with valid ID.",
         "Discount", "Value", "Museum", "Museum"),
        ("Group rates available for parties of 10 or more, 20% off regular admission.",
         "Group Booking", "Group / Value", "Museum", "Museum"),
        ("Twilight admission after 4pm is $8, regular price is $15.",
         "Matinee Deal", "Value", "Museum", "Museum"),
        ("Free admission for children under 3. Kids ages 3-12 just $5.",
         "Free", "Free / Social", "Museum", "Museum"),

        # ── Movie Theater ──────────────────────────────────────────────────────
        ("Matinee showings before 4pm are only $8 per ticket.",
         "Matinee Deal", "Value", "Movie Theater", "Movie Theater"),
        ("Twilight tickets for shows starting between 4pm and 6pm are $10.",
         "Matinee Deal", "Value", "Movie Theater", "Movie Theater"),
        ("Senior tickets $7 every day. Student discount with valid ID.",
         "Discount", "Value", "Movie Theater", "Movie Theater"),
        ("$5 Tuesday tickets all day on Tuesdays for all shows.",
         "Discount", "Value", "Movie Theater", "Movie Theater"),
        ("Group rates for parties of 10 or more. Private screening packages available.",
         "Group Booking", "Group / Value", "Movie Theater", "Movie Theater"),
        ("Loyalty rewards members earn points toward free tickets.",
         "Discount", "Value", "Movie Theater", "Movie Theater"),
        ("Early bird shows before noon are just $6.",
         "Matinee Deal", "Value", "Movie Theater", "Movie Theater"),

        # ── Aquarium ──────────────────────────────────────────────────────────
        ("Group discount of 15% for groups of 15 or more. Advance booking required.",
         "Group Booking", "Group / Value", "Aquarium", "Aquarium"),
        ("Members enjoy free unlimited visits plus 10% off gift shop purchases.",
         "Discount", "Value", "Aquarium", "Aquarium"),
        ("Free admission for children under 2. Kids 2-12 receive discounted pricing.",
         "Free", "Free / Social", "Aquarium", "Aquarium"),
        ("Twilight tickets available after 4pm at reduced pricing.",
         "Matinee Deal", "Value", "Aquarium", "Aquarium"),
        ("Annual membership pays for itself in just 2 visits.",
         "Discount", "Value", "Aquarium", "Aquarium"),
        ("Birthday party packages available for groups of 10 or more.",
         "Group Booking", "Group / Value", "Aquarium", "Aquarium"),

        # ── Comedy Club ────────────────────────────────────────────────────────
        ("Two-drink minimum included with ticket purchase. Happy hour pricing before 8pm.",
         "Happy Hour", "Value", "Comedy Club", "Comedy Club"),
        ("Group packages available for parties of 10 or more including priority seating.",
         "Group Booking", "Group / Value", "Comedy Club", "Comedy Club"),
        ("Early show tickets are $5 less than late show prices.",
         "Matinee Deal", "Value", "Comedy Club", "Comedy Club"),
        ("Happy hour drinks from 6pm to 8pm during early shows.",
         "Happy Hour", "Value", "Comedy Club", "Comedy Club"),
        ("Student and military discount available at the box office with valid ID.",
         "Discount", "Value", "Comedy Club", "Comedy Club"),
        ("Free entry for open mic nights every Tuesday, two-drink minimum.",
         "Free", "Free / Social", "Comedy Club", "Comedy Club"),
        ("No cover charge Sunday through Thursday nights.",
         "Free", "Free / Social", "Comedy Club", "Comedy Club"),

        # ── Casino ─────────────────────────────────────────────────────────────
        ("Players Club members receive free play credits and dining discounts.",
         "Discount", "Value", "Casino", "Casino"),
        ("Happy hour at the casino bar daily from 4pm to 7pm, $3 domestic beers.",
         "Happy Hour", "Value", "Casino", "Casino"),
        ("New members receive $25 in free play when they sign up for the rewards card.",
         "Free", "Free / Social", "Casino", "Casino"),
        ("Group event packages available for corporate outings and private parties.",
         "Group Booking", "Group / Value", "Casino", "Casino"),
        ("Early bird specials in the buffet from 11am to 1pm, 20% off regular price.",
         "Matinee Deal", "Value", "Casino", "Casino"),
        ("Senior Tuesdays: earn double points on all slot play every Tuesday.",
         "Discount", "Value", "Casino", "Casino"),

        # ── Theater ────────────────────────────────────────────────────────────
        ("Rush tickets available 30 minutes before curtain at 50% off.",
         "Discount", "Urgency", "Theater", "Theater"),
        ("Student rush tickets available with valid ID, subject to availability.",
         "Discount", "Value", "Theater", "Theater"),
        ("Group discounts available for parties of 10 or more, save up to 20%.",
         "Group Booking", "Group / Value", "Theater", "Theater"),
        ("Matinee performances on Wednesday and Sunday afternoons are discounted.",
         "Matinee Deal", "Value", "Theater", "Theater"),
        ("Early bird tickets purchased 2 weeks in advance receive 15% off.",
         "Discount", "Value", "Theater", "Theater"),
        ("Pay-what-you-can previews available for select performances.",
         "Free", "Free / Social", "Theater", "Theater"),
        ("Members enjoy presale access and 10% off all ticket purchases.",
         "Discount", "Value", "Theater", "Theater"),
        ("Half-price tickets available at the box office one hour before showtime.",
         "Discount", "Urgency", "Theater", "Theater"),

        # ── Bowling ────────────────────────────────────────────────────────────
        ("Cosmic bowling every Friday and Saturday night, $5 per game.",
         "Discount", "Value", "Bowling", "Bowling"),
        ("Unlimited bowling every Sunday from 10am to 2pm for $12 per person.",
         "Discount", "Value", "Bowling", "Bowling"),
        ("Group birthday party packages start at $12 per person, shoes included.",
         "Group Booking", "Group / Value", "Bowling", "Bowling"),
        ("Senior bowling league Tuesdays and Thursdays, discounted lane rates.",
         "Discount", "Value", "Bowling", "Bowling"),
        ("Kids bowl free on weekday mornings during summer.",
         "Free", "Free / Social", "Bowling", "Bowling"),
    ]

    rows = []
    for text, cat, mot, cui, btype in examples:
        rows.append({
            "text":     text,
            "category": cat,
            "motivator": mot,
            "cuisine":  cui,
            "btype":    btype,
            "source":   "synthetic_pos",
        })
    return pd.DataFrame(rows)


def _ascii_clean(text: str) -> str:
    text = text.encode("ascii", errors="ignore").decode("ascii")
    # Normalize all whitespace (including \n \r \t) to single spaces —
    # embedded newlines in scraped text corrupt the TextVectorization vocab file.
    text = re.sub(r'\s+', ' ', text)
    # Collapse runs of 5+ space-separated single characters (JS scraper artifact,
    # e.g. "S u n d a y , A p r i l 2 7").
    text = re.sub(r'\b\w(?:\s\w){4,}\b', ' ', text)
    return re.sub(r' {2,}', ' ', text).strip()


def _has_spaced_chars(text: str) -> bool:
    """True when >35% of tokens are single alpha chars — indicates corrupted scrape."""
    tokens = text.split()
    if len(tokens) < 20:
        return False
    ratio = sum(1 for t in tokens if len(t) == 1 and t.isalpha()) / len(tokens)
    return ratio > 0.35


def load_relabeled() -> pd.DataFrame:
    """Load Claude-relabeled records from data/relabeled/.

    Only loads positive (non-No Incentive) corrections — we already have
    enough No Incentive signal from synthetic examples and pipeline negatives.
    Adding relabeled negatives over-weights that class and makes the model
    too conservative.
    """
    import glob
    rows = []
    for path in glob.glob(RELABELED_GLOB):
        try:
            with open(path, encoding="utf-8") as f:
                records = json.load(f)
        except Exception:
            continue
        for r in records:
            meta  = r.get("_meta", {})
            text  = meta.get("scraped_text", "")
            if not text or len(text) < 50:
                continue
            cat = _map_category(r.get("Incentive Category", ""))
            if cat == "No Incentive":
                continue  # skip — negatives already covered by synthetic + pipeline_neg
            mot = _map_motivator(r.get("Psychological Motivator Type", ""))
            if not cat or not mot:
                continue
            rows.append({
                "text":     text[:2000],
                "category": cat,
                "motivator": mot,
                "cuisine":  _map_venue_type(r.get("Cuisine / Experience Category", "")),
                "btype":    _map_venue_type(r.get("Business Type", "")),
                "source":   "relabeled",
            })
    return pd.DataFrame(rows) if rows else pd.DataFrame(
        columns=["text", "category", "motivator", "cuisine", "btype", "source"]
    )


def load_dataset() -> pd.DataFrame:
#^ Run only the dataset loader & print class counts
#^ View model_test.ipynb
    frames = [load_presplit(), load_pipeline_outputs(), load_relabeled(),
              _synthetic_no_incentive(), _synthetic_niche_positives()]
    df = pd.concat(frames, ignore_index=True)
    df = df.dropna(subset=["text", "category", "motivator"])
    df["text"]  = df["text"].astype(str).str.strip().apply(_ascii_clean)
    df["btype"] = df["btype"].fillna(_VENUE_DEFAULT)
    df = df[df["text"].str.len() >= 10]
    # Drop rows where JS scraper produced space-separated single characters
    before = len(df)
    df = df[~df["text"].apply(_has_spaced_chars)]
    dropped = before - len(df)
    if dropped:
        print(f"  [clean] Dropped {dropped} rows with space-separated single-char tokens")
    return df


# ── Model ─────────────────────────────────────────────────────────────────────

def build_model(vectorizer, btype_lookup, n_cat, n_mot, n_cui, btype_vocab_size):
    text_in  = tf.keras.Input(shape=(1,), dtype=tf.string,  name="text")
    btype_in = tf.keras.Input(shape=(1,), dtype=tf.string,  name="business_type")

    # Text pathway
    x = vectorizer(text_in)
    x = tf.keras.layers.Embedding(MAX_TOKENS, EMBED_DIM, mask_zero=True)(x)
    x = tf.keras.layers.Bidirectional(tf.keras.layers.LSTM(LSTM_UNITS, return_sequences=True))(x)
    x = tf.keras.layers.Bidirectional(tf.keras.layers.LSTM(LSTM_UNITS // 2))(x)

    # Business-type pathway (small embedding)
    b = btype_lookup(btype_in)
    b = tf.keras.layers.Embedding(btype_vocab_size + 2, 8)(b)
    b = tf.keras.layers.Flatten()(b)

    # Shared trunk
    merged = tf.keras.layers.Concatenate()([x, b])
    shared = tf.keras.layers.Dense(64, activation="relu")(merged)
    shared = tf.keras.layers.Dropout(0.4)(shared)

    # Three output heads
    cat_out = tf.keras.layers.Dense(n_cat, activation="softmax", name="category")(shared)
    mot_out = tf.keras.layers.Dense(n_mot, activation="softmax", name="motivator")(shared)
    cui_out = tf.keras.layers.Dense(n_cui, activation="softmax", name="cuisine")(shared)

    model = tf.keras.Model(
        inputs={"text": text_in, "business_type": btype_in},
        outputs={"category": cat_out, "motivator": mot_out, "cuisine": cui_out},
    )
    return model


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    df = load_dataset()

    print(f"Total training rows : {len(df)}")
    print(f"  from presplit     : {(df['source']=='presplit').sum()}")
    print(f"  from pipeline     : {(df['source']=='pipeline').sum()}")
    print(f"  from relabeled    : {(df['source']=='relabeled').sum()}")
    print(f"  synthetic neg     : {(df['source']=='synthetic_neg').sum()}")
    print(f"  synthetic pos     : {(df['source']=='synthetic_pos').sum()}")
    print()
    for col in ["category", "motivator", "cuisine"]:
        print(f"--- {col} ---")
        print(df[col].value_counts().to_string())
        print()

    # ── Encode labels ──────────────────────────────────────────────────────────
    le_cat = LabelEncoder(); y_cat = le_cat.fit_transform(df["category"]).astype("int32")
    le_mot = LabelEncoder(); y_mot = le_mot.fit_transform(df["motivator"]).astype("int32")
    le_cui = LabelEncoder(); y_cui = le_cui.fit_transform(df["cuisine"]).astype("int32")

    texts  = df["text"].tolist()
    btypes = df["btype"].tolist()

    # ── Train/test split ───────────────────────────────────────────────────────
    idx = np.arange(len(df))
    train_idx, test_idx = train_test_split(idx, test_size=0.2, random_state=42, stratify=y_cat)

    X_train_text  = [texts[i]  for i in train_idx]
    X_test_text   = [texts[i]  for i in test_idx]
    X_train_btype = [btypes[i] for i in train_idx]
    X_test_btype  = [btypes[i] for i in test_idx]
    y_train_cat   = y_cat[train_idx]; y_test_cat = y_cat[test_idx]
    y_train_mot   = y_mot[train_idx]; y_test_mot = y_mot[test_idx]
    y_train_cui   = y_cui[train_idx]; y_test_cui = y_cui[test_idx]

    # ── Text vectorizer ────────────────────────────────────────────────────────
    vectorizer = tf.keras.layers.TextVectorization(
        max_tokens=MAX_TOKENS, output_mode="int", output_sequence_length=SEQ_LEN,
    )
    vectorizer.adapt(X_train_text)

    # Deduplicate vocabulary — embedded newlines in scraped text can produce
    # repeated empty-string tokens that break model save/load.
    _vocab = vectorizer.get_vocabulary()
    _seen, _unique = set(), []
    for _t in _vocab:
        if _t not in _seen:
            _seen.add(_t)
            _unique.append(_t)
    if len(_unique) < len(_vocab):
        print(f"  [vocab] Removed {len(_vocab) - len(_unique)} duplicate terms")
        vectorizer.set_vocabulary(_unique[2:], idf_weights=None)  # skip '' and [UNK] reserved slots

    # ── Business-type lookup ───────────────────────────────────────────────────
    btype_vocab = sorted(set(btypes))
    btype_lookup = tf.keras.layers.StringLookup(vocabulary=btype_vocab)

    # ── Datasets ───────────────────────────────────────────────────────────────
    def make_ds(texts, btypes, y_cat, y_mot, y_cui, shuffle=False):
        ds = tf.data.Dataset.from_tensor_slices((
            {"text": texts, "business_type": btypes},
            {"category": y_cat, "motivator": y_mot, "cuisine": y_cui},
        ))
        if shuffle:
            ds = ds.shuffle(1000)
        return ds.batch(BATCH_SIZE)

    train_ds = make_ds(X_train_text, X_train_btype, y_train_cat, y_train_mot, y_train_cui, shuffle=True)
    test_ds  = make_ds(X_test_text,  X_test_btype,  y_test_cat,  y_test_mot,  y_test_cui)

    # ── Class weights (category head only) ────────────────────────────────────
    cat_weights = compute_class_weight("balanced", classes=np.arange(len(le_cat.classes_)), y=y_train_cat)
    cat_weight_dict = dict(enumerate(cat_weights))
    print("Category class weights:", {le_cat.classes_[k]: round(v, 2) for k, v in cat_weight_dict.items()})

    # ── Build & compile ────────────────────────────────────────────────────────
    model = build_model(
        vectorizer, btype_lookup,
        n_cat=len(le_cat.classes_),
        n_mot=len(le_mot.classes_),
        n_cui=len(le_cui.classes_),
        btype_vocab_size=len(btype_vocab),
    )

    model.compile(
        optimizer=tf.keras.optimizers.Adam(1e-3),
        loss={
            "category": "sparse_categorical_crossentropy",
            "motivator": "sparse_categorical_crossentropy",
            "cuisine":   "sparse_categorical_crossentropy",
        },
        loss_weights={"category": 2.0, "motivator": 1.0, "cuisine": 1.0},
        metrics={"category": "accuracy", "motivator": "accuracy", "cuisine": "accuracy"},
    )

    model.fit(
        train_ds, epochs=EPOCHS, validation_data=test_ds,
        callbacks=[
            tf.keras.callbacks.EarlyStopping(
                monitor="val_category_accuracy", patience=6, restore_best_weights=True, mode="max",
            ),
            tf.keras.callbacks.ReduceLROnPlateau(
                monitor="val_loss", factor=0.5, patience=3, min_lr=1e-5,
            ),
        ],
        verbose=1,
    )

    # ── Evaluate ───────────────────────────────────────────────────────────────
    results = model.evaluate(test_ds, verbose=0)
    print()
    for name, val in zip(model.metrics_names, results):
        print(f"  {name:<40} {val:.4f}")

    # ── Save model + labels ────────────────────────────────────────────────────
    os.makedirs("models", exist_ok=True)
    model.save(MODEL_PATH)

    for path, le in [(LABELS_CAT, le_cat), (LABELS_MOT, le_mot), (LABELS_CUI, le_cui)]:
        with open(path, "w") as f:
            for lbl in le.classes_:
                f.write(lbl + "\n")

    with open(BTYPE_VOCAB, "w") as f:
        for v in btype_vocab:
            f.write(v + "\n")

    print(f"\nModel  -> {MODEL_PATH}")
    print(f"Labels -> {LABELS_CAT}, {LABELS_MOT}, {LABELS_CUI}")
    print(f"BType  -> {BTYPE_VOCAB}")

    # ── Classification reports ─────────────────────────────────────────────────
    preds = model.predict(test_ds, verbose=0)
    for head, le, y_true in [
        ("category", le_cat, y_test_cat),
        ("motivator", le_mot, y_test_mot),
        ("cuisine",   le_cui, y_test_cui),
    ]:
        y_pred = np.argmax(preds[head], axis=1)
        present = np.unique(y_true)
        print(f"\n--- {head} report ---")
        print(classification_report(
            y_true, y_pred,
            labels=present,
            target_names=le.classes_[present],
            zero_division=0,
        ))


if __name__ == "__main__":
    main()
