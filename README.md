# Venue Incentive Scraper

Scrapes venue websites and uses a trained TensorFlow classifier to extract and categorize promotional incentives (happy hours, discounts, live music, etc.), producing structured JSON output.

## How it works

1. **Scraper** — visits a venue's website across priority paths (`/happy-hour`, `/specials`, `/deals`, etc.), extracts only incentive-relevant paragraphs, and falls back to Playwright for JS-rendered pages.
2. **Model** — a Bidirectional LSTM classifier scores each sentence and picks the best incentive match using a `confidence × quality` ranking that filters out nav/CTA boilerplate.
3. **Field enricher** — maps business type and scraped text to structured output fields (cuisine category, group friendliness, timing, value, status).
4. **Pipeline** — ties the three together and writes results to `data/model_output/model_venues.json`.

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

## Setup

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install tensorflow playwright
playwright install chromium
```

> Playwright is optional — the scraper falls back to `requests` if it's not installed.

## Usage

### Run the model pipeline

```bash
# First 10 venues from the reference dataset
python run_model_pipeline.py

# Specific venues by index
python run_model_pipeline.py --indices 0,4,5,7

# Custom range and source file
python run_model_pipeline.py --offset 10 --limit 20 --source data/processed/venues.json
```

Output is saved to `data/model_output/model_venues.json`.

### Compare model output vs reference

```bash
python compare.py
# or specify files explicitly
python compare.py --original data/processed/venues.json --model data/model_output/model_venues.json
```

Shows per-venue field diffs and summary accuracy with exact and broad category matching.

### Quick benchmark

```bash
python benchmark.py
```

### Train or retrain the model

```bash
python src/trainmodel.py
```

Reads from `data/processed/` and saves the trained model to `models/`.

## Project structure

```
venue-scraper/
├── src/
│   ├── scraper.py          # Web scraper with Playwright fallback
│   ├── model_extractor.py  # Sentence classifier + quality scorer
│   ├── field_enricher.py   # Structured field mapping
│   └── trainmodel.py       # Model training script
├── run_model_pipeline.py   # Main pipeline entry point
├── compare.py              # Accuracy comparison tool
├── benchmark.py            # Quick benchmark against ground truth
├── data/
│   └── processed/          # Reference datasets (gitignored)
└── models/                 # Trained model files (gitignored)
```

## Output schema

Each venue record includes:

```json
{
  "venue_id": "...",
  "venue_name": "...",
  "Incentive Category": "Happy Hour",
  "Incentive Teaser": "Join us for happy hour Mon–Fri 3–6pm",
  "Full Incentive Description": "...",
  "Days / Timing Restrictions": "mon, fri, 3 pm, 6 pm",
  "Group Friendly?": "Likely",
  "Psychological Motivator Type": "Social",
  "Estimated Perceived Value ($ range)": "Unknown",
  "Expiration / Ongoing": "Ongoing",
  "_meta": {
    "model_confidence": 0.99,
    "scrape_time_s": 1.2,
    "inference_time_s": 0.8,
    "text_chars": 4500
  }
}
```
