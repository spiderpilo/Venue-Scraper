"""
Loads run_model_pipeline.py output JSON files into MySQL.

Usage:
    python load_to_mysql.py data/model_output/venues_export_2026-07-29_run.json
    python load_to_mysql.py data/model_output/*.json

Re-running against the same venue_id upserts venues (INSERT ... ON DUPLICATE
KEY UPDATE) and replaces that venue's incentive rows, so loading overlapping
export batches is safe — the latest run for a venue wins.

Requires the schema in db/schema.sql to already exist (see README "Loading
into MySQL").
"""

import argparse
import glob
import json
import os
import sys

import pymysql
from dotenv import load_dotenv

load_dotenv()

DB_CONFIG = {
    "host": os.environ.get("DB_HOST", "127.0.0.1"),
    "port": int(os.environ.get("DB_PORT", "3306")),
    "user": os.environ.get("DB_USER", "venue_scraper"),
    "password": os.environ.get("DB_PASSWORD", "devpassword"),
    "database": os.environ.get("DB_NAME", "venue_scraper"),
    "charset": "utf8mb4",
    "cursorclass": pymysql.cursors.Cursor,
}

_UPSERT_VENUE_SQL = """
INSERT INTO venues (
    venue_id, venue_name, address, city, state, business_type,
    cuisine_experience_category, source_url, notes,
    scrape_source, model_confidence, extraction_source
) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON DUPLICATE KEY UPDATE
    venue_name = VALUES(venue_name),
    address = VALUES(address),
    city = VALUES(city),
    state = VALUES(state),
    business_type = VALUES(business_type),
    cuisine_experience_category = VALUES(cuisine_experience_category),
    source_url = VALUES(source_url),
    notes = VALUES(notes),
    scrape_source = VALUES(scrape_source),
    model_confidence = VALUES(model_confidence),
    extraction_source = VALUES(extraction_source)
"""

_INSERT_INCENTIVE_SQL = """
INSERT INTO venue_incentives (
    venue_id, incentive_key, category, teaser, description, timing_text,
    schedule_type, schedule, group_friendly, motivator_type,
    estimated_value, expiration_status, priority
) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""


def load_records(paths):
    records = []
    for path in paths:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        records.extend(data if isinstance(data, list) else [data])
    return records


def upsert_venue(cursor, record):
    meta = record.get("_meta", {})
    cursor.execute(
        _UPSERT_VENUE_SQL,
        (
            record.get("venue_id"),
            record.get("venue_name"),
            record.get("address"),
            record.get("city"),
            record.get("state"),
            record.get("Business Type"),
            record.get("Cuisine / Experience Category"),
            record.get("Source URL"),
            record.get("Notes"),
            meta.get("scrape_source"),
            meta.get("model_confidence"),
            meta.get("extraction_source"),
        ),
    )
    cursor.execute("SELECT id FROM venues WHERE venue_id = %s", (record.get("venue_id"),))
    return cursor.fetchone()[0]


def replace_incentives(cursor, venue_pk, record):
    cursor.execute("DELETE FROM venue_incentives WHERE venue_id = %s", (venue_pk,))

    incentives = record.get("incentives") or []
    for entry in incentives:
        schedule = entry.get("schedule")
        cursor.execute(
            _INSERT_INCENTIVE_SQL,
            (
                venue_pk,
                entry.get("id"),
                record.get("Incentive Category"),
                record.get("Incentive Teaser"),
                record.get("Full Incentive Description"),
                record.get("Days / Timing Restrictions"),
                entry.get("type"),
                json.dumps(schedule) if schedule else None,
                record.get("Group Friendly?"),
                record.get("Psychological Motivator Type"),
                record.get("Estimated Perceived Value ($ range)"),
                record.get("Expiration / Ongoing"),
                entry.get("priority"),
            ),
        )
    return len(incentives)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("files", nargs="+", help="Pipeline output JSON file(s) or glob(s)")
    args = parser.parse_args()

    paths = []
    for pattern in args.files:
        matched = sorted(glob.glob(pattern))
        paths.extend(matched if matched else [pattern])

    records = load_records(paths)
    print(f"Loaded {len(records)} records from {len(paths)} file(s)")

    skipped = 0
    venues_written = 0
    incentives_written = 0

    try:
        conn = pymysql.connect(**DB_CONFIG)
    except pymysql.err.OperationalError as exc:
        print(f"\nERROR: Can't reach MySQL at {DB_CONFIG['host']}:{DB_CONFIG['port']} ({exc}).")
        print("  1. Make sure it's running: docker compose up -d mysql")
        print("  2. If running this script from inside Docker (not directly on the host),")
        print("     DB_HOST must be host.docker.internal, and the container needs")
        print("     --add-host=host.docker.internal:host-gateway — same as the Ollama setup.")
        print("     If running directly on the host / a local venv, DB_HOST=127.0.0.1 is correct.")
        print("See README.md 'Loading into MySQL' for details.\n")
        sys.exit(1)

    try:
        with conn.cursor() as cursor:
            for record in records:
                if not record.get("venue_id"):
                    skipped += 1
                    continue
                venue_pk = upsert_venue(cursor, record)
                incentives_written += replace_incentives(cursor, venue_pk, record)
                venues_written += 1
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    print(f"Venues upserted   : {venues_written}")
    print(f"Incentives written: {incentives_written}")
    if skipped:
        print(f"Skipped (no venue_id): {skipped}")


if __name__ == "__main__":
    main()
