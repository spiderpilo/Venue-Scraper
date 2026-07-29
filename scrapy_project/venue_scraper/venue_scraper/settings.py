# ─────────────────────────────────────────────────────────────────────────────
# settings.py — Global Scrapy configuration
#
# These are the DEFAULT settings for the whole project. Individual spiders
# can override any of these via their own `custom_settings` dict.
# ─────────────────────────────────────────────────────────────────────────────

BOT_NAME = "venue_scraper"

# Tell Scrapy where to find spider files
SPIDER_MODULES = ["venue_scraper.spiders"]
NEWSPIDER_MODULE = "venue_scraper.spiders"

# ── Output ────────────────────────────────────────────────────────────────────
# FEEDS tells Scrapy where to save the yielded items.
# Here it writes to a JSON file. "overwrite: True" clears the file each run.
FEEDS = {
    "data/scrapy-playwright/scaper_output.json" : { # Save scraped items in multiple numbered files
        "format": "json",
        # "batch_item_count": 100,
        "overwrite": True, # No overriding, use placeholders in the output path
    }
}

FEED_EXPORT_INDENT = 4 # pretty-print the JSON using 4 spaces per nesting level

# Don't send a User-Agent header (Playwright handles browser identity instead)
USER_AGENT = None

# ── Concurrency & politeness ──────────────────────────────────────────────────
# Only 2 requests running at the same time across the whole crawler
CONCURRENT_REQUESTS = 2
# Never more than 1 request at a time to the same domain — avoids getting blocked
CONCURRENT_REQUESTS_PER_DOMAIN = 1
# Wait 3 seconds between requests to the same site (polite crawling)
DOWNLOAD_DELAY = 3.0
# Randomize the delay (between 1.5s–6s) so it looks more like a real user
RANDOMIZE_DOWNLOAD_DELAY = True

COOKIES_ENABLED = True

# None = let Playwright manage headers; setting this to None avoids conflicts
PLAYWRIGHT_PROCESS_REQUEST_HEADERS = None

# ── AutoThrottle ──────────────────────────────────────────────────────────────
# AutoThrottle automatically adjusts the download delay based on server response
# times. If the server is slow, it backs off; if it's fast, it speeds up slightly.
AUTOTHROTTLE_ENABLED = True
AUTOTHROTTLE_START_DELAY = 3.0       # Start at 3s between requests
AUTOTHROTTLE_MAX_DELAY = 30.0        # Never wait more than 30s
AUTOTHROTTLE_TARGET_CONCURRENCY = 0.5  # Target 0.5 parallel requests per domain
AUTOTHROTTLE_DEBUG = False           # Set True to see throttle adjustments in logs

# ── HTTP Cache (disabled) ─────────────────────────────────────────────────────
# Caching would save pages locally so re-runs don't re-fetch the same pages.
# Disabled here because we want fresh data every run (venue offers change).
HTTPCACHE_ENABLED = False
HTTPCACHE_EXPIRATION_SECS = 60 * 60 * 24  # If enabled: cache expires after 24h
HTTPCACHE_DIR = "httpcache"
HTTPCACHE_IGNORE_HTTP_CODES = [500, 502, 503, 504, 522, 524, 408, 429]

# ── Retries ───────────────────────────────────────────────────────────────────
# If a request fails with one of these HTTP error codes, retry it once.
# Covers server errors and rate-limiting (429 = Too Many Requests).
RETRY_ENABLED = True
RETRY_TIMES = 1
RETRY_HTTP_CODES = [500, 502, 503, 504, 522, 524, 408, 429]

LOG_LEVEL = "INFO"

DOWNLOADER_MIDDLEWARES = {
    # Keep default Scrapy middlewares.
    # Do not enable proxy rotation for real venue websites at this stage.
}
"""
# Scrapy settings for venue_scraper project
#
# For simplicity, this file contains only settings considered important or
# commonly used. You can find more settings consulting the documentation:
#
#     https://docs.scrapy.org/en/latest/topics/settings.html
#     https://docs.scrapy.org/en/latest/topics/downloader-middleware.html
#     https://docs.scrapy.org/en/latest/topics/spider-middleware.html

BOT_NAME = "venue_scraper"

SPIDER_MODULES = ["venue_scraper.spiders"]
NEWSPIDER_MODULE = "venue_scraper.spiders"

ADDONS = {}


# Crawl responsibly by identifying yourself (and your website) on the user-agent
#USER_AGENT = "venue_scraper (+http://www.yourdomain.com)"

# Obey robots.txt rules
ROBOTSTXT_OBEY = True

# Concurrency and throttling settings
#CONCURRENT_REQUESTS = 16
CONCURRENT_REQUESTS_PER_DOMAIN = 1
DOWNLOAD_DELAY = 1

# Disable cookies (enabled by default)
#COOKIES_ENABLED = False

# Disable Telnet Console (enabled by default)
#TELNETCONSOLE_ENABLED = False

# Override the default request headers:
#DEFAULT_REQUEST_HEADERS = {
#    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
#    "Accept-Language": "en",
#}

# Enable or disable spider middlewares
# See https://docs.scrapy.org/en/latest/topics/spider-middleware.html
#SPIDER_MIDDLEWARES = {
#    "venue_scraper.middlewares.VenueScraperSpiderMiddleware": 543,
#}

# Enable or disable downloader middlewares
# See https://docs.scrapy.org/en/latest/topics/downloader-middleware.html
#DOWNLOADER_MIDDLEWARES = {
#    "venue_scraper.middlewares.VenueScraperDownloaderMiddleware": 543,
#}

# Enable or disable extensions
# See https://docs.scrapy.org/en/latest/topics/extensions.html
#EXTENSIONS = {
#    "scrapy.extensions.telnet.TelnetConsole": None,
#}

# Configure item pipelines
# See https://docs.scrapy.org/en/latest/topics/item-pipeline.html
#ITEM_PIPELINES = {
#    "venue_scraper.pipelines.VenueScraperPipeline": 300,
#}

# Enable and configure the AutoThrottle extension (disabled by default)
# See https://docs.scrapy.org/en/latest/topics/autothrottle.html
#AUTOTHROTTLE_ENABLED = True
# The initial download delay
#AUTOTHROTTLE_START_DELAY = 5
# The maximum download delay to be set in case of high latencies
#AUTOTHROTTLE_MAX_DELAY = 60
# The average number of requests Scrapy should be sending in parallel to
# each remote server
#AUTOTHROTTLE_TARGET_CONCURRENCY = 1.0
# Enable showing throttling stats for every response received:
#AUTOTHROTTLE_DEBUG = False

# Enable and configure HTTP caching (disabled by default)
# See https://docs.scrapy.org/en/latest/topics/downloader-middleware.html#httpcache-middleware-settings
#HTTPCACHE_ENABLED = True
#HTTPCACHE_EXPIRATION_SECS = 0
#HTTPCACHE_DIR = "httpcache"
#HTTPCACHE_IGNORE_HTTP_CODES = []
#HTTPCACHE_STORAGE = "scrapy.extensions.httpcache.FilesystemCacheStorage"

# Set settings whose default value is deprecated to a future-proof value
FEED_EXPORT_ENCODING = "utf-8"
"""