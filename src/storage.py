import json
from pathlib import Path

def save_to_json(data, filename="venues.json"):
    output_path = Path("data/processed") / filename

    with open(output_path, "w") as file:
        json.dump(data, file, indent=4)

    print(f"Saved results to {output_path}")