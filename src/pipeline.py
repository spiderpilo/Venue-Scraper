from src.place_search import search_places
from src.scraper import scrape_venue_pages
from src.incentive_extractor import extract_incentive
from src.field_enricher import enrich_fields
from src.storage import save_to_json
from src.dataset_builder import build_sentence_dataset, save_sentence_dataset


def run_pipeline():
    print("Pipeline started...")

    # 🔥 Multiple categories to increase dataset size
    categories = [
        "restaurants",
        "bars",
        "pizza",
        "coffee shops",
        "live music venues",
        "happy hour restaurants"
    ]

    places = []

    # 🔎 Search each category
    for category in categories:
        print(f"Searching category: {category}")
        places.extend(search_places(
            location="Long Beach, CA",
            category=category
        ))

    # 🔁 Deduplicate by place_id
    unique_places = {}
    for place in places:
        unique_places[place.get("place_id")] = place

    places = list(unique_places.values())

    print(f"Found {len(places)} unique places")

    places_with_text = []
    results = []

    # 🚀 Main processing loop
    for i, place in enumerate(places, start=1):
        print(f"Checking website for: {place.get('name')}")

        website_text = scrape_venue_pages(place.get("website"))

        # Store for ML dataset
        places_with_text.append({
            "venue_id": place.get("place_id"),
            "venue_name": place.get("name"),
            "source_url": place.get("website"),
            "website_text": website_text
        })

        incentive = extract_incentive(website_text)
        enriched = enrich_fields(place, website_text, incentive)

        results.append({
            "venue_id": place.get("place_id"),
            "row": i,
            "venue_name": place.get("name"),
            "address": place.get("address"),
            "city": place.get("city"),
            "state": place.get("state"),
            "Business Type": place.get("type"),

            "Cuisine / Experience Category": enriched["Cuisine / Experience Category"],
            "Incentive Category": incentive["category"],
            "Incentive Teaser": incentive["teaser"],
            "Full Incentive Description": incentive["description"],
            "Days / Timing Restrictions": enriched["Days / Timing Restrictions"],
            "Group Friendly?": enriched["Group Friendly?"],
            "Psychological Motivator Type": enriched["Psychological Motivator Type"],
            "Estimated Perceived Value ($ range)": enriched["Estimated Perceived Value ($ range)"],
            "Expiration / Ongoing": enriched["Expiration / Ongoing"],

            "Source URL": place.get("website"),
            "Notes": incentive["notes"]
        })

    print("Processed results:", results)

    # 📊 Build ML dataset
    sentence_df = build_sentence_dataset(places_with_text)
    save_sentence_dataset(sentence_df)

    # 💾 Save final venue data
    save_to_json(results)

    return results