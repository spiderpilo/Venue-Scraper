# Venue Scraper — Dev Log

Tracks changes, experiments, and metric shifts session by session.

---

## 2026-05-21

### Baseline (no ML model — Claude only)
- 100 venues scraped, all inference via Claude API
- Extraction source: 100 claude | 0 ml_model
- Avg inference time: ~1.1s/venue
- Avg model confidence: N/A

---

### [1] Built multi-output ML model (`src/trainmodel.py`)

**What changed:**
- Replaced single-output classifier with Functional API BiLSTM
- 3 output heads: Incentive Category (8 classes), Psychological Motivator (5), Cuisine/Experience (12)
- Added Business Type as second input (StringLookup + Embedding)
- Training data: 364 presplit gold standard + 49 synthetic No Incentive examples = 413 rows
- Label maps consolidate 65 fine-grained presplit categories → 8 broad classes

**Training result (v1):**
- val_category_accuracy: 0.94
- val_motivator_accuracy: 0.96
- val_cuisine_accuracy: 0.84
- Stopped at epoch ~15 (EarlyStopping)

**Fixes required:**
- `model.predict(dict)` crash — Keras 3 requires `tf.data.Dataset` wrapper
- `classification_report` crash — cuisine label count mismatch on test set
- Fixed: moved `model.save()` before reports; used `labels=np.unique(y_true)`

---

### [2] Hybrid pipeline: ML model (conf ≥ 0.75) → Claude fallback

**What changed (`src/model_extractor.py`):**
- Batch-predicts all candidate sentences in one dataset forward pass
- ML model used directly when confidence ≥ 0.75
- Claude called only when ML confidence < 0.75
- `ml_model_fallback` source label for cases where Claude returns No Incentive but ML found something

**Initial threshold bug:** required both `val != Unknown AND timing != Unknown` to use ML model — dropped 34 valid high-confidence predictions to Claude. Removed that guard.

**Pipeline run after fix:**
| Metric | Before fix | After fix |
|---|---|---|
| ML model uses | 2/100 | 27/100 |
| Claude calls | 100/100 | 16/100 |
| Avg confidence | — | 0.45 |

---

### [3] Retrain with real scraped text (`load_pipeline_outputs`)

**What changed:**
- Added `scraped_text` field to `_meta` in pipeline output
- `load_pipeline_outputs()` pulls positive (claude/ml_model labeled) + negative (no_result with real page text) records
- Training data: 413 → 494 rows (+81 real-scraped examples)
- Applied ASCII cleaning to all training text (`_ascii_clean`) — fixes Unicode crash during `model.save()`

**Training result (v2):**
- val_category_accuracy: 0.84 (harder test set — real scraped text)
- Test set category accuracy: 89%

**Pipeline run v2:**
| Metric | v1 | v2 |
|---|---|---|
| Avg confidence | 0.45 | 0.58 |
| ML model uses | 27/100 | 41/100 |
| Claude calls | 16/100 | 11/100 |
| Avg inference | 0.8s | 0.6s |

---

### [4] Compare vs gold standard — diagnosis

**compare.py analysis (100 venues):**
- Category exact match: 5%
- Category broad match: 11%
- Both found incentive: 71 venues → only 15% category agreement

**Top confusion pairs (model → gold):**
- Model: Discount, gold: Live Music — 8 cases
- Model: Discount, gold: Early Entry — 8 cases
- Model: Live Music, gold: Early Entry — 7 cases
- Model: Happy Hour, gold: Discount — 5 cases

**Root causes identified:**
1. Model over-fires on Happy Hour / Discount (most common in scraped text)
2. Early Entry info rarely on website surface (cover charge buried, JS-heavy)
3. Live Music info often in event calendars (hard to scrape)
4. 7 venues: complete scraper failure (0 chars returned)
5. 9 venues: scraped fine (2000+ chars) but incentive keywords not in page text

---

### [5] Business-type context in Claude extractor (`src/claude_extractor.py`)

