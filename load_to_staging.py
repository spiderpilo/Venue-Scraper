"""
Loads run_model_pipeline.py output JSON files into the app's own
p1_db_dev.tbl_venues_near_you_staging table (a different database on the
same DigitalOcean cluster as venue_scraper, alongside ticketmaster/yelp/
ConnectLive/partner_portal rows already in there).

Usage:
    python load_to_staging.py data/model_output/my_run.json

Field mapping notes (best-effort — the app's incentives_json shape carries
fields we don't produce: terms, max_redemptions, redemption_count. Those
are left null/0. `recurrence` is a coarse guess from the schedule's `days`
list, not a real distinct field in our data):

    source_event_id  <- venue_id (Google Place ID) — used as the upsert key
    source            <- "venue_scraper" (this pipeline)
    event_title,
    location_name     <- venue_name
    incentive_hint     <- Incentive Teaser
    incentives         <- Full Incentive Description (plain text)
    incentives_json    <- best-effort single-element array in the app's
                          shape (see _build_incentives_json below); null
                          when there's no incentive
    model_meta         <- full _meta dict from our output, for audit trail

Requires DB_HOST/DB_PORT/DB_USER/DB_PASSWORD (+ DB_SSL_REQUIRED or
DB_SSL_CA) same as load_to_mysql.py — see README.
"""

import argparse
import glob
import json
import os
import re
import ssl
import sys

import pymysql
from dotenv import load_dotenv

load_dotenv()

STAGING_DB = "p1_db_dev"
STAGING_TABLE = "tbl_venues_near_you_staging"
SOURCE_LABEL = "venue_scraper"

DB_CONFIG = {
    "host": os.environ.get("DB_HOST", "127.0.0.1"),
    "port": int(os.environ.get("DB_PORT", "3306")),
    "user": os.environ.get("DB_USER", "venue_scraper"),
    "password": os.environ.get("DB_PASSWORD", "devpassword"),
    "database": STAGING_DB,
    "charset": "utf8mb4",
    "cursorclass": pymysql.cursors.Cursor,
}

_ssl_ca = os.environ.get("DB_SSL_CA")
_ssl_required = os.environ.get("DB_SSL_REQUIRED", "").strip().lower() in ("1", "true", "yes")
if _ssl_ca:
    DB_CONFIG["ssl"] = {"ca": _ssl_ca}
elif _ssl_required:
    DB_CONFIG["ssl"] = {"ssl": {}}

_UPSERT_SQL = f"""
INSERT INTO {STAGING_TABLE} (
    source_event_id, source, event_title, location_name, address, city, state, zip_code,
    business_type, experience_category, category,
    incentive_category, timing_restrictions, group_friendly, motivator_type,
    perceived_value, expiration_status, model_notes, model_confidence,
    incentives_source, scrape_source, model_meta, model_updated_at,
    incentive_hint, incentives, incentives_json
) VALUES (
    %s, %s, %s, %s, %s, %s, %s, %s,
    %s, %s, %s,
    %s, %s, %s, %s,
    %s, %s, %s, %s,
    %s, %s, %s, NOW(),
    %s, %s, %s
)
ON DUPLICATE KEY UPDATE
    source = VALUES(source),
    event_title = VALUES(event_title),
    location_name = VALUES(location_name),
    address = VALUES(address),
    city = VALUES(city),
    state = VALUES(state),
    zip_code = VALUES(zip_code),
    business_type = VALUES(business_type),
    experience_category = VALUES(experience_category),
    category = VALUES(category),
    incentive_category = VALUES(incentive_category),
    timing_restrictions = VALUES(timing_restrictions),
    group_friendly = VALUES(group_friendly),
    motivator_type = VALUES(motivator_type),
    perceived_value = VALUES(perceived_value),
    expiration_status = VALUES(expiration_status),
    model_notes = VALUES(model_notes),
    model_confidence = VALUES(model_confidence),
    incentives_source = VALUES(incentives_source),
    scrape_source = VALUES(scrape_source),
    model_meta = VALUES(model_meta),
    model_updated_at = NOW(),
    incentive_hint = VALUES(incentive_hint),
    incentives = VALUES(incentives),
    incentives_json = VALUES(incentives_json)
"""


_NULLISH_VALUES = (None, "", "Unknown", "No incentive found")


def _nullish(value):
    return None if value in _NULLISH_VALUES else value


def _fit(value, max_len):
    """Truncate to fit the target column's varchar length rather than
    letting a rare long value (e.g. a multi-day specials list) fail the
    whole insert — this is their table, not ours to ALTER without asking."""
    if value is None or len(value) <= max_len:
        return value
    return value[: max_len - 1] + "…"


