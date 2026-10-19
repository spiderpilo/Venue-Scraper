"""
Fetches venues from local music API. Used for localmusic_run_model_pipeline.py

Response shape:
...
..[{"title":..., "artist":..., "city":..., "state":..., "address":..., "starts_at":..., ... }, {...},...]

"""

import os
import requests

PAGE_SIZE = 500

# get environment variables from .env
# same as lovable_client.py
def _require_env(name):
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(
            f"Missing required environment variable: {name}. "
            f"Add it to .env before using --from-local-music."
        )
    return value

def _map_venue(raw:dict)-> dict:
    """Rename fields in the json to fields that load_to_staging_localmusic expects.
        Matches column names in database.
    """
    # place id, name, address, city, state, type, website
    # city, state, address are already named as such and don't need to be mapped
    mapped = dict(raw)
    mapped["venue_id"] = raw.get("venue_key")
    mapped["venue_name"] = raw.get("venue")
    mapped["Business Type"] =raw.get("event_type")
    mapped["Source URL"] = raw.get("source_url")

    # new columns
    mapped["show_artist"] = raw.get("artist")
    mapped["show_starts"] = raw.get("starts_at_utc")
    mapped["show_ends"] = raw.get("ends_at")
    mapped["show_genre"] = raw.get("genre")
    # mapped["show_price"] = raw.get("cover_max_usd")
    mapped["show_title"] = raw.get("title")

    # not new, but things we can pull from the local music API that the lovable API does not have.
    mapped["event_url"] = raw.get("venue_website")
    mapped["zip_code"] = raw.get("postcode")
    mapped["latitude"] = raw.get("lat")
    mapped["longitude"] = raw.get("lon")


    return mapped

def fetch_music_venues(from_date=None, page_size=PAGE_SIZE, max_venues=None):

    api_url = _require_env("LOCALMUSIC_API_URL")
    api_key = _require_env("LOCALMUSIC_SCRAPER_API_KEY")
    api_auth = _require_env("LOCALMUSIC_AUTH")

    headers = {
        "apikey": api_key,
        "Authorization": f"Bearer {api_auth}"

    }

    all_venues = []
    cursor = None
    page = 0

    while True:

        # params for url request
        params = {"limit": page_size}
        
        if cursor is not None:
            params["cursor"] = cursor

        # request
        resp = requests.get(api_url, headers=headers, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        all_venues.extend(data)
        page += 1


        # finish pulling data

        if max_venues is not None and len(all_venues) >= max_venues:
            print(f"  Reached max_venues={max_venues}, stopping pagination early.")
            break

        cursor = data.get("next_cursor") # check for more pages
        if cursor is None:
            break


    if max_venues is not None:
        all_venues = all_venues[:max_venues]

    mapped = [_map_venue(v) for v in data] # map venue data to expected key names
    valid = [v for v in mapped if v.get("Source URL")]

    print(f"  Local music: {len(valid)}/{len(mapped)} venues have a website")
    
    return valid