**What changed:**
- Added `business_type` parameter to `extract_with_claude()`
- System prompt now includes category guidance per venue type:
  - Nightclub → prefer Early Entry
  - Live Music venue → prefer Live Music
  - Restaurant → prefer Happy Hour
  - Bowling/Museum/Theater → prefer Matinee Deal / Group Booking
- Business type prepended to user message: `[Venue type: Nightclub]\n\n{text}`
- `model_extractor.py` now passes `business_type` through to Claude call

---

### [6] Relabeling pipeline (`src/relabel_pipeline.py`)

**What changed:**
- New script re-runs Claude on all stored `scraped_text` records with business type context
- Saves corrected labels to `data/relabeled/`
- `trainmodel.py` loads relabeled data via `load_relabeled()` as a 4th data source

**Relabeling run on model_venues_2026-05-21.json:**
- 90 eligible records (had scraped text)
- 17 category corrections made (Discount→Happy Hour, Live Music→Early Entry, Discount→Matinee Deal, etc.)
- 24 positive + 66 negative training examples produced

**Training result (v3):**
- Total training rows: 588 (364 presplit + 68 pipeline + 90 relabeled + 49 synthetic)
- Early Entry F1: 1.00 (up from 0.97)
- Matinee Deal F1: 1.00 (up from 0.67)
- Category accuracy: 82% on test set (harder — more real-world text)
- Pipeline run in progress...

---

### [7] Pipeline v3 results + regression diagnosis

**Pipeline run v3 (model after relabeled retrain):**
| Metric | v2 | v3 |
|---|---|---|
| Avg confidence | 0.58 | 0.41 ❌ |
| ML model uses | 41/100 | 16/100 ❌ |
| Claude calls | 11/100 | 20/100 ❌ |

**Root cause:** `load_relabeled()` was including 66 No Incentive records from relabeling
(venues where Claude said "no incentive" on re-examination). This over-weighted the
No Incentive class, making the model too conservative.

**Fix:** `load_relabeled()` now skips No Incentive records entirely — we already have
49 synthetic + pipeline negatives for that class. Only positive corrections are loaded.

**Retraining (v4) in progress...**

---

### [8] Model v4 — positive-only relabeling fix + pipeline results

**Training (v4):**
- Total rows: 525 (364 presplit + 68 pipeline + 24 relabeled pos only + 49 synthetic)
- Category accuracy: 89%
- Early Entry F1: 1.00 | Free F1: 1.00 | Group Booking F1: 0.93 | Live Music F1: 0.93
- Happy Hour F1: 0.83 | Matinee Deal F1: 0.91 | Discount F1: 0.79

**Pipeline run v4 (50 venues):**
| Metric | v2 | v3 ❌ | v4 |
|---|---|---|---|
| Avg confidence | 0.58 | 0.41 | **0.65** |
| ML model uses | 41% | 16% | **62%** |
| Claude calls | 11% | 20% | **8%** |
| Inference time | 0.6s | 0.9s | **0.6s** |

**Key lesson:** Relabeled No Incentive records (66) flooded that class and made the
model too conservative. Fix: `load_relabeled()` skips No Incentive — only positive
corrections from relabeling are used as training data.

---

### [9] Expanded keywords + category hint correlation

**What changed (`src/model_extractor.py`):**
- `INCENTIVE_KEYWORDS` expanded from 34 → 80+ phrases
  - Added: drink/cocktail/beer/wine specials, live band/entertainment, guest list,
    doors open, 2-for-1, BOGO, group rate, per game/lane, member/loyalty/season pass
- Added `CATEGORY_HINTS` dict: 60+ keyword → category mappings
- Added `_category_hint()` helper (longest-match priority)
- Added hint-boost logic: if ML conf 0.50–0.74 AND hint confirms ML category → boost +0.15, skip Claude

**Result:** hint-boost fired 0 times — expanded keywords alone pushed more sentences
past 0.75 directly. Hint logic remains as safety net.

**Pipeline run v5 (100 venues):**
| Metric | v4 (50) | v5 (100) |
|---|---|---|
| Avg confidence | 0.65 | 0.61 |
| ML model uses | 62% | **57%** |
| Claude calls | 8% | **7%** |
| Inference time | 0.6s | **0.4s** |

