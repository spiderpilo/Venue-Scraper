"""
Full pipeline inspection tool — shows scraper output, filtered sentences,
and Llama extraction result side by side per venue.

Usage:
    python inspect_pipeline.py --limit 10
    python inspect_pipeline.py --indices 0,3,7
    python inspect_pipeline.py --url https://example.com --name "My Venue"
    python inspect_pipeline.py --source data/processed/my_file.json --limit 5
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(__file__))

from src.scraper import scrape_venue_pages, fallback_search, scrape_wayback
from src.model_extractor import _has_incentive_keywords
from src.llama_extractor import extract_incentive_with_llama

DEFAULT_SOURCE = "data/processed/json_batches_combined_presplit.json"
OUTPUT_DIR = "data/inspect"
SCRAPE_BUDGET = 45.0


def _divider(char="─", width=70):
    print(char * width)


def _header(text, char="═", width=70):
    print(f"\n{char * width}")
    print(f"  {text}")
    print(f"{char * width}")


def inspect_venue(name: str, url: str, btype: str = "") -> dict:
    _header(f"{name}")
    print(f"  URL  : {url}")
    print(f"  Type : {btype or 'Unknown'}")

    # ── 1. Scrape ────────────────────────────────────────────────────────────
    print(f"\n  [1] SCRAPER")
    _divider()
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

    scrape_time = round(time.time() - t0, 1)
    print(f"  source={source}  chars={len(text):,}  ({scrape_time}s)")
    if text:
        print(f"\n  Raw text (first 500 chars):")
        for line in text[:500].split("\n"):
            if line.strip():
                print(f"    {line.strip()[:120]}")
    else:
        print("  (no content scraped)")

    # ── 2. Filtered sentences ────────────────────────────────────────────────
    print(f"\n  [2] FILTERED SENTENCES  (sent to Llama)")
    _divider()
    sentences = re.split(r"[.!?\n]", text)
    matched = []
    seen = set()
    for s in sentences:
        s = s.strip()
        if len(s) >= 10 and _has_incentive_keywords(s) and s not in seen:
            seen.add(s)
            matched.append(s)

    if matched:
        for i, s in enumerate(matched, 1):
            print(f"  [{i}] {s[:160]}")
    else:
        print("  (no keyword-matched sentences found)")

    # ── 3. Llama extraction ──────────────────────────────────────────────────
    print(f"\n  [3] LLAMA RESULT")
    _divider()
    t1 = time.time()
    result = extract_incentive_with_llama(text, business_type=btype)
    llama_time = round(time.time() - t1, 1)

    print(f"  Category : {result['category']}")
    print(f"  Teaser   : {result['teaser']}")
    print(f"  Timing   : {result['timing']}")
    print(f"  Value    : {result['value']}")
    print(f"  Motivator: {result['motivator']}")
    print(f"  Status   : {result['status']}")
    print(f"  Inference: {llama_time}s")

    return {
        "venue_name": name,
        "url": url,
        "business_type": btype,
        "scrape_source": source,
        "scrape_time_s": scrape_time,
        "raw_text_chars": len(text),
        "raw_text": text,
        "filtered_sentences": matched,
        "llama_result": result,
        "llama_time_s": llama_time,
    }


def load_venues(source: str) -> list[dict]:
    with open(source, encoding="utf-8-sig") as f:
        data = json.load(f)
    venues = data if isinstance(data, list) else [data]
    return [v for v in venues if v.get("Source URL")]


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url",     type=str, default=None)
    parser.add_argument("--name",    type=str, default="Venue")
    parser.add_argument("--source",  type=str, default=DEFAULT_SOURCE)
    parser.add_argument("--indices", type=str, default=None, help="e.g. 0,3,7")
    parser.add_argument("--offset",  type=int, default=0)
    parser.add_argument("--limit",   type=int, default=5)
    parser.add_argument("--output",  type=str, default=None)
    args = parser.parse_args()

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    results = []

    if args.url:
        results.append(inspect_venue(args.name, args.url))
    else:
        venues = load_venues(args.source)
        if args.indices:
            idxs = [int(x) for x in args.indices.split(",")]
            batch = [venues[i] for i in idxs if i < len(venues)]
        else:
            batch = venues[args.offset: args.offset + args.limit]

        print(f"\nInspecting {len(batch)} venues from {args.source}")
        for v in batch:
            results.append(inspect_venue(
                v.get("venue_name", "Unknown"),
                v.get("Source URL", ""),
                v.get("Business Type", ""),
            ))

    out_file = args.output or f"pipeline_inspect_{datetime.now().strftime('%Y-%m-%d_%H%M')}.json"
    out_path = os.path.join(OUTPUT_DIR, out_file)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"\n\nSaved {len(results)} venues → {out_path}")
