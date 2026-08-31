# SCRAPY PROJECT

The scraper uses the Python frameworks **Scrapy** & Scrapy-Playwright to crawl venue websites, interact with JavaScript-rendered pages, and extract candidate text related to venues, happy hours, discounts, brunch specials, promotions, and other incentives. 

## 1. Project Goals
The primary goals of this project are to:
- Crawl restaurant & venue websites.
- Handle JavaScript heavy renders using Playwright.
- Interact with cookie banners, search inputs, location selectors, and modal dialogs.
- Detect text associated with incentives (i.e: happy hour, half-off, promotions, specials, etc.)
- Extract coherent text from DOM blocks.
- Remove duplicate & overly broad candidate blocks.
- Export candidate records as `.json` for later classification and formatting.

## 2. Setup Project 

### Virtual Environment 
---
```bash
cd scrapy_project # Navigate to scrapy_project directory

# Linux or MacOS
python3 -m venv .scrapy_env
source .scrapy_env/bin/activate
# Windows
python -m venv .scrapy_env
.scrapy_env\Scripts\Activate.ps1
```
### Dependencies 
---
```bash
pip install Scrapy
pip install scrapy-playwright
pip install playwright
pip install python-dotenv

playwright install chromium

# Verify:
scrapy_list # or
scrapy
```

### Environment variables
---
Venue discovery comes from two external APIs — the spider won't start
without these. Add them to the repo-root `.env` (the same file the main
pipeline uses; `load_dotenv()` walks up from wherever `scrapy crawl` is run
and finds it automatically):

```
# Lovable API — the venue directory this spider crawls
LOVABLE_API_URL=
LOVABLE_SCRAPER_API_KEY=

# Supabase — live-music event listings (public_events_v1 table)
SUPABASE_BASE_URL=
SUPABASE_KEY=
```

Missing any of these raises a clear error naming which one, rather than
crashing partway through a crawl.

Optional spider arguments (for incremental/limited Lovable API pulls):
```bash
scrapy crawl venue_scraper -a limit=50 -a from_date=2026-01-01
```

### 
```bash
# Switch to Main Development Branch (the ones labelled with 'scrapy')
git checkout <options> # OPTIONS: working-spider, spider/nav-scoring, spider/nav-scoring

git pull # Pull current changes

scrapy crawl venue_scraper # Run code

```
#### Observe Output from your Directory:
`/data/scrapy-playwright/scrapy_output.json`

## 3. Helpful Links & Resources
---
- [YouTube - Scrapy for Beginners - A Complete How To Example Web Scraping Project](https://youtu.be/s4jtkzHhLzY?si=V7IjT7HXRbxEjcFp)
- [YouTube Playlist - The Python Scrapy Playbook](https://youtube.com/playlist?list=PLkhQp3-EGsIi39YF-BE306DDX1xVSTHmn&si=B6T7FXOdLAnoiE86)