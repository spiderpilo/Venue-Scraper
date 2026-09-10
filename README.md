# Venue Incentive Scraper

Scrapes venue websites and automatically detects promotional incentives (happy hours, discounts, live music, etc.), then outputs structured JSON for the backend.

---

## How the pipeline works, start to finish

1. **Get a list of venues.** Either pulled live from the Lovable API (`--from-lovable`) or read from a JSON export file (`--source`). Either way, every venue needs a name, address, business type, and website URL.
2. **Scrape each venue's website.** A real browser (Playwright) opens the page and pulls its text. If the site is blocked, doesn't load, or is too JS-heavy, it falls back to a Wayback Machine snapshot, then a Serper search, in that order.
3. **Classify the scraped text.** A local Llama model (via Ollama — no paid API call here) reads the text and decides: is there a promotional incentive (Happy Hour, Discount, Free, Live Music, Early Entry, Group Booking, Matinee Deal), and if so, what's the teaser, timing, and value? Generic "join our rewards program" / loyalty-signup pitches get filtered out at this step rather than treated as real incentives.
4. **Enrich the result.** A few more fields get filled in from the scraped text and the model's answer — cuisine/experience category, whether it's group-friendly, the psychological motivator type — and the timing gets turned into a structured `incentives` schedule block (specific days/times, or a date range) the backend can render directly instead of parsing free text.
5. **Write the output.** Everything for that run gets saved as one JSON file in `data/model_output/`.
6. **Load into MySQL.** `load_to_mysql.py` reads that JSON and upserts it into two tables — `venues` and `venue_incentives` — either the local dev database or the team's DigitalOcean cluster. Re-running against the same venues never creates duplicates; it just updates them.
7. **The app reads from MySQL**, not from the JSON files. That's the actual handoff to the rest of the product — steps 1–6 are how the database gets (and stays) populated.

---

## Setup

