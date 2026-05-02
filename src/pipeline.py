from src.place_search import search_places
from src.scraper import scrape_multiple_pages, scrape_website_text
from src.incentive_extractor import extract_incentive
from src.storage import save_to_json


def run_pipeline():
    print("Pipeline started...")

    places = search_places(
        location="Long Beach, CA",
        category="restaurants"
    )

    print(f"Found {len(places)} places")

    results = []

    for i, place in enumerate(places, start=1):
        print(f"Checking website for: {place.get('name')}")

        from src.scraper import scrape_multiple_pages

        website_text = scrape_multiple_pages(place.get("website"))
        incentive = extract_incentive(website_text)

        results.append({
            "venue_id": place.get("place_id"),
            "row": i,
            "venue_name": place.get("name"),
            "address": place.get("address"),
            "city": place.get("city"),
            "state": place.get("state"),
            "Business Type": place.get("type"),
            "Cuisine / Experience Category": "Unknown",
            "Incentive Category": incentive["category"],
            "Incentive Teaser": incentive["teaser"],
            "Full Incentive Description": incentive["description"],
            "Days / Timing Restrictions": incentive["timing"],
            "Group Friendly?": "Unknown",
            "Psychological Motivator Type": incentive["motivator"],
            "Estimated Perceived Value ($ range)": incentive["value"],
            "Expiration / Ongoing": incentive["status"],
            "Source URL": place.get("website"),
            "Notes": incentive["notes"]
        })

    print("Processed results:", results)

    save_to_json(results)

    return results