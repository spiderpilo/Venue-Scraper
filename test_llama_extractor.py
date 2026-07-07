"""
Test: compare Llama 3.2 3B incentive extraction vs current TF model output.

Sends raw scraped text to Llama and asks it to extract the incentive,
then compares side-by-side with what the TF model produced.

Usage:
    python test_llama_extractor.py
    python test_llama_extractor.py --model-output data/model_output/model_venues_2026-06-25_off0000.json
    python test_llama_extractor.py --limit 20
"""

import argparse
import json
import os
import time

import requests

OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "llama3.1:8b"
OUTPUT_DIR = "data/inspect"

CATEGORIES = [
    "Happy Hour", "Live Music", "Early Entry", "Discount",
    "Free", "Group Booking", "Matinee Deal", "No Incentive",
]

_PROMPT = """\
You are extracting promotional incentives from venue website text.

CATEGORY DEFINITIONS:
- Happy Hour: drink/food specials at specific times (e.g. "$5 beers 3-6pm", "half price appetizers")
- Early Entry: no cover charge, free/reduced admission before a certain time (e.g. "free before 10pm", "no cover on guest list")
- Live Music: live bands, DJs, concerts, open mic (e.g. "live jazz every Friday", "DJ Saturday nights")
- Discount: % off, reduced pricing, promo codes, loyalty rewards (e.g. "20% off Tuesdays", "student discount")
- Free: free admission, free events, free item (e.g. "free entry all night", "free hot dog day")
- Group Booking: group rates, party packages, private events (e.g. "groups of 10+ get 15% off")
- Matinee Deal: time-based admission pricing, twilight tickets (e.g. "matinee tickets $8 before 4pm")
- No Incentive: opening hours, address, phone number, general descriptions, menu items, boilerplate

EXAMPLES OF INCENTIVES (these have a category):
- "Join us for happy hour Monday-Friday 4-7pm, $5 wells and $6 craft beers" → Happy Hour, timing: Mon-Fri 4-7pm, value: $5
- "No cover charge before 10pm on Fridays and Saturdays" → Early Entry, timing: Fri-Sat before 10pm
- "Live music every Thursday night starting at 8pm, no cover" → Live Music, timing: Thursday 8pm
- "Twilight tickets available after 5pm for just $9" → Matinee Deal, timing: after 5pm, value: $9
- "Kids bowl free every Sunday morning" → Free, timing: Sunday morning
- "Group rates available for parties of 15 or more, 20% off" → Group Booking, value: 20% off

EXAMPLES OF NO INCENTIVE (these have no category):
- "Monday to Thursday 10am-9pm, Friday to Sunday 9am-9pm" → No Incentive (just hours)
- "Located at 450 Main Street. Call us at (310) 555-1234" → No Incentive (contact info)
- "Award-winning cuisine crafted from locally sourced seasonal ingredients" → No Incentive (marketing copy)
- "Must be 21 or older to enter. Valid ID required." → No Incentive (policy)
- "View Menu Reserve Now Welcome To Taqueria Las Milpas" → No Incentive (nav/homepage boilerplate)

Analyze the text below and extract the BEST incentive if one exists.
If the text only contains hours, location, menu items, or generic descriptions — return No Incentive.

Respond with JSON only, no explanation. Use this exact format:
{{
  "category": "<one of: Happy Hour | Live Music | Early Entry | Discount | Free | Group Booking | Matinee Deal | No Incentive>",
  "teaser": "<one sentence, max 10 words, describing the incentive. Empty string if No Incentive>",
  "timing": "<days and times the incentive applies, or Unknown>",
  "value": "<price or discount amount, e.g. $9 or 50% off, or Unknown>",
  "confidence": "<high | medium | low>"
}}

Venue type: {business_type}
Text:
{text}
"""


def _call_ollama(prompt: str, timeout: float = 30.0) -> dict | None:
    try:
        r = requests.post(
            OLLAMA_URL,
            json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
            timeout=timeout,
        )
        if r.status_code != 200:
            return None
        raw = r.json().get("response", "").strip()

        # Extract JSON from response
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start == -1 or end == 0:
            return None
        return json.loads(raw[start:end])
    except Exception as e:
        return None


