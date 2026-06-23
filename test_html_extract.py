"""
Test: extract incentive-relevant data from raw HTML without JS rendering.
Mines JSON-LD, __NEXT_DATA__, meta tags, and inline script data.

Usage:
    python test_html_extract.py --url https://533vietfusion.com/
    python test_html_extract.py --source data/processed/json_batches_combined_presplit.json --limit 20
"""

import argparse
import json
import os
import re
import sys
import time

import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}

OUTPUT_DIR = "data/inspect"


def extract_meta(soup):
    """Extract meta description and OG tags."""
    meta = {}
    for tag in soup.find_all("meta"):
        name = tag.get("name", "") or tag.get("property", "")
        content = tag.get("content", "")
        if name and content and name in (
            "description", "og:description", "og:title", "og:site_name",
            "twitter:description", "twitter:title",
        ):
            meta[name] = content
    return meta


def extract_jsonld(soup):
    """Extract all JSON-LD blocks, flatten nested @graph arrays."""
    results = []
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string)
            if isinstance(data, list):
                results.extend(data)
            elif isinstance(data, dict) and "@graph" in data:
                results.extend(data["@graph"])
            elif isinstance(data, dict):
                results.append(data)
        except (json.JSONDecodeError, TypeError):
            continue
    return results


def extract_jsonld_text(ld_blocks):
    """Pull human-readable text from JSON-LD structured data."""
    parts = []
    for block in ld_blocks:
        btype = block.get("@type", "")

        # Business name + description
        for key in ("name", "description"):
            val = block.get(key, "")
            if val and len(val) > 5:
                parts.append(val)

        # Opening hours (schema.org format: "Mo 07:00-21:00, Tu 07:00-21:00")
        hours = block.get("openingHours")
        if hours:
            if isinstance(hours, list):
                parts.append(" | ".join(hours))
            else:
                parts.append(f"Opening Hours: {hours}")

        # openingHoursSpecification (structured)
        specs = block.get("openingHoursSpecification", [])
        if specs:
            for spec in specs:
                days = spec.get("dayOfWeek", [])
                if isinstance(days, str):
                    days = [days]
                opens = spec.get("opens", "")
                closes = spec.get("closes", "")
                if days and opens:
                    parts.append(f"{', '.join(days)}: {opens}-{closes}")

        # Offers / hasOfferCatalog / event
        for offer_key in ("makesOffer", "hasOfferCatalog", "offers"):
            offers = block.get(offer_key)
            if offers:
                if isinstance(offers, dict):
                    offers = [offers]
                if isinstance(offers, list):
                    for o in offers[:5]:
                        name = o.get("name", "")
                        desc = o.get("description", "")
                        price = o.get("price", "")
                        if name or desc:
                            parts.append(f"{name}: {desc} {f'${price}' if price else ''}".strip())

        # Events
        if btype in ("Event", "MusicEvent", "DanceEvent", "FoodEvent"):
            ename = block.get("name", "")
            edesc = block.get("description", "")
            edate = block.get("startDate", "")
            parts.append(f"Event: {ename} {edate} {edesc}".strip())

        # Menu / hasMenu
        menu = block.get("hasMenu")
        if menu and isinstance(menu, dict):
            mname = menu.get("name", "")
            mdesc = menu.get("description", "")
            if mname or mdesc:
                parts.append(f"Menu: {mname} {mdesc}".strip())

        # Nested sub-organizations (e.g., FoodEstablishment inside Organization)
        for sub_key in ("subOrganization", "department"):
            sub = block.get(sub_key)
            if sub:
                if isinstance(sub, dict):
                    sub = [sub]
                if isinstance(sub, list):
                    parts.extend(extract_jsonld_text(sub))

    return parts


def extract_next_data(soup):
    """Extract text content from __NEXT_DATA__ (Next.js sites)."""
    script = soup.find("script", id="__NEXT_DATA__")
    if not script or not script.string:
        return None, []

    try:
        data = json.loads(script.string)
    except (json.JSONDecodeError, TypeError):
        return None, []

    props = data.get("props", {}).get("pageProps", {})

    # Walk the props tree and extract string values that look like content
    texts = []
    _walk_for_text(props, texts, depth=0)
    return props, texts


