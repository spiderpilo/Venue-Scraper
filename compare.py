"""
Compare original/presplit ground truth vs ML model output.

Shows per-venue field diffs plus two accuracy scores:
  • Exact  — model label must match presplit label exactly
  • Broad  — both are mapped to a common parent before comparing

Usage:
    python compare.py
    python compare.py --original data/processed/venues.json \
                      --model    data/model_output/model_venues.json
"""

import argparse
import json

# ── label mappings ────────────────────────────────────────────────────────────

# Presplit fine-grained → broad model label (same map used in trainmodel.py)
PRESPLIT_TO_BROAD = {
    # Live Music
    "Live Music": "Live Music", "Free Live Music": "Live Music",
    "Live Music Nights": "Live Music", "Summer Concert Series": "Live Music",
    "Free Concert Series": "Live Music", "Free Concert Nights": "Live Music",
    "Free Entertainment": "Live Music", "Free Music": "Live Music",
    "Free Show Entry": "Live Music", "Happy Hour Show": "Live Music",
    "Live Music Happy Hour": "Live Music", "Free Street Events": "Live Music",
    # Early Entry
    "Early Entry": "Early Entry", "Early Entry + Drink": "Early Entry",
    # Group Booking
    "Group Booking": "Group Booking", "Group Discount": "Group Booking",
    "Group Rental": "Group Booking", "Group Tour": "Group Booking",
    "Group Dive": "Group Booking", "Group Deal": "Group Booking",
    "Group Charter": "Group Booking", "Group Friendly": "Group Booking",
    # Matinee Deal
    "Matinee Deal": "Matinee Deal", "Twilight Ticket": "Matinee Deal",
    "Twilight Admission": "Matinee Deal", "Twilight Deal": "Matinee Deal",
    # Happy Hour
    "Happy Hour": "Happy Hour", "Taco Tuesday": "Happy Hour",
    "Lunch Special": "Happy Hour", "Lunch Bento": "Happy Hour",
    "Afternoon Deal": "Happy Hour", "Early Bird Dining": "Happy Hour",
    "Lunch Bowl Deal": "Happy Hour", "Lunch Combo": "Happy Hour",
    "Early Bird Dinner": "Happy Hour",
    # Free
    "Free": "Free", "Free Day": "Free", "Free Hot Dog Day": "Free",
    "Free Root Beer Float Day": "Free", "Pay What You Can": "Free",
    "Slurpee Deal": "Free", "Family Deal": "Free",
    "Free Events": "Free", "Free Community Event": "Free",
    "Free Tour Day": "Free", "Free Entry": "Free",
    # Discount
    "Discount": "Discount", "Early Bird Ticket": "Discount",
    "Early Bird": "Discount", "Combo Deal": "Discount",
    "Night Strike": "Discount", "Discount Days": "Discount",
    "Unlimited Bowling": "Discount", "Tasting Deal": "Discount",
    "Unlimited Play": "Discount", "After Hours": "Discount",
    "Player Reward": "Discount", "Day Pass": "Discount",
    "First Time Discount": "Discount", "24-Hour Access": "Discount",
    "Military Discount": "Discount", "After 3 PM Deal": "Discount",
    "Ride Wristband": "Discount", "Student Discount": "Discount",
    "Hiking Deal": "Discount", "Night Strike + Food": "Discount",
    "Unlimited Play Package": "Discount", "Secret Menu Deal": "Discount",
    "Unlimited Jump": "Discount",
    # No Incentive
    "No Incentive": "No Incentive",
}

COMPARE_FIELDS = [
    "Incentive Category",
    "Cuisine / Experience Category",
    "Days / Timing Restrictions",
    "Group Friendly?",
    "Psychological Motivator Type",
    "Estimated Perceived Value ($ range)",
    "Expiration / Ongoing",
]

UNKNOWN_VALUES = {"unknown", "", "needs extraction", "no incentive found", "—"}


# ── helpers ───────────────────────────────────────────────────────────────────

def load_json(path):
    with open(path) as f:
        content = f.read()
    try:
        data = json.loads(content)
        if isinstance(data, list):
            return [v for v in data if isinstance(v, dict)]
        return [data]
    except json.JSONDecodeError:
        decoder, pos, out = json.JSONDecoder(), 0, []
        while pos < len(content):
            stripped = content[pos:].lstrip()
            if not stripped:
                break
            skip = len(content[pos:]) - len(stripped)
            try:
                obj, end = decoder.raw_decode(stripped)
                pos = pos + skip + end
                if isinstance(obj, list):
                    out.extend(v for v in obj if isinstance(v, dict))
                elif isinstance(obj, dict):
                    out.append(obj)
            except Exception:
                break
        return out


def index_by_id(records):
    return {r["venue_id"]: r for r in records if r.get("venue_id")}


def trunc(s, n=36):
    s = str(s or "—")
    return s[:n] + "…" if len(s) > n else s


def field_flag(orig, model, field):
    a = str(orig.get(field) or "").strip().lower()
    b = str(model.get(field) or "").strip().lower()
    if a in UNKNOWN_VALUES and b in UNKNOWN_VALUES:
        return "~"
    return "✓" if a == b else "✗"


def broad(label):
    return PRESPLIT_TO_BROAD.get(str(label or "").strip(), None)


# ── main ─────────────────────────────────────────────────────────────────────

