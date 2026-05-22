"""
Re-label all pipeline output records that have scraped_text using Claude,
then save as a clean training file.

Usage:
    python -m src.relabel_pipeline
    python -m src.relabel_pipeline --input data/model_output/model_venues_2026-05-21.json
    python -m src.relabel_pipeline --glob "data/model_output/*.json"
"""

import argparse
import glob as glob_module
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.claude_extractor import extract_with_claude

OUTPUT_DIR = "data/relabeled"

MOTIVATOR_MAP = {
    "Live Music":    "Free / Social",
    "Early Entry":   "Urgency",
    "Group Booking": "Group / Value",
    "Matinee Deal":  "Value",
    "Happy Hour":    "Value",
    "Free":          "Free / Social",
    "Discount":      "Value",
    "No Incentive":  None,
}


def _default_motivator(category: str) -> str:
    return MOTIVATOR_MAP.get(category, "Value") or "Value"


def relabel(input_paths: list[str], output_path: str):
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    records = []
    for path in input_paths:
        try:
            with open(path, encoding="utf-8") as f:
                records.extend(json.load(f))
        except Exception as e:
            print(f"  skip {path}: {e}")

    # Only process records that have real scraped text
    eligible = [
        r for r in records
        if len(r.get("_meta", {}).get("scraped_text", "")) >= 100
    ]

    print(f"\nRecords total    : {len(records)}")
    print(f"Eligible (w/text): {len(eligible)}")
    print(f"Output           : {output_path}\n")

    results = []
    skipped = 0
    changed = 0

    for i, r in enumerate(eligible, 1):
        name      = r.get("venue_name", "?")
        btype     = r.get("Business Type", "")
        text      = r["_meta"]["scraped_text"]
        old_cat   = r.get("Incentive Category", "No Incentive")

        print(f"[{i}/{len(eligible)}] {name[:50]}")

        result = extract_with_claude(text, business_type=btype)
        new_cat = result.get("category", "No Incentive")

        if new_cat == "No Incentive":
            skipped += 1
            print(f"         -> No Incentive (skipping)")
            # Still record as negative training example
            results.append({
                "venue_name":        name,
                "Business Type":     btype,
                "Incentive Category": "No Incentive",
                "Psychological Motivator Type": "Value",
                "Cuisine / Experience Category": btype,
                "Incentive Teaser":   "",
                "Full Incentive Description": "",
                "_meta": {
                    "scraped_text":      text,
                    "extraction_source": "relabeled_claude",
                    "old_category":      old_cat,
                    "text_chars":        len(text),
                },
            })
            continue

        if new_cat != old_cat:
            changed += 1

        motivator = _default_motivator(new_cat)
        print(f"         -> {new_cat}  (was: {old_cat})  val={result.get('value','-')}  timing={result.get('timing','-')}")

        results.append({
            "venue_name":        name,
            "Business Type":     btype,
            "Incentive Category": new_cat,
            "Psychological Motivator Type": motivator,
            "Cuisine / Experience Category": btype,
            "Incentive Teaser":   result.get("teaser", ""),
            "Full Incentive Description": result.get("description", ""),
            "_meta": {
                "scraped_text":      text,
                "extraction_source": "relabeled_claude",
                "old_category":      old_cat,
                "value":             result.get("value", ""),
                "timing":            result.get("timing", ""),
                "text_chars":        len(text),
            },
        })

        time.sleep(0.15)  # stay under rate limit

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    pos = sum(1 for r in results if r["Incentive Category"] != "No Incentive")
    neg = sum(1 for r in results if r["Incentive Category"] == "No Incentive")
    print(f"\n{'='*60}")
    print(f"  Done: {len(results)} records  |  {pos} positive  |  {neg} negative")
    print(f"  Category changed: {changed}")
    print(f"  Saved -> {output_path}")
    print(f"{'='*60}\n")
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=str, default=None,
                        help="Single pipeline output file to relabel")
    parser.add_argument("--glob", type=str, default="data/model_output/*.json",
                        help="Glob pattern for pipeline files (default: data/model_output/*.json)")
    parser.add_argument("--output", type=str, default=None)
    args = parser.parse_args()

    if args.input:
        paths = [args.input]
        # Derive output name from input filename so each batch gets its own file
        stem = Path(args.input).stem  # e.g. model_venues_2026-05-21_off0100
        default_out = os.path.join(OUTPUT_DIR, f"relabeled_{stem}.json")
    else:
        paths = glob_module.glob(args.glob)
        paths = [p for p in paths if "_relabeled" not in p]
        default_out = os.path.join(
            OUTPUT_DIR, f"relabeled_{datetime.now().strftime('%Y-%m-%d')}.json"
        )

    out = args.output or default_out
    relabel(paths, out)
