-- ─────────────────────────────────────────────────────────────────────────────
-- schema.sql — MySQL schema for pipeline output
--
-- Mirrors the JSON records produced by run_model_pipeline.py
-- (see README.md "Output format"). One venue record maps to:
--   - exactly one row in `venues`
--   - zero or one rows in `venue_incentives` (zero when
--     Incentive Category is "No Incentive"/"Unknown" — matches
--     build_incentives() returning [] in src/schedule_formatter.py)
--
-- venue_incentives is a child table (not folded into venues) so it maps
-- cleanly onto the `incentives` array the backend already expects, and so
-- a venue with multiple incentives in the future doesn't require a schema
-- change.
-- ─────────────────────────────────────────────────────────────────────────────

CREATE DATABASE IF NOT EXISTS venue_scraper
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

USE venue_scraper;

CREATE TABLE IF NOT EXISTS venues (
    id                              INT AUTO_INCREMENT PRIMARY KEY,
    venue_id                        VARCHAR(255) NOT NULL,   -- Google Place ID from the source export
    venue_name                      VARCHAR(255) NOT NULL,
    address                         VARCHAR(500),
    city                            VARCHAR(120),
    state                           VARCHAR(50),
    business_type                   VARCHAR(120),
    cuisine_experience_category     VARCHAR(120),
    source_url                      TEXT,
    notes                           TEXT,

    -- Pipeline QA metadata (from each record's `_meta`) — lets the app
    -- filter out low-confidence or fallback-sourced data if it wants to.
    scrape_source                   VARCHAR(20),             -- direct / wayback / serper_fallback
    model_confidence                DECIMAL(4,3),
    extraction_source                VARCHAR(20),             -- llama / claude / ml_model / no_result

    created_at                      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at                      TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    UNIQUE KEY uq_venues_venue_id (venue_id),
    KEY idx_venues_city (city),
    KEY idx_venues_business_type (business_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS venue_incentives (
    id                  INT AUTO_INCREMENT PRIMARY KEY,
    venue_id            INT NOT NULL,

    incentive_key       VARCHAR(100),   -- slug, e.g. "happy_hour" (the `id` field in the incentives array)
    category             VARCHAR(50) NOT NULL,  -- Happy Hour / Discount / Free / Live Music / Early Entry / Group Booking / Matinee Deal
    teaser               VARCHAR(255),
    description          TEXT,

    timing_text          VARCHAR(500),   -- raw "Days / Timing Restrictions" string
    schedule_type         ENUM('recurring', 'always', 'date_range'),
    schedule              JSON,           -- {days, periods, timezone} or {start_date, end_date} — matches the `schedule` sub-object in README's incentives block

    group_friendly        VARCHAR(20),    -- Yes / No / Likely / Unknown
    motivator_type         VARCHAR(50),
    estimated_value        VARCHAR(500),  -- usually a short price/pct, but sometimes a full multi-day specials list
    expiration_status      VARCHAR(50),
    priority                INT,

    created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    FOREIGN KEY (venue_id) REFERENCES venues(id) ON DELETE CASCADE,
    KEY idx_venue_incentives_venue_id (venue_id),
    KEY idx_venue_incentives_category (category)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
