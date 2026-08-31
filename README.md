# Venue Incentive Scraper

Scrapes venue websites and automatically detects promotional incentives (happy hours, discounts, live music, etc.), then outputs structured JSON for the backend.

---

## What it does

1. Visits each venue's website and looks for incentive-related content
2. If the site is blocked or JS-heavy, falls back to Wayback Machine or a Serper search
3. Runs the content through a local Llama model (via Ollama) to classify the incentive
4. Outputs a structured JSON file with all fields filled in, including a backend-ready `incentives` schedule block

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

`run_model_pipeline.py` checks this automatically before doing any scraping: if Ollama isn't reachable, or is reachable but missing `llama3.1:8b`/`llama3.2:3b`, it fails immediately with a message telling you which of the two is wrong. If you don't see that check fail, the model is loading correctly — if every venue in your output still comes back `No Incentive` with `model_confidence: 0.0` and `extraction_source: "no_result"` in `_meta`, something's still off; re-check steps 2 and the `--add-host` flag.

### 3. Create your `.env` file

Create a file called `.env` in the project root and add:

```
ANTHROPIC_API_KEY=your_key_here
SERPER_API_KEY=your_key_here
```

> ⚠️ Never commit this file. It's already in `.gitignore`.
>
> `SERPER_API_KEY` is used as a scraping fallback (when a venue's site can't be reached directly or Wayback has nothing) and for pricing lookups when a detected incentive has no listed price — get a free key at [serper.dev](https://serper.dev). `ANTHROPIC_API_KEY` is not called by the default pipeline (`run_model_pipeline.py`) today; it's only used by `src/relabel_pipeline.py` for model retraining. Both keys can be placeholder values if you're not using those paths, but the `.env` file must exist.

### 4. Build the Docker image

```bash
docker build -t venue-scraper .
```

This takes 5–10 minutes the first time. After that it's instant.

---

## Running the pipeline

### Test run (10 venues)

```bash
docker run --rm --add-host=host.docker.internal:host-gateway --env-file .env -v ${PWD}/data:/app/data venue-scraper python run_model_pipeline.py --source data/processed/All_Venues_w_Incentives.json --limit 10
```

### Full run (all 1060 venues)

```bash
docker run --rm --add-host=host.docker.internal:host-gateway --env-file .env -v ${PWD}/data:/app/data venue-scraper python run_model_pipeline.py --source data/processed/All_Venues_w_Incentives.json --limit 1060 --output my_run.json
```

Output is saved to `data/model_output/` on your local machine.

---

## Loading into MySQL

The app pulls venue/incentive data from MySQL, not directly from the pipeline's
JSON output. `db/schema.sql` defines two tables:

- `venues` — one row per venue (name, address, business type, source URL,
  plus pipeline QA fields: `scrape_source`, `model_confidence`, `extraction_source`)
- `venue_incentives` — one row per detected incentive, FK'd to `venues`.
  Empty for venues where `Incentive Category` is "No Incentive" (matches the
  JSON output's `incentives: []`). The `schedule` column stores the same
  nested JSON documented above (`days`/`periods`/`timezone` for recurring
  incentives, `start_date`/`end_date` for date-bounded ones).

### 1. Start MySQL

```bash
docker compose up -d mysql
```

This starts a local MySQL 8 container and runs `db/schema.sql` automatically
on first boot (only on first boot — if you change the schema later, either
drop the `mysql_data` volume and let it re-init, or apply the change with
`ALTER TABLE` / re-run the `.sql` file by hand). Default credentials are in
`.env` (`DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`) and match
`docker-compose.yml`'s defaults, so no extra setup is needed for local dev.

This is a local dev database, not the production one — once the app team
has a real MySQL server, point `DB_HOST`/`DB_PORT`/etc. at that instead.

### 2. Load pipeline output

```bash
docker run --rm --add-host=host.docker.internal:host-gateway --env-file .env \
  -e DB_HOST=host.docker.internal -v ${PWD}/data:/app/data venue-scraper \
  python load_to_mysql.py data/model_output/my_run.json
```

Accepts multiple files or a glob (`data/model_output/*.json`). Loading is
idempotent and safe to re-run — each venue is upserted on `venue_id`, and
that venue's incentive rows are replaced with whatever's in the file you just
loaded, so re-loading the same or an overlapping export won't create
duplicates.

`DB_HOST=host.docker.internal` + `--add-host` is required because the
pipeline container needs to reach MySQL running on your host machine — same
reason the model pipeline commands above need it for Ollama. If you're
running `load_to_mysql.py` directly on the host (outside Docker, e.g. in a
local venv with `pip install -r requirements.txt`), use `DB_HOST=127.0.0.1`
instead and drop `--add-host`.

The script checks MySQL is reachable before doing anything else — if it
isn't, it fails immediately with which of the two setups above you're likely
missing, rather than a raw connection traceback.

### 3. Production: DigitalOcean Managed MySQL

The team's shared/production data lives on DigitalOcean's Managed MySQL, not
the local docker-compose instance above (that stays useful for individual
dev/testing).

**One-time setup (whoever creates the cluster):**

1. In the DigitalOcean dashboard: Databases → Create Database Cluster → MySQL.
2. Once it's up, open the cluster's **Connection Details** panel for the
   host, port, username, password, and database name.
3. Download the CA certificate from the same panel (**Download CA
   Certificate**) and save it somewhere on your machine, e.g. `~/.mysql/do-ca-certificate.crt`.
4. Under **Trusted Sources**, add whichever machines will run
   `load_to_mysql.py` (your IP, a teammate's IP, or a CI runner) — DO
   rejects connections from anywhere not on this list.
5. Connect with a MySQL client using those details and run `db/schema.sql`
   once to create the tables (DO's managed clusters don't support the
   `docker-entrypoint-initdb.d` auto-init trick the local container uses).

**Everyone loading data**, add to `.env`:

```
DB_HOST=<from the DO connection details panel>
DB_PORT=25060
DB_NAME=venue_scraper
DB_USER=<from DO>
DB_PASSWORD=<from DO>
DB_SSL_CA=/path/to/do-ca-certificate.crt
```

Then load exactly as before, but simpler — this is a real internet host, so
skip `--add-host`/`host.docker.internal` and mount the CA cert into the
container:

```bash
docker run --rm --env-file .env \
  -v ${PWD}/data:/app/data \
  -v ~/.mysql/do-ca-certificate.crt:/app/ca.crt:ro \
  -e DB_SSL_CA=/app/ca.crt \
  venue-scraper python load_to_mysql.py data/model_output/my_run.json
```

If the connection fails, the error message adapts based on `DB_HOST` and
points at the DO-specific things to check (Trusted Sources, the CA cert
path, credentials) instead of the local Docker networking advice.

---

## Pulling venues from the Lovable API

Instead of manually dropping an export file into `data/processed/` and
renaming its columns by hand, the pipeline can fetch venues live from the
Lovable API (a Supabase Edge Function that returns the venue directory, with
Google Place IDs, websites, categories, etc.) and map its fields
automatically (`website` → `Source URL`, `category` → `Business Type`).

Add to `.env`:
```
LOVABLE_API_URL=
LOVABLE_SCRAPER_API_KEY=
```

Then run with `--from-lovable` instead of `--source`:

```bash
docker run --rm --add-host=host.docker.internal:host-gateway --env-file .env -v ${PWD}/data:/app/data venue-scraper python run_model_pipeline.py --from-lovable --limit 10
```

`--offset`/`--limit`/`--indices` still work the same way, slicing the venues
after they're fetched. For incremental pulls (only venues updated since a
given date), add `--lovable-from-date 2026-08-01` — note this passes the
date straight through to the API's own `from_date` filter, which hasn't been
verified against the live API the way pagination has.

---

## Using a different gold standard file

If you have a new list of venues to run:

1. Drop your new JSON file into the `data/processed/` folder
2. Make sure the file has these fields per venue:
   - `Source URL` — the venue's website
   - `venue_name` — display name
   - `Business Type` — e.g. Bar, Nightclub, Restaurant
   - `city` — used as a fallback search hint
3. Run it by pointing `--source` at your file:

```bash
docker run --rm --add-host=host.docker.internal:host-gateway --env-file .env -v ${PWD}/data:/app/data venue-scraper python run_model_pipeline.py --source data/processed/YOUR_FILE.json --limit 10
```

Start with `--limit 10` to verify it's working before doing the full run.

---

## Useful commands

### Run a small test batch
```bash
docker run --rm --add-host=host.docker.internal:host-gateway --env-file .env -v ${PWD}/data:/app/data venue-scraper python run_model_pipeline.py --source data/processed/All_Venues_w_Incentives.json --limit 10
```

### Run specific venues by row number
```bash
docker run --rm --add-host=host.docker.internal:host-gateway --env-file .env -v ${PWD}/data:/app/data venue-scraper python run_model_pipeline.py --source data/processed/All_Venues_w_Incentives.json --indices 0,5,12,20
```

### Run from a specific row onwards
```bash
docker run --rm --add-host=host.docker.internal:host-gateway --env-file .env -v ${PWD}/data:/app/data venue-scraper python run_model_pipeline.py --source data/processed/All_Venues_w_Incentives.json --offset 100 --limit 50
```

### See what sentences are being scraped (before the model sees them)
```bash
docker run --rm --add-host=host.docker.internal:host-gateway --env-file .env -v ${PWD}/data:/app/data venue-scraper python scrape_inspect.py --source data/processed/All_Venues_w_Incentives.json --limit 10
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
