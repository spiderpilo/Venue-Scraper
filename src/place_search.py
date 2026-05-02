import requests

from src.config import GOOGLE_MAPS_API_KEY, DEFAULT_LOCATION, DEFAULT_CATEGORY, MAX_RESULTS


def search_places(location=DEFAULT_LOCATION, category=DEFAULT_CATEGORY):
    if not GOOGLE_MAPS_API_KEY:
        raise ValueError("Missing GOOGLE_MAPS_API_KEY in .env")

    url = "https://places.googleapis.com/v1/places:searchText"

    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": GOOGLE_MAPS_API_KEY,
        "X-Goog-FieldMask": "places.id,places.displayName,places.formattedAddress,places.primaryType,places.rating,places.websiteUri",
    }

    payload = {
        "textQuery": f"{category} near {location}",
        "maxResultCount": MAX_RESULTS,
    }

    response = requests.post(url, headers=headers, json=payload, timeout=10)

    if response.status_code != 200:
        print("Google API Error:")
        print(response.status_code)
        print(response.text)
        response.raise_for_status()

    data = response.json()
    places = data.get("places", [])

    results = []

    for place in places:
        results.append({
            "place_id": place.get("id"),
            "name": place.get("displayName", {}).get("text"),
            "address": place.get("formattedAddress", ""),
            "city": location.split(",")[0].strip(),
            "state": "CA",
            "website": place.get("websiteUri"),
            "rating": place.get("rating"),
            "type": place.get("primaryType", "restaurant"),
        })

    return results