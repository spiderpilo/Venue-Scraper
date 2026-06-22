"""
Scrape venues and output a JSON file showing which sentences are fed to the model.

Usage:
    python scrape_inspect.py                          # first 10 venues, saves to data/inspect/
    python scrape_inspect.py --limit 5
    python scrape_inspect.py --indices 0,3,7
    python scrape_inspect.py --source data/processed/All_Venues_w_Incentives.json --limit 5
    python scrape_inspect.py --url https://example.com --name "My Venue"
    python scrape_inspect.py --output my_output.json
    python scrape_inspect.py --workers 8               # parallel scraping (default: 5)
"""

import argparse
import concurrent.futures
import json
import os
import re
import sys
import threading
import time
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(__file__))

from src.scraper import scrape_venue_pages, fallback_search, scrape_wayback
from src.model_extractor import _has_incentive_keywords

DEFAULT_SOURCE = "data/processed/json_batches_combined_presplit.json"
OUTPUT_DIR = "data/inspect"

SCRAPE_BUDGET = 45.0


def get_candidates(text: str) -> list[str]:
    raw = re.split(r"[.!?\n]", text)
    seen = set()
    results = []
    for s in raw:
        s = s.strip()
        if len(s) >= 10 and _has_incentive_keywords(s) and s not in seen:
            seen.add(s)
            results.append(s)
    return results


def _scrape_one(name, url, btype):
    """Scrape a single venue. Returns (text, source, elapsed)."""
    t0 = time.time()
    deadline = t0 + SCRAPE_BUDGET

    text = scrape_venue_pages(url, business_type=btype, max_time=SCRAPE_BUDGET)
    source = "direct"
    if not text:
        text = scrape_wayback(url, deadline=deadline)
        source = "wayback" if text else source
    if not text:
        text = fallback_search(name, "")
        source = "serper" if text else source

    elapsed = round(time.time() - t0, 1)
    return text, source, elapsed


def inspect_venue(name: str, url: str, btype: str = "") -> dict:
    print(f"  Scraping: {name}  ({url})")
    text, source, elapsed = _scrape_one(name, url, btype)
    candidates = get_candidates(text)
    print(f"    source={source}  chars={len(text):,}  sentences={len(candidates)}  ({elapsed}s)")

    return {
        "venue_name":         name,
        "url":                url,
        "business_type":      btype,
        "scrape_source":      source,
        "scrape_time_s":      elapsed,
        "raw_text_chars":     len(text),
        "sentence_count":     len(candidates),
        "sentences":          candidates,
    }


def _inspect_parallel(batch, workers):
    """Scrape venues in parallel, then build results in order."""
    n = len(batch)
    scrape_results = [None] * n
    progress_lock = threading.Lock()
    completed = [0]

    def _scrape_with_progress(idx_venue):
        idx, v = idx_venue
        name  = v.get("venue_name", "Unknown")
        url   = v.get("Source URL", "")
        btype = v.get("Business Type", "")
        result = _scrape_one(name, url, btype)
        with progress_lock:
            completed[0] += 1
            chars = len(result[0])
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
            for idx, result in pool.map(_scrape_with_progress, enumerate(batch)):
                scrape_results[idx] = result
    finally:
        sys.stdout.close()
        sys.stdout = old_stdout

    sys.stderr.write("\n")
    sys.stderr.flush()

    results = []
    for i, v in enumerate(batch):
        text, source, elapsed = scrape_results[i]
        candidates = get_candidates(text)
        name  = v.get("venue_name", "Unknown")
        url   = v.get("Source URL", "")
        btype = v.get("Business Type", "")

        print(f"  {name}: source={source}  chars={len(text):,}  sentences={len(candidates)}  ({elapsed}s)")

        results.append({
            "venue_name":     name,
            "url":            url,
            "business_type":  btype,
            "scrape_source":  source,
            "scrape_time_s":  elapsed,
            "raw_text_chars": len(text),
            "sentence_count": len(candidates),
            "sentences":      candidates,
        })

    return results


def load_venues(source: str) -> list[dict]:
    with open(source, encoding="utf-8-sig") as f:
        data = json.load(f)
    venues = data if isinstance(data, list) else [data]
    return [v for v in venues if v.get("Source URL")]


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url",     type=str, default=None, help="Single URL to inspect")
    parser.add_argument("--name",    type=str, default="Venue", help="Name for --url mode")
    parser.add_argument("--source",  type=str, default=DEFAULT_SOURCE)
    parser.add_argument("--indices", type=str, default=None, help="e.g. 0,3,7")
    parser.add_argument("--offset",  type=int, default=0)
    parser.add_argument("--limit",   type=int, default=10)
    parser.add_argument("--output",  type=str, default=None, help="Output filename")
    parser.add_argument("--workers", type=int, default=5,
                        help="Number of parallel scraping workers (default: 5)")
    args = parser.parse_args()

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    if args.url:
        results = [inspect_venue(args.name, args.url)]
    else:
        venues = load_venues(args.source)
        if args.indices:
            idxs = [int(x) for x in args.indices.split(",")]
            batch = [venues[i] for i in idxs if i < len(venues)]
        else:
            batch = venues[args.offset: args.offset + args.limit]

        n = len(batch)
        print(f"\nInspecting {n} venues from {args.source}\n")

        if args.workers > 1 and n > 1:
            results = _inspect_parallel(batch, args.workers)
        else:
            results = [inspect_venue(
                v.get("venue_name", "Unknown"),
                v.get("Source URL", ""),
                v.get("Business Type", ""),
            ) for v in batch]

    out_file = args.output or f"inspect_{datetime.now().strftime('%Y-%m-%d_%H%M')}.json"
    out_path = os.path.join(OUTPUT_DIR, out_file)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"\nSaved {len(results)} venues → {out_path}")