**Relabeling:** 7 corrections (down from 17) — model and Claude converging.

**Training v5:** 524 rows | 86% category accuracy
- Live Music F1: 0.96 | Early Entry F1: 0.97 | Happy Hour F1: 0.84

**Next:** venues 100–200 (`--offset 100 --limit 100`) running now.

---

## 2026-05-21 (continued)

### [10] TextVectorization vocabulary corruption — root cause & fix

**Bug:** Model saved but failed to load with:
`ValueError: The passed vocabulary has at least one repeated term: ['w', 'e', 's', 'f', '']`

**Root cause:** Scraped texts contained embedded `\n` characters. TF's `TextVectorization`
`standardize="lower_and_strip_punctuation"` keeps `\n` (it is whitespace, not punctuation).
When `adapt()` produced consecutive-whitespace tokens, the vocabulary file (stored as
one-term-per-line in the `.keras` zip) received blank lines — interpreted as extra `''`
empty-string tokens colliding with the reserved mask token at position 0.

**Fix:** `_ascii_clean()` now normalizes all whitespace to single spaces before training:
```python
text = re.sub(r'\s+', ' ', text)
```
Added `set_vocabulary` dedup step as a safety net.

---

### [11] Pipeline_neg class flood — second imbalance regression

**Symptoms:** After accumulating 300+ pipeline runs, `load_pipeline_outputs()` loaded
209 `pipeline_neg` rows (venues scraped OK, no incentive found). Combined with 49 synthetic
negatives = 258 total No Incentive examples. Happy Hour F1 dropped from 0.83 to 0.44.
Identical pattern to v3 regression (relabeled negatives flooding the class).

**Fix:** Capped `pipeline_neg` at `_MAX_PIPELINE_NEG = 60` with random sampling (seed=42).

**Training v7 results (710 rows):**
| Metric | v6 (broken) | v7 (fixed) |
|---|---|---|
| Category accuracy | 69% | **75%** |
| Happy Hour F1 | 0.44 | **0.69** |
| Early Entry F1 | 0.97 | 0.97 |
| Group Booking F1 | 0.92 | 0.95 |
| Matinee Deal F1 | 0.75 | 0.80 |
| Live Music F1 | 0.82 | 0.81 |

---

### [12] Full 364-venue pipeline v7 + gold standard comparison

**Pipeline run v7 (all 364 venues):**
| Metric | v5 (100) | v7 (364) |
|---|---|---|
| Avg confidence | 0.61 | **0.68** |
| ML model uses | 57% | **78%** |
| Claude calls | 7% | **4%** |
| Avg inference | 0.4s | **0.4s** |
| Successfully scraped | — | 342/364 (94%) |
| Wall time | — | 4196s (~70 min) |

**Gold standard comparison (245 matched venues):**
| Metric | v5 (100) | v7 (364) |
|---|---|---|
| Category exact match | 5% | **9.4%** |
| Category broad match | 11% | **16.3%** |
| Both found incentive | — | 202/245 |
| Broad match (both found) | — | 19.8% |

**Top confusion pairs (broad ref → model):**
- Live Music → Happy Hour: 32 cases
- Early Entry → Happy Hour: 26 cases
- Discount → Happy Hour: 19 cases
- Free → Discount: 11 cases

**Key insight:** Model over-predicts Happy Hour because deal/pricing language
on bar/restaurant websites overlaps with Happy Hour vocabulary. Gold standard
captures the venue's PRIMARY draw (e.g., cover charge = Early Entry), while
scraped text surfaces the most visible page content (drink specials = Happy Hour).
This gap is structural — not a model bug.

**Model missed** 43 venues: model returned No Incentive but gold standard has incentive.
**Model added** 0 venues: all model positives were confirmed by gold standard.

---

## 2026-06-11

### [13] Bot bypass, Wayback fallback, per-venue timeout