_ZIP_RE = re.compile(r"\b(\d{5})(?:-\d{4})?\b")


def _extract_zip(address):
    if not address:
        return None
    match = _ZIP_RE.search(address)
    return match.group(1) if match else None


def _recurrence_guess(schedule):
    days = (schedule or {}).get("days")
    if not days:
        return None
    return "DAILY" if len(days) == 7 else "WEEKLY"


def _build_incentives_json(record):
    incentives = record.get("incentives") or []
    if not incentives:
        return None
    entry = incentives[0]
    schedule = entry.get("schedule") or {}
    return json.dumps([{
        "id": entry.get("id"),
        "type": entry.get("title"),
        "terms": None,
        "title": record.get("venue_name"),
        "end_date": schedule.get("end_date"),
        "priority": entry.get("priority"),
        "schedule": schedule or None,
        "incentives": entry.get("description"),
        "recurrence": _recurrence_guess(schedule),
        "start_date": schedule.get("start_date"),
        "group_friendly": record.get("Group Friendly?"),
        "incentive_hint": record.get("Incentive Teaser"),
        "max_redemptions": None,
        "redemption_count": 0,
    }])


def map_record(record):
    meta = record.get("_meta", {})
    category = _nullish(record.get("Incentive Category"))
    if category == "No Incentive":
        category = None

    return (
        record.get("venue_id"),
        SOURCE_LABEL,
        _fit(record.get("venue_name"), 255),
        _fit(record.get("venue_name"), 255),
        _fit(record.get("address"), 255),
        _fit(record.get("city"), 100),
        _fit(record.get("state"), 100),
        _extract_zip(record.get("address")),
        _fit(_nullish(record.get("Business Type")), 100),
        _fit(_nullish(record.get("Cuisine / Experience Category")), 100),
        _fit(_nullish(record.get("Business Type")), 100),
        _fit(category, 100),
        _fit(_nullish(record.get("Days / Timing Restrictions")), 500),
        _fit(_nullish(record.get("Group Friendly?")), 16),
        _fit(_nullish(record.get("Psychological Motivator Type")), 50),
        _fit(_nullish(record.get("Estimated Perceived Value ($ range)")), 100),
        _fit(_nullish(record.get("Expiration / Ongoing")), 50),
        _nullish(record.get("Notes")),
        meta.get("model_confidence"),
        _fit(meta.get("extraction_source"), 32),
        _fit(meta.get("scrape_source"), 32),
        json.dumps({k: v for k, v in meta.items() if k != "scraped_text"}),
        _fit(_nullish(record.get("Incentive Teaser")), 255),
        _nullish(record.get("Full Incentive Description")),
        _build_incentives_json(record),
    )


def load_records(paths):
    records = []
    for path in paths:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        records.extend(data if isinstance(data, list) else [data])
    return records


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

    is_local_host = DB_CONFIG["host"] in ("127.0.0.1", "localhost", "host.docker.internal")

    if _ssl_ca and not os.path.exists(_ssl_ca):
        print(f"\nERROR: DB_SSL_CA is set to '{_ssl_ca}' but that file doesn't exist in this container.\n")
        sys.exit(1)

    try:
        conn = pymysql.connect(**DB_CONFIG)
    except ssl.SSLError as exc:
        print(f"\nERROR: DB_SSL_CA points to a file that isn't a valid CA certificate ({exc}).\n")
        sys.exit(1)
    except (pymysql.err.OperationalError, pymysql.err.InternalError) as exc:
        print(f"\nERROR: Can't reach MySQL at {DB_CONFIG['host']}:{DB_CONFIG['port']} ({exc}).")
        if is_local_host:
            print("  Make sure it's running and DB_HOST/--add-host are set correctly.")
        else:
            print("  Check DB_HOST/DB_PORT/DB_USER/DB_PASSWORD, DB_SSL_REQUIRED, and Trusted Sources.")
        print()
        sys.exit(1)

    written = 0
    skipped = 0
    try:
        with conn.cursor() as cursor:
            for record in records:
                if not record.get("venue_id"):
                    skipped += 1
                    continue
                cursor.execute(_UPSERT_SQL, map_record(record))
                written += 1
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    print(f"Rows upserted into {STAGING_DB}.{STAGING_TABLE}: {written}")
    if skipped:
        print(f"Skipped (no venue_id): {skipped}")


if __name__ == "__main__":
    main()
