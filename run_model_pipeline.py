"""
Model pipeline: scrape venues from venues.json using the ML model extractor.

Usage:
    python run_model_pipeline.py                      # first 10 venues
    python run_model_pipeline.py --indices 0,4,5,7    # specific venues by index
    python run_model_pipeline.py --offset 5 --limit 5
    python run_model_pipeline.py --limit 100 --output model_venues_2026-05-17.json
    python run_model_pipeline.py --workers 8           # parallel scraping (default: 5)
"""

import argparse
import concurrent.futures
import json
import os
import sys
import threading
import time
from datetime import datetime

# sys.stdout.reconfigure(encoding="utf-8", errors="replace")
# sys.path.insert(0, os.path.dirname(__file__))

from src.scraper import scrape_venue_pages, fallback_search, fallback_search_pricing, scrape_wayback
from src.model_extractor import extract_incentive_with_model, extract_value
from src.field_enricher import enrich_fields
from src.schedule_formatter import build_incentives
from src.teaser_rewriter import rewrite_teaser

OUTPUT_DIR  = "data/model_output"
OUTPUT_FILE = "model_venues.json"

DEFAULT_SOURCE = "data/processed/json_batches_combined_presplit.json"


def load_all_venues(path=DEFAULT_SOURCE):
    with open(path, encoding="utf-8-sig") as f:
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

    valid = [v for v in venues if v.get("Source URL")]

    if not valid and venues:
        sample_keys = list(venues[0].keys()) if venues else []
        print(f"\nERROR: Loaded {len(venues)} records but none have a 'Source URL' field.")
        print(f"Fields found in your file: {sample_keys}")
        print("Rename the URL column to 'Source URL' or check the file format.\n")

    return valid


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


# ── Scraping (parallelizable) ────────────────────────────────────────────────

SCRAPE_BUDGET = 45.0

def _scrape_one(venue):
    """Scrape a single venue. Returns (text, scrape_source, scrape_time)."""
    name = venue.get("venue_name", "Unknown")
    url  = venue.get("Source URL", "")
    btype = venue.get("Business Type", "")

    t0 = time.time()
    deadline = t0 + SCRAPE_BUDGET
    text = scrape_venue_pages(url, business_type=btype, max_time=SCRAPE_BUDGET)
    scrape_source = "direct"
    if not text:
        text = scrape_wayback(url, deadline=deadline)
        if text:
            scrape_source = "wayback"
    if not text:
        text = fallback_search(name, venue.get("city", ""))
        if text:
            scrape_source = "serper_fallback"
    scrape_time = time.time() - t0
    return text, scrape_source, scrape_time


def _scrape_all(venues, workers):
    """Scrape all venues, returning list of (text, source, time) in order."""
    n = len(venues)

    if workers <= 1:
        results = []
        for i, v in enumerate(venues, 1):
            name = v.get("venue_name", "Unknown")
            url  = v.get("Source URL", "")
            print(f"[{i}/{n}] {name}")
            print(f"        {url}")
            results.append(_scrape_one(v))
        return results

    # Parallel scraping — suppress verbose per-URL output, show progress counter
    scrape_results = [None] * n
    progress_lock = threading.Lock()
    completed = [0]

    def _scrape_with_progress(idx_venue):
        idx, venue = idx_venue
        result = _scrape_one(venue)
        with progress_lock:
            completed[0] += 1
            chars = len(result[0])
            name = venue.get("venue_name", "Unknown")
            sys.stderr.write(
                f"\r  Scraped {completed[0]}/{n}: {name[:30]:<30}  "
                f"({result[1]}, {chars:,} chars, {result[2]:.1f}s)"
            )
            sys.stderr.flush()
        return idx, result

    old_stdout = sys.stdout
    sys.stdout = open(os.devnull, "w")
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            for idx, result in pool.map(_scrape_with_progress, enumerate(venues)):
                scrape_results[idx] = result
    finally:
        sys.stdout.close()
        sys.stdout = old_stdout

    sys.stderr.write("\n")
    sys.stderr.flush()
    return scrape_results