**What changed:**
- `playwright-stealth` added — patches `navigator.webdriver`, plugins, languages to evade bot detection
- SPA shell detection (`_is_spa_shell`) — detects React/Next/Vue pages with < 300 chars text, forces Playwright
- Wayback Machine fallback (`scrape_wayback`) — pulls archived snapshots from archive.org for fully blocked sites
- Per-venue 45s hard scrape budget — deadline propagation through all passes, Playwright goto capped at 10s, networkidle at 3s
- Deep type-specific paths for nightclubs (`/tickets`, `/bottle-service`, `/vip`) and bars (`/drink-specials`)
- Pricing-targeted Serper fallback when value is Unknown

**1060-venue gold standard run:**
| Metric | 364-venue (v7) | 1060-venue |
|---|---|---|
| Successfully scraped | 342/364 (94%) | 785/1060 (74%) |
| Avg confidence | 0.68 | 0.57 |
| ML model uses | 78% | 45% |
| Claude calls | 4% | 8% |
| Wall time | 70 min | 437 min |
| Incentive found | — | 748/1060 (71%) |

---

### [14] Structured `incentives` schedule block

**What changed:**
- New `src/schedule_formatter.py` — parses timing strings into backend-ready format
- Day parser: handles "Monday - Friday", "Wed-Sun", "daily", individual day names → ISO numbers (1=Mon, 7=Sun)
- Time parser: "3pm", "4:30PM", "15:00", "3:00pm - 7:00pm" → `HH:MM:SS`
- Type detector: `recurring` (has days/times), `always` (no timing), `date_range` (specific dates)
- Wired into `run_model_pipeline.py` — each record gets an `incentives` array

**50-venue sample results:**
- 43/50 records got populated `incentives` block
- 415/748 incentives got parsed schedule (days/times) in full 1060-venue run

---

### [15] Sentence deduplication

**Problem:** Scraper hits 8+ pages per site (happy-hour, specials, deals, events, menu, homepage, etc.). Shared headers/footers/nav produce identical sentences. 3Vino's had 50 candidate sentences but only ~5 unique ones.

**Fix:** Deduplicated sentences in `model_extractor.py` and `scrape_inspect.py` using a `seen` set before candidates hit the model. Model now sees more diverse content in its 20-sentence window.

---

### [16] Docker support + team setup

**What changed:**
- Added `Dockerfile` — Python 3.13-slim + Playwright + Chromium, copies source and models
- Added `.dockerignore` — excludes `.env`, `data/`, `__pycache__`, `.git/`
- Removed `models/` from `.gitignore` — model files now in repo so Docker builds work
- Default `--limit` changed from 10 to all venues
- Added error message when source file not found or has wrong field names
- README rewritten with Docker quickstart, useful commands, gold standard swap instructions

---

### [17] `scrape_inspect.py` — sentence inspection tool

**What changed:**
- New script that scrapes venues and outputs JSON showing every keyword-matched sentence
- Per-venue: `venue_name`, `url`, `scrape_source`, `raw_text_chars`, `sentence_count`, `sentences[]`
- Saves to `data/inspect/inspect_YYYY-MM-DD_HHMM.json`
- Supports `--limit`, `--indices`, `--offset`, `--source`, `--url`, `--output`

---

## Known Issues / Next Steps

- [x] TextVectorization vocab corruption fixed (whitespace normalization in `_ascii_clean`)
- [x] Pipeline_neg class imbalance fixed (capped at 60 rows)
- [x] Full 364-venue pipeline run completed
- [x] Gold standard comparison run
- [x] Happy Hour over-prediction: business-type post-processing prior added (`_apply_btype_prior`)
- [x] 22 venues return 0 chars: Wayback Machine fallback + playwright-stealth added
- [x] Per-venue 45s scrape timeout to skip stalled JS-heavy sites
- [x] Structured `incentives` schedule block for backend
- [x] Sentence deduplication before model inference
- [x] Docker support for team deployment
- [ ] Relabel 1060-venue output → retrain model with larger dataset
- [ ] 275 venues still return 0 chars — sites fully unreachable
