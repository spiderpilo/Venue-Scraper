from src.storage import save_to_json

def run_pipeline():
    print("Pipeline started...")

    places = [
        {
            "place_id": "abc123",
            "name": "Tony's Pizza",
            "address": "123 Main St, Long Beach, CA",
            "city": "Long Beach",
            "state": "CA",
            "website": "https://example.com",
            "rating": 4.5,
            "type": "Restaurant"
        }
    ]

    results = []

    for i, place in enumerate(places, start=1):
        results.append({
            "venue_id": place["place_id"],
            "row": i,
            "venue_name": place["name"],
            "address": place["address"],
            "city": place["city"],
            "state": place["state"],
            "Business Type": place["type"],
            "Cuisine / Experience Category": "Pizza",  # placeholder
            "Incentive Category": "Discount",          # placeholder
            "Incentive Teaser": "10% off at night",    # placeholder
            "Full Incentive Description": "10% off after 7PM",  # placeholder
            "Days / Timing Restrictions": "After 7PM",  # placeholder
            "Group Friendly?": "Yes",
            "Psychological Motivator Type": "Discount",
            "Estimated Perceived Value ($ range)": "$5-$10",
            "Expiration / Ongoing": "Ongoing",
            "Source URL": place["website"],
            "Notes": "Baseline test data"
        })

    save_to_json(results)

    return results