# ── Processing (sequential — TF model not thread-safe) ────────────────────────

def _process_one(venue, text, scrape_source, scrape_time, idx, n_total):
    """Run model inference + enrichment for one venue. Returns the output record."""
    name  = venue.get("venue_name", "Unknown")
    url   = venue.get("Source URL", "")
    btype = venue.get("Business Type", "")
    place = venue_to_place(venue)

    timing_metrics = {}
    t1 = time.time()
    incentive = extract_incentive_with_model(
        text, business_type=btype, timing_metrics=timing_metrics,
    )

    # Value rescue: pricing-targeted search when extraction found no price
    if (incentive.get("value", "Unknown") == "Unknown"
            and incentive["category"] not in ("No Incentive", "Unknown")):
        pricing_text = fallback_search_pricing(name, venue.get("city", ""), incentive["category"])
        if pricing_text:
            v = extract_value(pricing_text)
            if v != "Unknown":
                incentive = dict(incentive)
                incentive["value"] = v
                incentive["notes"] = incentive.get("notes", "") + " [value: pricing search]"

    infer_time = time.time() - t1
    enriched = enrich_fields(place, text, incentive)

    original_teaser = incentive["teaser"]
    teaser = rewrite_teaser(original_teaser)

    record = {
        "venue_id": venue.get("venue_id"),
        "row": idx,
        "venue_name": name,
        "address": venue.get("address"),
        "city": venue.get("city"),
        "state": venue.get("state"),
        "Business Type": venue.get("Business Type"),
        "Cuisine / Experience Category": enriched["Cuisine / Experience Category"],
        "Incentive Category": incentive["category"],
        "Incentive Teaser": teaser,
        "Full Incentive Description": incentive["description"],
        "Days / Timing Restrictions": enriched["Days / Timing Restrictions"],
        "Group Friendly?": enriched["Group Friendly?"],
        "Psychological Motivator Type": enriched["Psychological Motivator Type"],
        "Estimated Perceived Value ($ range)": enriched["Estimated Perceived Value ($ range)"],
        "Expiration / Ongoing": enriched["Expiration / Ongoing"],
        "Source URL": url,
        "Notes": incentive.get("notes", ""),
        "incentives": build_incentives({
            "Incentive Category": incentive["category"],
            "Full Incentive Description": incentive["description"],
            "Days / Timing Restrictions": enriched["Days / Timing Restrictions"],
            "Expiration / Ongoing": enriched["Expiration / Ongoing"],
        }),
        "_meta": {
            "model_confidence": round(incentive.get("model_confidence", 0.0), 4),
            "scrape_time_s": round(scrape_time, 2),
            "inference_time_s": round(infer_time, 2),
            "text_chars": len(text),
            "scrape_source": scrape_source,
            "extraction_source": incentive.get("source", "unknown"),
            "scraped_text": text,
        },
    }

    conf = incentive.get("model_confidence", 0.0)
    ext_src = incentive.get("source", "unknown")
    print(f"[{idx}/{n_total}] {name}")
    print(f"        Category : {incentive['category']}  (conf {conf:.2f})  [{ext_src}]")
    rewritten = " [rewritten]" if teaser != original_teaser else ""
    print(f"        Teaser   : {teaser[:68]}{rewritten}")
    print(f"        Value    : {incentive.get('value', '—')}")
    print(f"        Timing   : {incentive.get('timing', '—')}")
    print(f"        Scrape   : {scrape_time:.1f}s | Inference: {infer_time:.1f}s | {len(text):,} chars")
    print()

    return record


# ── Orchestrator ──────────────────────────────────────────────────────────────