### Requirements
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) installed and running
- [Ollama](https://ollama.com/download) installed and running on your machine (the pipeline calls it from inside the container — see step 2)
- A `.env` file in the project root with your API keys (see below)

### 1. Clone the repo

```bash
git clone https://github.com/spiderpilo/Venue-Scraper.git
cd Venue-Scraper
```

### 2. Install Ollama and pull the models

The pipeline runs its classification and text-rewriting locally through [Ollama](https://ollama.com/download), not through a paid API. Install it, then pull the two models this project uses:

```bash
ollama pull llama3.1:8b
ollama pull llama3.2:3b
```

Leave the Ollama app/service running in the background — the Docker container reaches it over the host network, which is why every `docker run` command below includes `--add-host=host.docker.internal:host-gateway` (required on Linux; harmless on Mac/Windows).

`run_model_pipeline.py` checks this automatically before doing any scraping: if Ollama isn't reachable, or is reachable but missing `llama3.1:8b`/`llama3.2:3b`, it fails immediately with a message telling you which of the two is wrong. If you don't see that check fail, the model is loading correctly — if every venue in your output still comes back `No Incentive` with `model_confidence: 0.0` and `extraction_source: "no_result"` in `_meta`, something's still off; re-check step 2 and the `--add-host` flag.

### 3. Create your `.env` file

Create a file called `.env` in the project root:

```
ANTHROPIC_API_KEY=your_key_here
SERPER_API_KEY=your_key_here

# Only needed if pulling venues live instead of from a file — see "Choosing a venue source"
LOVABLE_API_URL=
LOVABLE_SCRAPER_API_KEY=
```

> ⚠️ Never commit this file. It's already in `.gitignore`.
>
> `SERPER_API_KEY` is used as a scraping fallback (when a venue's site can't be reached directly or Wayback has nothing) and for pricing lookups when a detected incentive has no listed price — get a free key at [serper.dev](https://serper.dev). `ANTHROPIC_API_KEY` is not called by the default pipeline (`run_model_pipeline.py`) today; it's only used by `src/relabel_pipeline.py` for model retraining. Keys you're not using can stay blank, but the `.env` file must exist.

### 4. Build the Docker image

```bash
docker build -t venue-scraper .
```

This takes 5–10 minutes the first time. After that it's instant — but **rebuild any time you pull code changes**; edits to `.py` files don't take effect until the image is rebuilt.

---

## Running the pipeline

```bash
docker run --rm --add-host=host.docker.internal:host-gateway --env-file .env -v ${PWD}/data:/app/data venue-scraper python run_model_pipeline.py --from-lovable --limit 10
```

That's a 10-venue test run pulling live from the Lovable API (see below). Drop `--limit 10` to process everything the source has.

Useful flags, all combinable:
- `--limit N` / `--offset N` — process N venues starting at a given position
- `--indices 0,5,12,20` — process specific venues by index instead
- `--output my_run.json` — name the output file (default is auto-named by date; saved to `data/model_output/`)
- `--workers N` — parallel scraping workers (default 5)

### Choosing a venue source

**Option A — Lovable API (`--from-lovable`, recommended):** pulls venues live instead of requiring someone to export and manually relabel a file. Needs `LOVABLE_API_URL`/`LOVABLE_SCRAPER_API_KEY` in `.env` (see Setup step 3). Field mapping (`website`→`Source URL`, `category`→`Business Type`) happens automatically.

```bash
docker run --rm --add-host=host.docker.internal:host-gateway --env-file .env -v ${PWD}/data:/app/data venue-scraper python run_model_pipeline.py --from-lovable --limit 10
```

`--limit`/`--offset`/`--indices` slice the venues after fetching — except `--limit` without `--indices`, which stops paginating the API early once it has enough, so small test runs stay fast instead of always pulling the entire venue directory first.

For incremental pulls (only venues updated since a date), add `--lovable-from-date 2026-08-01` — this passes straight through to the API's own `from_date` filter, which hasn't been verified against the live API the way pagination has.

**Option B — a JSON file** (a one-off export, or if the Lovable API isn't set up yet):

1. Drop the file into `data/processed/`
2. Make sure it has these fields per venue: `Source URL` (website), `venue_name`, `Business Type`, `city` (used as a fallback search hint). If your file uses different column names (e.g. `website`/`category` instead), rename them first — the pipeline doesn't guess.
3. Run with `--source` instead of `--from-lovable`:

```bash
docker run --rm --add-host=host.docker.internal:host-gateway --env-file .env -v ${PWD}/data:/app/data venue-scraper python run_model_pipeline.py --source data/processed/YOUR_FILE.json --limit 10
```

---

## Loading into MySQL

The app pulls venue/incentive data from MySQL, not directly from the pipeline's JSON output. `db/schema.sql` defines two tables:

- `venues` — one row per venue (name, address, business type, source URL, plus pipeline QA fields: `scrape_source`, `model_confidence`, `extraction_source`)
- `venue_incentives` — one row per detected incentive, FK'd to `venues`. Empty for venues where `Incentive Category` is "No Incentive" (matches the JSON output's `incentives: []`). The `schedule` column stores the same nested JSON documented below (`days`/`periods`/`timezone` for recurring incentives, `start_date`/`end_date` for date-bounded ones).

### Local dev database

```bash
docker compose up -d mysql
```

Starts a local MySQL 8 container and runs `db/schema.sql` automatically on first boot (only on first boot — if you change the schema later, either drop the `mysql_data` volume and let it re-init, or apply the change by hand). Default credentials are already in `.env` (`DB_HOST=127.0.0.1`, etc.) matching `docker-compose.yml`'s defaults, so no extra setup is needed.

Load pipeline output into it:

```bash
docker run --rm --add-host=host.docker.internal:host-gateway --env-file .env \
  -e DB_HOST=host.docker.internal -v ${PWD}/data:/app/data venue-scraper \
  python load_to_mysql.py data/model_output/my_run.json
```

Accepts multiple files or a glob (`data/model_output/*.json`). Loading is idempotent and safe to re-run — each venue is upserted on `venue_id`, and that venue's incentive rows are replaced with whatever's in the file you just loaded, so re-loading the same or an overlapping export won't create duplicates.

`DB_HOST=host.docker.internal` + `--add-host` is required because the container needs to reach MySQL running on your host machine — same reason the pipeline commands above need it for Ollama. Running `load_to_mysql.py` directly on the host instead (outside Docker, in a local venv with `pip install -r requirements.txt`)? Use `DB_HOST=127.0.0.1` and drop `--add-host`.

The script checks MySQL is reachable before doing anything else — if it isn't, it fails immediately naming which of the above you're likely missing, rather than a raw connection traceback.

### Production: DigitalOcean Managed MySQL

The team's shared data lives here — a real cluster, already set up in the team's DO project (Databases → your cluster). The local docker-compose database above stays useful for individual dev/testing; this is what the app actually reads from.

**Getting the connection details** (dashboard → your cluster → **Connection Details** panel, "Connection parameters" view — use **Public network**, not VPC, since this is connected to from individual laptops, not another resource inside DO):

```
DB_HOST=<host from the panel>
DB_PORT=25060
DB_NAME=venue_scraper
DB_USER=<user from the panel>
DB_PASSWORD=<password from the panel>
DB_SSL_REQUIRED=true
```

Add those to `.env`. Also check the cluster's **Trusted Sources** (under Settings) — DO rejects connections from any IP not on that list, so add yours (and anyone else's who'll load data) there first.

`DB_SSL_REQUIRED=true` is all the SSL setup needed — verified working against the live cluster. (There's also a stricter `DB_SSL_CA=/path/to/downloaded-ca-cert.crt` option if you want the connection to verify against DO's specific CA certificate instead of just requiring encryption, but it's not necessary for this to work.)

Load exactly as local, but simpler — this is a real internet host, so skip `--add-host`/`host.docker.internal`:

```bash
docker run --rm --env-file .env -v ${PWD}/data:/app/data venue-scraper python load_to_mysql.py data/model_output/my_run.json
```

If the connection fails, the error message adapts based on `DB_HOST` and points at the DO-specific things to check (Trusted Sources, credentials, SSL config) instead of the local Docker networking advice.

**One-time-only, whoever sets up a brand new cluster** (already done for the current one — skip unless standing up another): create the cluster in the DO dashboard, then run `db/schema.sql` against it with any MySQL client before the app/team can use it — DO's managed clusters don't support the `docker-entrypoint-initdb.d` auto-init trick the local container uses.

---

## Output format

Each venue in the output JSON looks like this:

```json
{
  "venue_name": "333 Pacific",
  "Incentive Category": "Happy Hour",
  "Incentive Teaser": "Join us from 3-6pm Wednesday-Sunday for $9 cocktails",
  "Full Incentive Description": "...",
  "Days / Timing Restrictions": "Wednesday-Sunday, 3pm - 6pm",
  "Group Friendly?": "Yes",
  "Psychological Motivator Type": "Value",
  "Estimated Perceived Value ($ range)": "$9",
  "Expiration / Ongoing": "Ongoing",
  "incentives": [
    {
      "id": "happy_hour",
      "title": "Happy Hour",
      "description": "$9 cocktails and appetizers",
      "type": "recurring",
      "priority": null,
      "schedule": {
        "days": [3, 4, 5, 6, 7],
        "periods": [{ "start": "15:00:00", "end": "18:00:00" }],
        "timezone": "America/Los_Angeles"
      }
    }
  ]
}
```

The `incentives` block is what the backend consumes. `type` is one of:
- `recurring` — repeats on set days/times (has a `schedule` with `days` and `periods`)
- `always` — no time restriction, always available
- `date_range` — limited to a specific date window (has `start_date` / `end_date`)

---

## Incentive categories

| Category | Examples |
|---|---|
| Happy Hour | drink specials, afternoon deals |
| Discount | % off, coupon codes, early bird |
| Free | free entry, free events |
| Live Music | concerts, DJ nights, no cover |
| Early Entry | early access, arrive before X |
| Group Booking | group deals, party packages |
| Matinee Deal | twilight tickets, afternoon admission |
| No Incentive | no promotional content found |

---

## Other useful commands

### See what sentences are being scraped (before the model sees them)
```bash
docker run --rm --add-host=host.docker.internal:host-gateway --env-file .env -v ${PWD}/data:/app/data venue-scraper python scrape_inspect.py --source data/processed/YOUR_FILE.json --limit 10
```
Saves a JSON file to `data/inspect/` showing every sentence pulled from each venue.

### Inspect a single venue URL directly
```bash
docker run --rm --add-host=host.docker.internal:host-gateway --env-file .env -v ${PWD}/data:/app/data venue-scraper python scrape_inspect.py --url https://example.com --name "Venue Name"
```

### Retrain the ML model
```bash
docker run --rm --add-host=host.docker.internal:host-gateway --env-file .env -v ${PWD}/data:/app/data venue-scraper python src/trainmodel.py
```

---

## Project structure

```
venue-scraper/
├── src/
│   ├── scraper.py              # Scrapes websites (Playwright + Wayback + Serper)
│   ├── lovable_client.py       # Fetches + paginates venues from the Lovable API (--from-lovable)
│   ├── llama_extractor.py      # Local Llama (Ollama) model that classifies incentives
│   ├── teaser_rewriter.py      # Local Llama (Ollama) model that shortens long teasers
│   ├── model_extractor.py      # Legacy ML model + value-rescue helper; also has the Claude fallback path (unused by default pipeline)
│   ├── field_enricher.py       # Fills in structured output fields
│   ├── schedule_formatter.py   # Builds the backend incentives block
│   ├── claude_extractor.py     # Claude API extractor, used for model retraining (relabel_pipeline.py), not the default run
│   ├── relabel_pipeline.py     # Re-labels data for model retraining
│   └── trainmodel.py           # Trains the ML model
├── run_model_pipeline.py       # Main script — runs the full pipeline
├── load_to_mysql.py            # Loads pipeline output JSON into MySQL
├── scrape_inspect.py           # Debug tool — shows scraped sentences as JSON
├── db/
│   └── schema.sql              # MySQL schema (venues + venue_incentives)
├── docker-compose.yml          # Local MySQL for development
├── Dockerfile
├── data/
│   ├── processed/              # Input files go here (gitignored)
│   ├── model_output/           # Pipeline results (gitignored)
│   └── inspect/                # Sentence inspection output (gitignored)
└── models/                     # Trained model files (gitignored)
```