def extract_with_llama(text: str, business_type: str = "") -> dict:
    if not text:
        return {
            "category": "No Incentive",
            "teaser": "No incentive found",
            "timing": "Unknown",
            "value": "Unknown",
            "confidence": "high",
        }

    prompt = _PROMPT.format(
        business_type=business_type or "Unknown",
        text=text[:3000],
    )

    result = _call_ollama(prompt)
    if not result:
        return {
            "category": "No Incentive",
            "teaser": "LLM call failed",
            "timing": "Unknown",
            "value": "Unknown",
            "confidence": "low",
        }

    # Validate category
    if result.get("category") not in CATEGORIES:
        result["category"] = "No Incentive"

    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-output", type=str,
                        default="data/model_output/model_venues_2026-06-25_off0000.json")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--output", type=str, default=None)
    args = parser.parse_args()

    if not os.path.exists(args.model_output):
        print(f"ERROR: {args.model_output} not found")
        return

    with open(args.model_output) as f:
        tf_results = json.load(f)

    # Only test venues where TF model found something (more interesting comparison)
    candidates = [r for r in tf_results if r["_meta"].get("scraped_text")]
    if args.limit:
        candidates = candidates[:args.limit]

    print(f"\nTesting Llama vs TF model on {len(candidates)} venues...\n")
    print(f"{'Venue':<30} {'TF Category':<15} {'Llama Category':<15} {'Match'}")
    print("-" * 75)

    results = []
    for r in candidates:
        name = r["venue_name"]
        btype = r.get("Business Type", "")
        text = r["_meta"].get("scraped_text", "")
        tf_category = r["Incentive Category"]
        tf_teaser = r["Incentive Teaser"]
        tf_value = r.get("Estimated Perceived Value ($ range)", "Unknown")
        tf_timing = r.get("Days / Timing Restrictions", "Unknown")

        t0 = time.time()
        llama = extract_with_llama(text, btype)
        elapsed = round(time.time() - t0, 2)

        match = "✓" if llama["category"] == tf_category else "✗"

        print(f"{name[:29]:<30} {tf_category:<15} {llama['category']:<15} {match}  ({elapsed}s)")

        results.append({
            "venue_name": name,
            "business_type": btype,
            "scraped_text_chars": len(text),
            "tf_model": {
                "category": tf_category,
                "teaser": tf_teaser,
                "value": tf_value,
                "timing": tf_timing,
                "confidence": r["_meta"].get("model_confidence", 0),
                "source": r["_meta"].get("extraction_source", ""),
            },
            "llama": {
                "category": llama.get("category"),
                "teaser": llama.get("teaser"),
                "value": llama.get("value"),
                "timing": llama.get("timing"),
                "confidence": llama.get("confidence"),
            },
            "category_match": llama["category"] == tf_category,
            "llama_inference_s": elapsed,
        })

    # Summary
    total = len(results)
    matches = sum(1 for r in results if r["category_match"])
    avg_time = sum(r["llama_inference_s"] for r in results) / total if total else 0

    print(f"\n{'='*75}")
    print(f"  Category agreement : {matches}/{total} ({100*matches//total}%)")
    print(f"  Avg Llama time     : {avg_time:.2f}s/venue")

    # Breakdown by category
    print(f"\n  Disagreements:")
    for r in results:
        if not r["category_match"]:
            print(f"    {r['venue_name'][:30]:<30} TF={r['tf_model']['category']:<15} Llama={r['llama']['category']}")
            print(f"      TF teaser   : {r['tf_model']['teaser'][:80]}")
            print(f"      Llama teaser: {r['llama']['teaser'][:80]}")

    # Save
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    out_file = args.output or f"llama_comparison_{time.strftime('%Y-%m-%d_%H%M')}.json"
    out_path = os.path.join(OUTPUT_DIR, out_file)
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"\n  Saved -> {out_path}")
    print(f"{'='*75}\n")


if __name__ == "__main__":
    main()