def compare(original_path, model_path):
    originals = load_json(original_path)
    models    = load_json(model_path)

    orig_idx  = index_by_id(originals)
    model_idx = index_by_id(models)

    common_ids = [r["venue_id"] for r in models if r.get("venue_id") in orig_idx]
    if not common_ids:
        print("No matching venue_ids between the two files.")
        return

    print("\n" + "=" * 74)
    print("  VENUE-BY-VENUE COMPARISON")
    print(f"  Reference : {original_path}")
    print(f"  Model     : {model_path}")
    print("=" * 74)

    total_fields = matched_fields = 0
    cat_rows = []

    for vid in common_ids:
        orig  = orig_idx[vid]
        model = model_idx[vid]
        name  = model.get("venue_name", vid)
        meta  = model.get("_meta", {})
        conf  = meta.get("model_confidence", 0.0)
        chars = meta.get("text_chars", 0)
        st    = meta.get("scrape_time_s", 0)
        it    = meta.get("inference_time_s", 0)

        orig_cat  = orig.get("Incentive Category", "")
        model_cat = model.get("Incentive Category", "")
        broad_orig  = broad(orig_cat)
        broad_model = broad(model_cat)
        exact_match = str(orig_cat).strip().lower() == str(model_cat).strip().lower()
        broad_match = (broad_orig is not None and broad_orig == broad_model)

        print(f"\n  {'─'*70}")
        print(f"  {name}")
        print(f"  conf={conf:.2f}  |  {chars:,} chars  |  scrape {st}s  |  infer {it}s")
        print(f"  {'─'*70}")
        print(f"  {'Field':<34} {'Reference':<22} {'Model':<22} {'?':>2}")
        print(f"  {'─'*34} {'─'*22} {'─'*22} {'─'*2}")

        for field in COMPARE_FIELDS:
            flag = field_flag(orig, model, field)
            if flag == "✓":
                matched_fields += 1
                total_fields += 1
            elif flag == "✗":
                total_fields += 1
            ov = trunc(orig.get(field), 22)
            mv = trunc(model.get(field), 22)
            print(f"  {field:<34} {ov:<22} {mv:<22} {flag:>2}")

        # Category line with broad annotation
        exact_sym = "✓ exact" if exact_match else ("~ broad" if broad_match else "✗")
        print()
        print(f"  Category  ref   : {orig_cat}  →  broad: {broad_orig or '?'}")
        print(f"  Category  model : {model_cat}  →  broad: {broad_model or '?'}   [{exact_sym}]")
        print(f"  Teaser    ref   : {trunc(orig.get('Incentive Teaser'), 64)}")
        print(f"  Teaser    model : {trunc(model.get('Incentive Teaser'), 64)}")
        print(f"  Desc      ref   : {trunc(orig.get('Full Incentive Description'), 64)}")
        print(f"  Desc      model : {trunc(model.get('Full Incentive Description'), 64)}")

        cat_rows.append({
            "name": name, "orig_cat": orig_cat, "model_cat": model_cat,
            "broad_orig": broad_orig, "broad_model": broad_model,
            "exact": exact_match, "broad": broad_match,
            "conf": conf, "chars": chars,
        })

    # ── summary ──────────────────────────────────────────────────────────────
    n = len(cat_rows)
    exact_n = sum(1 for r in cat_rows if r["exact"])
    broad_n = sum(1 for r in cat_rows if r["broad"])
    field_pct = matched_fields / total_fields * 100 if total_fields else 0
    # Exclude venues where model returned "No Incentive" due to failed scrape
    scraped = [r for r in cat_rows if r["chars"] > 0]
    scraped_exact = sum(1 for r in scraped if r["exact"])
    scraped_broad = sum(1 for r in scraped if r["broad"])

    print("\n\n" + "=" * 74)
    print("  SUMMARY")
    print("=" * 74)
    print(f"  Venues compared           : {n}")
    print(f"  Field agreement (excl ~)  : {matched_fields}/{total_fields}  ({field_pct:.0f}%)")
    print()
    print(f"  Category — exact match    : {exact_n}/{n}  ({exact_n/n*100:.0f}%)")
    print(f"  Category — broad match    : {broad_n}/{n}  ({broad_n/n*100:.0f}%)")
    if scraped:
        print(f"  Category — exact (scraped): {scraped_exact}/{len(scraped)}  ({scraped_exact/len(scraped)*100:.0f}%)")
        print(f"  Category — broad (scraped): {scraped_broad}/{len(scraped)}  ({scraped_broad/len(scraped)*100:.0f}%)")
    print()
    print(f"  {'Venue':<40} {'Ref':<16} {'Model':<16} {'Broad ref':<14} {'Broad mdl':<14} {'Conf':>5}  Match")
    print(f"  {'─'*40} {'─'*16} {'─'*16} {'─'*14} {'─'*14} {'─'*5}  {'─'*5}")
    for r in cat_rows:
        exact_sym = "✓ exact" if r["exact"] else ("~ broad" if r["broad"] else "✗")
        print(
            f"  {r['name'][:39]:<40}"
            f" {r['orig_cat'][:15]:<16}"
            f" {r['model_cat'][:15]:<16}"
            f" {(r['broad_orig'] or '?')[:13]:<14}"
            f" {(r['broad_model'] or '?')[:13]:<14}"
            f" {r['conf']:>5.2f}"
            f"  {exact_sym}"
        )
    print("=" * 74 + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--original", default="data/processed/json_batches_combined_presplit.json",
    )
    parser.add_argument("--model", default="data/model_output/model_venues.json")
    args = parser.parse_args()
    compare(args.original, args.model)
