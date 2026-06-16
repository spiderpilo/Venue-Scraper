# Venue Incentive Scraper

Scrapes venue websites and uses a trained TensorFlow classifier to extract and categorize promotional incentives (happy hours, discounts, live music, etc.), producing structured JSON output.

## How it works

1. **Scraper** — visits a venue's website across priority paths (`/happy-hour`, `/specials`, `/deals`, etc.), falls back to Playwright for JS-rendered pages, Wayback Machine for blocked sites, and Serper for fully unreachable ones.
2. **Model** — a Bidirectional LSTM classifier scores each sentence and picks the best incentive match. Falls back to Claude API when confidence is low.
3. **Field enricher** — maps business type and scraped text to structured output fields (cuisine category, group friendliness, timing, value, status).
4. **Schedule formatter** — converts timing strings into a typed `incentives` block (recurring/always/date_range) with ISO day numbers and `HH:MM:SS` periods for the backend.
5. **Pipeline** — ties all four together and writes results to `data/model_output/`.

## Incentive categories

| Label | Examples |
|---|---|
| Happy Hour | drink specials, afternoon deals, lunch combos |
| Discount | % off, coupon codes, early bird tickets |
| Free | free entry, free events, pay what you can |
| Live Music | concerts, DJ nights, no cover charge |
| Early Entry | early access + drink, pre-sale entry |
| Group Booking | group deals, party packages, corporate events |
| Matinee Deal | twilight tickets, afternoon admission |
| No Incentive | no promotional content found |

---

## Quickstart (Docker) — recommended

Docker is the easiest way to run this. No local Python setup needed.

**Prerequisites:** [Docker Desktop](https://www.docker.com/products/docker-desktop/) installed and running.

### 1. Clone and set up environment

```powershell
git clone https://github.com/spiderpilo/Venue-Scraper.git
cd Venue-Scraper
```

Create a `.env` file in the project root with your API keys:

```
ANTHROPIC_API_KEY=your_key_here
SERPER_API_KEY=your_key_here
```

### 2. Build the Docker image

```powershell
docker build -t venue-scraper .
```

First build takes 5–10 minutes (downloads Python, TensorFlow, Playwright). Subsequent builds are fast.

### 3. Run the pipeline

```powershell
# Test with 10 venues
docker run --rm --env-file .env -v ${PWD}/data:/app/data venue-scraper python run_model_pipeline.py --source data/processed/All_Venues_w_Incentives.json --limit 10

# Full run (all venues)
docker run --rm --env-file .env -v ${PWD}/data:/app/data venue-scraper python run_model_pipeline.py --source data/processed/All_Venues_w_Incentives.json --limit 1060 --output my_run.json

# Specific venues by index
docker run --rm --env-file .env -v ${PWD}/data:/app/data venue-scraper python run_model_pipeline.py --source data/processed/All_Venues_w_Incentives.json --indices 0,3,7,12
```

Output is saved to `data/model_output/` on your local machine.

### 4. Inspect scraped sentences

See exactly which sentences are being fed to the model:

```powershell
docker run --rm --env-file .env -v ${PWD}/data:/app/data venue-scraper python scrape_inspect.py --source data/processed/All_Venues_w_Incentives.json --limit 10
```

Output is saved to `data/inspect/inspect_YYYY-MM-DD_HHMM.json`.

### Using a different gold standard file

Drop the new file into `data/processed/` and pass it via `--source`:

```powershell
docker run --rm --env-file .env -v ${PWD}/data:/app/data venue-scraper python run_model_pipeline.py --source data/processed/YOUR_NEW_FILE.json --limit 10
```

The file needs these fields per venue: `Source URL`, `venue_name`, `Business Type`, `city`.

---

## Local setup (alternative)

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
```

Then use the same commands without the `docker run ... venue-scraper` prefix:

```bash
python run_model_pipeline.py --source data/processed/All_Venues_w_Incentives.json --limit 10
python scrape_inspect.py --limit 10
```

---

## All commands

| Command | What it does |
|---|---|
| `python run_model_pipeline.py --source <file> --limit <n>` | Run pipeline on N venues |
| `python run_model_pipeline.py --indices 0,3,7` | Run on specific venue indices |
| `python scrape_inspect.py --source <file> --limit <n>` | Dump scraped sentences to JSON |
| `python scrape_inspect.py --url https://example.com --name "Venue"` | Inspect a single URL |
| `python src/trainmodel.py` | Train / retrain the ML model |
| `python compare.py` | Compare model output vs reference |
| `python benchmark.py` | Quick accuracy benchmark |

---

## Project structure

```
venue-scraper/
├── src/
│   ├── scraper.py              # Web scraper (Playwright + Wayback + Serper fallbacks)
│   ├── model_extractor.py      # BiLSTM sentence classifier
│   ├── field_enricher.py       # Structured field mapping
│   ├── schedule_formatter.py   # Converts timing strings to backend schedule format
│   ├── claude_extractor.py     # Claude API fallback extractor
│   ├── relabel_pipeline.py     # Re-labels pipeline output for training
│   └── trainmodel.py           # Model training script
├── run_model_pipeline.py       # Main pipeline entry point
├── scrape_inspect.py           # Sentence inspection tool
├── compare.py                  # Accuracy comparison tool
├── benchmark.py                # Quick benchmark against ground truth
├── Dockerfile                  # Docker build config
├── data/
│   └── processed/              # Gold standard input files (gitignored)
│   └── model_output/           # Pipeline results (gitignored)
│   └── inspect/                # Sentence inspection output (gitignored)
└── models/                     # Trained model files (gitignored)
```

---

## Output schema

Each venue record includes:

```json
{
  "venue_id": "...",
  "venue_name": "...",
  "Incentive Category": "Happy Hour",
  "Incentive Teaser": "Join us for happy hour Mon–Fri 3–6pm",
  "Full Incentive Description": "...",
  "Days / Timing Restrictions": "Monday - Friday, 3pm - 6pm",
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
        "days": [1, 2, 3, 4, 5],
        "periods": [{ "start": "15:00:00", "end": "18:00:00" }],
        "timezone": "America/Los_Angeles"
      }
    }
  ],
  "_meta": {
    "model_confidence": 0.89,
    "scrape_time_s": 1.2,
    "inference_time_s": 0.8,
    "text_chars": 4500,
    "scrape_source": "direct",
    "extraction_source": "ml_model"
  }
}
```
