from src.place_search import search_places
from src.storage import save_to_json


def run_pipeline():
    print("Pipeline started...")

    # Get real places from Google Places API
    places = search_places(
        location="Long Beach, CA",
        category="restaurants"
    )

    print(f"Found {len(places)} places")

    results = []

    for i, place in enumerate(places, start=1):
        results.append({
            "venue_id": place.get("place_id"),
            "row": i,
            "venue_name": place.get("name"),
            "address": place.get("address"),
            "city": place.get("city"),
            "state": place.get("state"),
            "Business Type": place.get("type"),
            "Cuisine / Experience Category": "Unknown",
            "Incentive Category": "Unknown",
            "Incentive Teaser": "Needs extraction",
            "Full Incentive Description": "Needs extraction",
            "Days / Timing Restrictions": "Unknown",
            "Group Friendly?": "Unknown",
            "Psychological Motivator Type": "Unknown",
            "Estimated Perceived Value ($ range)": "Unknown",
            "Expiration / Ongoing": "Unknown",
            "Source URL": place.get("website"),
            "Notes": "Google Places baseline"
        })

    print("Processed results:", results)

    # Save to JSON
    save_to_json(results)

    return results