# Venue Incentive Scraper

Scrapes venue websites and automatically detects promotional incentives (happy hours, discounts, live music, etc.), then outputs structured JSON for the backend.

---

## What it does

1. Visits each venue's website and looks for incentive-related content
2. If the site is blocked or JS-heavy, falls back to Wayback Machine or a Google search
3. Runs the content through an ML model to classify the incentive
4. If the model isn't confident enough, asks Claude API to decide
5. Outputs a structured JSON file with all fields filled in, including a backend-ready `incentives` schedule block

---

## Setup

### Requirements
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) installed and running
- A `.env` file in the project root with your API keys (see below)

### 1. Clone the repo

```bash
git clone https://github.com/spiderpilo/Venue-Scraper.git
cd Venue-Scraper
```

### 2. Create your `.env` file

Create a file called `.env` in the project root and add:

```
ANTHROPIC_API_KEY=your_key_here
SERPER_API_KEY=your_key_here
```

> ⚠️ Never commit this file. It's already in `.gitignore`.

### 3. Build the Docker image

```bash
docker build -t venue-scraper .
```

This takes 5–10 minutes the first time. After that it's instant.

---

## Running the pipeline

### Test run (10 venues)

```bash
docker run --rm --env-file .env -v ${PWD}/data:/app/data venue-scraper python run_model_pipeline.py --source data/processed/All_Venues_w_Incentives.json --limit 10
```

### Full run (all 1060 venues)

```bash
docker run --rm --env-file .env -v ${PWD}/data:/app/data venue-scraper python run_model_pipeline.py --source data/processed/All_Venues_w_Incentives.json --limit 1060 --output my_run.json
```

Output is saved to `data/model_output/` on your local machine.

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
docker run --rm --env-file .env -v ${PWD}/data:/app/data venue-scraper python run_model_pipeline.py --source data/processed/YOUR_FILE.json --limit 10
```

Start with `--limit 10` to verify it's working before doing the full run.

---

## Useful commands

### Run a small test batch
```bash
docker run --rm --env-file .env -v ${PWD}/data:/app/data venue-scraper python run_model_pipeline.py --source data/processed/All_Venues_w_Incentives.json --limit 10
```

### Run specific venues by row number
```bash
docker run --rm --env-file .env -v ${PWD}/data:/app/data venue-scraper python run_model_pipeline.py --source data/processed/All_Venues_w_Incentives.json --indices 0,5,12,20
```

### Run from a specific row onwards
```bash
docker run --rm --env-file .env -v ${PWD}/data:/app/data venue-scraper python run_model_pipeline.py --source data/processed/All_Venues_w_Incentives.json --offset 100 --limit 50
```

### See what sentences are being scraped (before the model sees them)
```bash
docker run --rm --env-file .env -v ${PWD}/data:/app/data venue-scraper python scrape_inspect.py --source data/processed/All_Venues_w_Incentives.json --limit 10
```
Saves a JSON file to `data/inspect/` showing every sentence pulled from each venue.

### Inspect a single venue URL directly
```bash
docker run --rm --env-file .env -v ${PWD}/data:/app/data venue-scraper python scrape_inspect.py --url https://example.com --name "Venue Name"
```

### Retrain the ML model
```bash
docker run --rm --env-file .env -v ${PWD}/data:/app/data venue-scraper python src/trainmodel.py
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
│   ├── model_extractor.py      # ML model that classifies incentives
│   ├── field_enricher.py       # Fills in structured output fields
│   ├── schedule_formatter.py   # Builds the backend incentives block
│   ├── claude_extractor.py     # Claude API fallback
│   ├── relabel_pipeline.py     # Re-labels data for model retraining
│   └── trainmodel.py           # Trains the ML model
├── run_model_pipeline.py       # Main script — runs the full pipeline
├── scrape_inspect.py           # Debug tool — shows scraped sentences as JSON
├── Dockerfile
├── data/
│   ├── processed/              # Input files go here (gitignored)
│   ├── model_output/           # Pipeline results (gitignored)
│   └── inspect/                # Sentence inspection output (gitignored)
└── models/                     # Trained model files (gitignored)
```
