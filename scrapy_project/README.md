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

playwright install chromium

# Verify:
scrapy_list # or
scrapy
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