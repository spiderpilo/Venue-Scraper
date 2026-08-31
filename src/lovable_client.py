"""
Fetches venues from the Lovable API (a Supabase Edge Function) and maps them
onto the field names run_model_pipeline.py expects.

Response shape, confirmed against the live API:
{
  "scrape": {"started_at": ..., "completed_at": ..., "status": ...,
             "new_venues_added": ..., "total_found": ..., ...},
  "venues": [{"id": <int, pagination cursor — NOT the same as venue_id>,
              "venue_id": <Google Place ID>, "venue_name": ..., "website": ...,
              "category": ..., "address": ..., "city": ..., "state": ..., ...}, ...],
  "count": <int>,
  "next_cursor": <int, last venue's internal "id">,
  "has_more": <bool>,
}

Pagination is cursor-based on the internal "id" field: request the next page
with ?cursor=<last id>&limit=<n>. Verified live against the real endpoint.
"""

import os

import requests

PAGE_SIZE = 500


def _require_env(name):
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(
            f"Missing required environment variable: {name}. "
            f"Add it to .env before using --from-lovable."
        )
    return value


def _map_venue(raw: dict) -> dict:
    # Same field mapping applied by hand to manually-exported files earlier
    # (website -> Source URL, category -> Business Type), now automatic.
    mapped = dict(raw)
    mapped["Source URL"] = raw.get("website")
    mapped["Business Type"] = raw.get("category")
    return mapped


def fetch_lovable_venues(from_date=None, page_size=PAGE_SIZE, max_venues=None):
    """
    Fetch venues from the Lovable API, paginating until has_more is false
    (or, with max_venues set, until at least that many have been fetched —
    for small test runs, so --limit doesn't require pulling the entire
    venue directory first). Returns a list of dicts already mapped onto the
    pipeline's expected field names, filtered to venues that have a website.
    """
    api_url = _require_env("LOVABLE_API_URL")
    api_key = _require_env("LOVABLE_SCRAPER_API_KEY")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
    }

    all_venues = []
    cursor = None
    page = 0

    while True:
        params = {"limit": page_size}
        if from_date:
            params["from_date"] = from_date
        if cursor is not None:
            params["cursor"] = cursor

        resp = requests.get(api_url, headers=headers, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        page += 1

        batch = data.get("venues", [])
        all_venues.extend(batch)

        if page == 1:
            scrape = data.get("scrape") or {}
            if scrape:
                print(
                    f"  Lovable scrape run: status={scrape.get('status')} "
                    f"new_venues_added={scrape.get('new_venues_added')} "
                    f"total_found={scrape.get('total_found')}"
                )

        print(f"  Lovable page {page}: {len(batch)} venues (total so far: {len(all_venues)})")

        if max_venues is not None and len(all_venues) >= max_venues:
            print(f"  Reached max_venues={max_venues}, stopping pagination early.")
            break
        if not data.get("has_more"):
            break
        cursor = data.get("next_cursor")
        if cursor is None:
            break

    if max_venues is not None:
        all_venues = all_venues[:max_venues]

    mapped = [_map_venue(v) for v in all_venues]
    valid = [v for v in mapped if v.get("Source URL")]

    print(f"  Lovable: {len(valid)}/{len(mapped)} venues have a website")

    return valid