def run(indices=None, offset=0, limit=None, source=DEFAULT_SOURCE, output=None, workers=5):
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    out_file = output or OUTPUT_FILE
    out_path = os.path.join(OUTPUT_DIR, out_file)

    if not os.path.exists(source):
        print(f"\nERROR: Source file not found: {source}")
        print("Pass your file with --source data/processed/YOUR_FILE.json\n")
        return []

    all_venues = load_all_venues(source)

    if indices is not None:
        venues = [all_venues[i] for i in indices if i < len(all_venues)]
    elif limit is None:
        venues = all_venues[offset:]
    else:
        venues = all_venues[offset:offset + limit]

    n_total = len(venues)
    print("\n" + "=" * 65)
    print(f"  MODEL PIPELINE -- {n_total} venues, {workers} workers -> {out_path}")
    print("=" * 65 + "\n")

    pipeline_start = time.time()

    # Phase 1: scrape all venues (parallel when workers > 1)
    scrape_data = _scrape_all(venues, workers)

    scrape_wall = time.time() - pipeline_start
    scraped_ok = sum(1 for text, _, _ in scrape_data if text)
    print(f"  Scraping done: {scraped_ok}/{n_total} with content  ({scrape_wall:.1f}s wall time)\n")

    # Phase 2: model inference + enrichment (sequential)
    results = []
    for i, venue in enumerate(venues):
        text, scrape_source, scrape_time = scrape_data[i]
        record = _process_one(venue, text, scrape_source, scrape_time, i + 1, n_total)
        results.append(record)

    total_time = time.time() - pipeline_start

    with open(out_path, "w") as f:
        json.dump(results, f, indent=4)

    print("=" * 65)
    print("  METRICS")
    print("=" * 65)
    n = len(results)
    if n == 0:
        print("  No venues processed.\n")
        return results
    scraped = sum(1 for r in results if r["_meta"]["text_chars"] > 0)
    avg_scrape = sum(r["_meta"]["scrape_time_s"] for r in results) / n
    avg_infer = sum(r["_meta"]["inference_time_s"] for r in results) / n
    avg_conf = sum(r["_meta"]["model_confidence"] for r in results) / n
    claude_n = sum(1 for r in results if r["_meta"]["extraction_source"] == "claude")
    ml_n     = sum(1 for r in results if r["_meta"]["extraction_source"] == "ml_model")
    print(f"  Venues processed    : {n}")
    print(f"  Successfully scraped: {scraped}/{n}")
    print(f"  Total wall time     : {total_time:.1f}s")
    print(f"  Scrape wall time    : {scrape_wall:.1f}s  ({workers} workers)")
    print(f"  Avg scrape/venue    : {avg_scrape:.1f}s")
    print(f"  Avg inference/venue : {avg_infer:.1f}s")
    print(f"  Avg model confidence: {avg_conf:.2f}")
    print(f"  Extraction source   : {claude_n} claude  |  {ml_n} ml_model")
    print(f"  Saved → {out_path}")
    print("=" * 65 + "\n")

    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--indices", type=str, default=None,
                        help="Comma-separated venue indices, e.g. 0,4,7,11")
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--limit", type=int, default=None,
                        help="Number of venues to process (default: all)")
    parser.add_argument("--source", type=str, default=DEFAULT_SOURCE,
                        help="Path to source JSON file")
    parser.add_argument("--output", type=str, default=None,
                        help="Output filename (default: model_venues_YYYY-MM-DD.json)")
    parser.add_argument("--workers", type=int, default=5,
                        help="Number of parallel scraping workers (default: 5)")
    args = parser.parse_args()

    idx = [int(x) for x in args.indices.split(",")] if args.indices else None
    if args.output:
        out = args.output
    elif idx:
        out = f"model_venues_{datetime.now().strftime('%Y-%m-%d')}_custom.json"
    else:
        out = f"model_venues_{datetime.now().strftime('%Y-%m-%d')}_off{args.offset:04d}.json"

    run(indices=idx, offset=args.offset, limit=args.limit, source=args.source,
        output=out, workers=args.workers)
