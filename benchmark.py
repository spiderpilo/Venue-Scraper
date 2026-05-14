"""
Benchmark: ML model extractor vs pre-scraped ground truth.

Picks 5 venues from venues.json that already have a Source URL,
re-scrapes them live, runs the TensorFlow model, then compares
the predicted Incentive Category against the stored ground truth.

Usage:
    python benchmark.py
"""

import json
import time
import os
import sys

# Ensure imports resolve from project root
sys.path.insert(0, os.path.dirname(__file__))

from src.scraper import scrape_venue_pages
from src.model_extractor import extract_incentive_with_model


# ── helpers ──────────────────────────────────────────────────────────────────

def load_venues(path="data/processed/venues.json", limit=5):
    """Parse venues.json (may contain multiple concatenated JSON objects)."""
    with open(path) as f:
        content = f.read()

    decoder = json.JSONDecoder()
    pos = 0
    all_venues = []

    while pos < len(content):
        stripped = content[pos:].lstrip()
        if not stripped:
            break
        offset = len(content[pos:]) - len(stripped)
        try:
            obj, end = decoder.raw_decode(stripped)
            pos = pos + offset + end
            if isinstance(obj, list):
                all_venues.extend(v for v in obj if isinstance(v, dict))
            elif isinstance(obj, dict):
                all_venues.append(obj)
        except Exception:
            break

    # Prefer venues with a non-Unknown ground-truth category
    with_url = [v for v in all_venues if v.get("Source URL")]
    known = [v for v in with_url if v.get("Incentive Category", "Unknown") != "Unknown"]
    fallback = [v for v in with_url if v.get("Incentive Category", "Unknown") == "Unknown"]

    selected = (known + fallback)[:limit]
    return selected


def category_match(predicted: str, ground_truth: str) -> bool:
    return predicted.strip().lower() == ground_truth.strip().lower()


def bar(value: float, width: int = 20, char: str = "█") -> str:
    filled = int(round(value * width))
    return char * filled + "░" * (width - filled)


# ── benchmark ────────────────────────────────────────────────────────────────

def run_benchmark():
    print("\n" + "=" * 70)
    print("  MODEL BENCHMARK — 5 Venues (live re-scrape vs stored ground truth)")
    print("=" * 70 + "\n")

    venues = load_venues(limit=5)
    if not venues:
        print("ERROR: No venues with URLs found in venues.json")
        return

    results = []
    total_start = time.time()

    for i, venue in enumerate(venues, 1):
        name = venue.get("venue_name", "Unknown")
        url = venue.get("Source URL", "")
        ground_truth_category = venue.get("Incentive Category", "Unknown")

        print(f"[{i}/5] {name}")
        print(f"      URL: {url}")

        # ── scrape ──────────────────────────────────────────────────────────
        t0 = time.time()
        text = scrape_venue_pages(url)
        scrape_time = time.time() - t0

        # ── model inference ─────────────────────────────────────────────────
        timing = {}
        t1 = time.time()
        extraction = extract_incentive_with_model(text, timing_metrics=timing)
        total_inference = time.time() - t1

        predicted_category = extraction.get("category", "Unknown")
        confidence = extraction.get("model_confidence", 0.0)
        matched = category_match(predicted_category, ground_truth_category)

        results.append({
            "name": name,
            "url": url,
            "ground_truth": ground_truth_category,
            "predicted": predicted_category,
            "confidence": confidence,
            "matched": matched,
            "scrape_time": scrape_time,
            "inference_time": total_inference,
            "total_time": scrape_time + total_inference,
            "text_chars": len(text),
            "teaser": extraction.get("teaser", "—"),
        })

        status = "✓ MATCH" if matched else "✗ MISS "
        print(f"      Ground truth : {ground_truth_category}")
        print(f"      Predicted    : {predicted_category}  (confidence: {confidence:.2f})")
        print(f"      Result       : {status}")
        print(f"      Scrape time  : {scrape_time:.2f}s  |  Inference: {total_inference:.2f}s  |  Text: {len(text):,} chars")
        print(f"      Teaser       : {extraction.get('teaser', '—')}")
        print()

    total_elapsed = time.time() - total_start

    # ── summary ──────────────────────────────────────────────────────────────
    n = len(results)
    matches = sum(1 for r in results if r["matched"])
    accuracy = matches / n if n else 0
    avg_scrape = sum(r["scrape_time"] for r in results) / n if n else 0
    avg_infer = sum(r["inference_time"] for r in results) / n if n else 0
    avg_total = sum(r["total_time"] for r in results) / n if n else 0

    print("=" * 70)
    print("  SUMMARY")
    print("=" * 70)
    print(f"  Venues tested     : {n}")
    print(f"  Category matches  : {matches}/{n}  ({accuracy*100:.0f}%)")
    print(f"  Accuracy bar      : [{bar(accuracy)}]")
    print()
    print(f"  Avg scrape time   : {avg_scrape:.2f}s")
    print(f"  Avg inference     : {avg_infer:.2f}s")
    print(f"  Avg total/venue   : {avg_total:.2f}s")
    print(f"  Total wall time   : {total_elapsed:.2f}s")
    print()

    print("  Per-venue breakdown:")
    print(f"  {'Venue':<32} {'GT':<14} {'Pred':<14} {'Conf':>5}  {'Match':>6}  {'Time':>6}")
    print("  " + "-" * 68)
    for r in results:
        flag = "✓" if r["matched"] else "✗"
        print(
            f"  {r['name'][:31]:<32}"
            f" {r['ground_truth'][:13]:<14}"
            f" {r['predicted'][:13]:<14}"
            f" {r['confidence']:>5.2f}"
            f"  {flag:>6}"
            f"  {r['total_time']:>5.1f}s"
        )
    print("=" * 70 + "\n")

    return results


if __name__ == "__main__":
    run_benchmark()