def _walk_for_text(obj, texts, depth=0):
    """Recursively walk JSON and collect string values that look like content."""
    if depth > 8:
        return
    if isinstance(obj, str):
        stripped = obj.strip()
        if 20 <= len(stripped) <= 1000 and not stripped.startswith(("http", "/", "{", "<")):
            texts.append(stripped)
    elif isinstance(obj, dict):
        for v in obj.values():
            _walk_for_text(v, texts, depth + 1)
    elif isinstance(obj, list):
        for item in obj[:50]:
            _walk_for_text(item, texts, depth + 1)


def extract_nuxt_data(html):
    """Extract from __NUXT__ or __NUXT_DATA__ patterns."""
    match = re.search(r'window\.__NUXT__\s*=\s*(\{.*?\});?\s*</script>', html, re.DOTALL)
    if not match:
        return []
    try:
        data = json.loads(match.group(1))
        texts = []
        _walk_for_text(data, texts, depth=0)
        return texts
    except (json.JSONDecodeError, TypeError):
        return []


def extract_from_html(url):
    """Fetch a URL and extract all embedded data without JS rendering."""
    t0 = time.time()
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        if r.status_code != 200:
            return {"url": url, "error": f"HTTP {r.status_code}", "elapsed_s": round(time.time() - t0, 2)}
    except Exception as e:
        return {"url": url, "error": str(e), "elapsed_s": round(time.time() - t0, 2)}

    html = r.text
    soup = BeautifulSoup(html, "html.parser")

    # 1. Meta tags
    meta = extract_meta(soup)

    # 2. JSON-LD
    ld_blocks = extract_jsonld(soup)
    ld_text = extract_jsonld_text(ld_blocks)

    # 3. __NEXT_DATA__
    next_props, next_texts = extract_next_data(soup)

    # 4. __NUXT__
    nuxt_texts = extract_nuxt_data(html)

    # 5. Visible text (what requests gets without JS)
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    visible = soup.get_text(" ", strip=True)

    elapsed = round(time.time() - t0, 2)

    return {
        "url": url,
        "elapsed_s": elapsed,
        "html_size": len(html),
        "visible_text_chars": len(visible),
        "meta_tags": meta,
        "jsonld_blocks": len(ld_blocks),
        "jsonld_types": [b.get("@type", "?") for b in ld_blocks],
        "jsonld_text": ld_text,
        "jsonld_raw": ld_blocks,
        "has_next_data": next_props is not None,
        "next_data_texts": next_texts[:20],
        "nuxt_texts": nuxt_texts[:20],
        "visible_text_preview": visible[:500],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", type=str, default=None, help="Single URL to test")
    parser.add_argument("--name", type=str, default="Venue")
    parser.add_argument("--source", type=str, default=None)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--output", type=str, default=None)
    args = parser.parse_args()

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    results = []

    if args.url:
        print(f"Extracting from {args.url}...")
        result = extract_from_html(args.url)
        result["venue_name"] = args.name
        results.append(result)
    elif args.source:
        with open(args.source, encoding="utf-8-sig") as f:
            venues = json.load(f)
        if not isinstance(venues, list):
            venues = [venues]
        venues = [v for v in venues if v.get("Source URL")]
        batch = venues[args.offset: args.offset + args.limit]

        print(f"Extracting embedded data from {len(batch)} venues...\n")
        for i, v in enumerate(batch, 1):
            name = v.get("venue_name", "Unknown")
            url = v.get("Source URL", "")
            print(f"  [{i}/{len(batch)}] {name}...", end=" ", flush=True)
            result = extract_from_html(url)
            result["venue_name"] = name
            results.append(result)

            if "error" in result:
                print(f"FAILED: {result['error']}")
            else:
                n_signals = len(result["jsonld_text"]) + len(result["next_data_texts"]) + len(result["nuxt_texts"])
                print(f"OK ({result['elapsed_s']}s, {result['jsonld_blocks']} JSON-LD, {n_signals} text signals)")

    out_file = args.output or f"html_extract_{time.strftime('%Y-%m-%d_%H%M')}.json"
    out_path = os.path.join(OUTPUT_DIR, out_file)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"\nSaved {len(results)} venues -> {out_path}")


if __name__ == "__main__":
    main()
