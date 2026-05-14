"""
Model pipeline: scrape venues from venues.json using the ML model extractor.

Usage:
    python run_model_pipeline.py                      # first 10 venues
    python run_model_pipeline.py --indices 0,4,5,7    # specific venues by index
    python run_model_pipeline.py --offset 5 --limit 5
"""

import argparse
import json
import time
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from src.scraper import scrape_venue_pages
from src.model_extractor import extract_incentive_with_model
from src.field_enricher import enrich_fields

OUTPUT_DIR  = "data/model_output"
OUTPUT_FILE = "model_venues.json"

DEFAULT_SOURCE = "data/processed/json_batches_combined_presplit.json"


def load_all_venues(path=DEFAULT_SOURCE):
    with open(path) as f:
        content = f.read()

    # Handle both plain JSON arrays and concatenated JSON objects
    try:
        data = json.loads(content)
        venues = data if isinstance(data, list) else [data]
    except json.JSONDecodeError:
        decoder = json.JSONDecoder()
        pos, venues = 0, []
        while pos < len(content):
            stripped = content[pos:].lstrip()
            if not stripped:
                break
            skip = len(content[pos:]) - len(stripped)
            try:
                obj, end = decoder.raw_decode(stripped)
                pos = pos + skip + end
                if isinstance(obj, list):
                    venues.extend(v for v in obj if isinstance(v, dict))
                elif isinstance(obj, dict):
                    venues.append(obj)
            except Exception:
                break

    return [v for v in venues if v.get("Source URL")]


def venue_to_place(venue: dict) -> dict:
    return {
        "place_id": venue.get("venue_id"),
        "name": venue.get("venue_name"),
        "address": venue.get("address"),
        "city": venue.get("city"),
        "state": venue.get("state"),
        "type": venue.get("Business Type", ""),
        "website": venue.get("Source URL"),
    }


def run(indices=None, offset=0, limit=10, source=DEFAULT_SOURCE):
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    all_venues = load_all_venues(source)

    if indices is not None:
        venues = [all_venues[i] for i in indices if i < len(all_venues)]
    else:
        venues = all_venues[offset:offset + limit]

    n_total = len(venues)
    print("\n" + "=" * 65)
    print(f"  MODEL PIPELINE — {n_total} venues → {OUTPUT_DIR}/{OUTPUT_FILE}")
    print("=" * 65 + "\n")

    results = []
    pipeline_start = time.time()

    for i, venue in enumerate(venues, 1):
        name = venue.get("venue_name", "Unknown")
        url = venue.get("Source URL", "")
        place = venue_to_place(venue)

        print(f"[{i}/{n_total}] {name}")
        print(f"        {url}")

        t0 = time.time()
        text = scrape_venue_pages(url)
        scrape_time = time.time() - t0

        timing_metrics = {}
        t1 = time.time()
        incentive = extract_incentive_with_model(text, timing_metrics=timing_metrics)
        infer_time = time.time() - t1

        enriched = enrich_fields(place, text, incentive)

        record = {
            "venue_id": venue.get("venue_id"),
            "row": i,
            "venue_name": name,
            "address": venue.get("address"),
            "city": venue.get("city"),
            "state": venue.get("state"),
            "Business Type": venue.get("Business Type"),
            "Cuisine / Experience Category": enriched["Cuisine / Experience Category"],
            "Incentive Category": incentive["category"],
            "Incentive Teaser": incentive["teaser"],
            "Full Incentive Description": incentive["description"],
            "Days / Timing Restrictions": enriched["Days / Timing Restrictions"],
            "Group Friendly?": enriched["Group Friendly?"],
            "Psychological Motivator Type": enriched["Psychological Motivator Type"],
            "Estimated Perceived Value ($ range)": enriched["Estimated Perceived Value ($ range)"],
            "Expiration / Ongoing": enriched["Expiration / Ongoing"],
            "Source URL": url,
            "Notes": incentive.get("notes", ""),
            "_meta": {
                "model_confidence": round(incentive.get("model_confidence", 0.0), 4),
                "scrape_time_s": round(scrape_time, 2),
                "inference_time_s": round(infer_time, 2),
                "text_chars": len(text),
            },
        }

        results.append(record)

        conf = incentive.get("model_confidence", 0.0)
        print(f"        Category : {incentive['category']}  (conf {conf:.2f})")
        print(f"        Teaser   : {incentive['teaser'][:68]}")
        print(f"        Scrape   : {scrape_time:.1f}s | Inference: {infer_time:.1f}s | {len(text):,} chars")
        print()

    total_time = time.time() - pipeline_start

    out_path = os.path.join(OUTPUT_DIR, OUTPUT_FILE)
    with open(out_path, "w") as f:
        json.dump(results, f, indent=4)

    print("=" * 65)
    print("  METRICS")
    print("=" * 65)
    n = len(results)
    scraped = sum(1 for r in results if r["_meta"]["text_chars"] > 0)
    avg_scrape = sum(r["_meta"]["scrape_time_s"] for r in results) / n
    avg_infer = sum(r["_meta"]["inference_time_s"] for r in results) / n
    avg_conf = sum(r["_meta"]["model_confidence"] for r in results) / n
    print(f"  Venues processed   : {n}")
    print(f"  Successfully scraped: {scraped}/{n}")
    print(f"  Total wall time    : {total_time:.1f}s")
    print(f"  Avg scrape/venue   : {avg_scrape:.1f}s")
    print(f"  Avg inference/venue: {avg_infer:.1f}s")
    print(f"  Avg model confidence: {avg_conf:.2f}")
    print(f"  Saved → {out_path}")
    print("=" * 65 + "\n")

    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--indices", type=str, default=None,
                        help="Comma-separated venue indices, e.g. 0,4,7,11")
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--source", type=str, default=DEFAULT_SOURCE,
                        help="Path to source JSON file")
    args = parser.parse_args()

    idx = [int(x) for x in args.indices.split(",")] if args.indices else None
    run(indices=idx, offset=args.offset, limit=args.limit, source=args.source)
