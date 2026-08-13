import re
from collections import defaultdict
from urllib.parse import urljoin, urlparse, urldefrag

import scrapy
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

# ─────────────────────────────────────────────────────────────────────────────
# HOW THIS SPIDER WORKS (high level)
#
# This is a Scrapy spider that uses Playwright (a real browser) to visit venue
# websites and hunt for promotional offers like "Happy Hour" or "Half Off".
#
# The core flow per page:
#   1. Open the URL in a real Chromium browser (via Playwright)
#   2. Dismiss any cookie banners so they don't block the content
#   3. Fill in a location search box if one appears (targets LA venues)
#   4. Scan every heading (h1-h6) on the page for offer keywords
#   5. For each matching heading, walk UP the DOM tree to find the best
#      containing block — one that adds description text around the heading
#   6. Score and rank those containers, keep the best one per heading
#   7. Deduplicate results and yield them as structured records
# ─────────────────────────────────────────────────────────────────────────────

class VenueScraperSpider(scrapy.Spider):
    # Scrapy uses `name` to identify this spider when you run:
    #   scrapy crawl venue_scraper
    name = "venue_scraper"

    custom_settings = {
        # Tell Scrapy to use asyncio under the hood, required for Playwright
        "TWISTED_REACTOR": "twisted.internet.asyncioreactor.AsyncioSelectorReactor",

        # Route all HTTP/HTTPS requests through the Playwright browser
        # instead of Scrapy's normal HTTP downloader
        "DOWNLOAD_HANDLERS": {
            "http": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
            "https": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
        },

        # Keep the browser visible while debugging.
        # Set headless: True in production so no browser window opens.
        # slow_mo: 250 adds a 250ms delay between browser actions — useful
        # for watching what the browser is doing step by step.
        "PLAYWRIGHT_LAUNCH_OPTIONS": {
            "headless": False,
            "slow_mo": 250,
        },

        # This replaces browser.new_context(...)
        # A "context" in Playwright is like a browser profile — it sets
        # the viewport size, language, and fake GPS location.
        # "la_context" is a custom name; it spoofs an LA-based user.
        "PLAYWRIGHT_CONTEXTS": {
            "la_context": {
                "viewport": {
                    "width": 820,
                    "height": 780,
                },
                "locale": "en-US",
                # Spoof GPS coordinates for Los Angeles so that venue sites
                # that ask "what's your location?" get the right city
                "geolocation": {
                    "latitude": 34.0522,
                    "longitude": -118.2437,
                },
                "permissions": ["geolocation"],
            }
        },

        # "PLAYWRIGHT_MAX_PAGES_PER_CONTEXT": 2,
        "HTTPCACHE_ENABLED": False,   # Don't cache pages — always fetch fresh
        "COOKIES_ENABLED": True,      # Allow cookies (needed for session-based sites)
        "LOG_LEVEL": "INFO",
        "ITEM_PIPELINES": {},         # No item pipelines active right now
    }

    # ── Offer detection patterns ──────────────────────────────────────────────
    # These regex patterns are what the spider actually searches for in headings.
    # Only "happy_hour" and "half_off" are active — more can be added here.
    # re.I = case-insensitive, so "Happy Hour", "HAPPY HOUR", etc. all match.
    offer_patterns = {
        "happy_hour": re.compile(r"\bhappy\s*hour\b", re.I),
        "half_off": re.compile(
            r"\b(?:half[\s-]*off|1\s*/\s*2\s*off|50\s*%\s*off)\b",
            re.I,
        ),
    }

    # ── Link scoring weights (not yet used in this version) ───────────────────
    # When the spider eventually crawls linked pages (depth > 0), these weights
    # determine which internal links are worth following. Higher = more likely
    # to contain offer content. e.g. a link labeled "happy hour" scores 100,
    # a link labeled "food" only scores 15.
    link_term_weights = {
        "happy hour": 100,
        "half off": 100,
        "specials": 75,
        "promotions": 70,
        "offers": 70,
        "deals": 65,
        "menu": 50,
        "brunch": 40,
        "food": 15,
        "drink": 15,
    }

    # Links containing any of these terms will be skipped entirely —
    # they're noise pages (account pages, legal, etc.)
    excluded_link_terms = {
        "gift card",
        "gift-card",
        "rewards",
        "loyalty",
        "account",
        "login",
        "sign in",
        "sign-in",
        "careers",
        "privacy",
        "accessibility",
        "nutrition",
        "contact us",
    }

    # How deep the crawler is allowed to follow links from the starting page.
    # depth=0 = only the start URL; depth=2 = start + 2 levels of linked pages
    max_depth = 2
    # Cap how many links to follow per page to avoid crawling the entire site
    max_followed_links_per_page = 5
    # Minimum score a link must have (from link_term_weights) to be followed
    min_link_score = 40

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # 10 real venue sites, pulled from venues the model pipeline already
        # categorized as "Happy Hour" — good odds of matching this spider's
        # offer_patterns.
        self.start_urls = [
            "http://www.gaslamp.org/",
            "https://www.thegeezer.com/",
            "https://www.georgesatthecove.com/",
            "https://www.bigbearmountainresort.com/things-to-do/dining",
            "https://gloriascocinamx.com/",
            "https://www.goathilltavern.com/",
            "http://goldcountrylanes.com/",
            "http://www.goldenacorncasino.com/",
            "http://goosetown-lounge.edan.io/",
            "https://grandolebbq.com/",
        ]

    async def start(self):
        # Entry point — Scrapy calls this to generate the first request(s).
        # `yield` sends the request into Scrapy's queue; Scrapy calls
        # parse_page() when each page loads.
        for url in self.start_urls:
            yield self.make_playwright_request(
                url=url,
                depth=0,          # depth=0 means this is a seed/starting page
                source_url=None,  # No referrer for seed pages
                discovery_reason=["seed"],
            )

    def make_playwright_request(self, url, depth, source_url, discovery_reason):
        # Builds a Scrapy Request object wired to open in a Playwright browser.
        # The `meta` dict is how Scrapy passes extra data alongside the request.
        return scrapy.Request(
            url=url,
            callback=self.parse_page,          # Called when page loads successfully
            errback=self.errback_close_page,   # Called if the page fails to load
            meta={
                    "playwright" : True,                  # Use Playwright for this request
                    "playwright_include_page" : True,     # Give us the raw page object in parse_page
                    "playwright_context" : "la_context",  # Use the LA browser context defined above
                    "playwright_page_goto_kwargs" : {
                        "wait_until" : "domcontentloaded", # Don't wait for all images/JS — just the HTML
                        "timeout" : 6000,                  # Give up if page doesn't load in 6 seconds
                    },
                    "dont_cache": True,           # Always fetch fresh, ignore any cache
                    "download_timeout": 90,       # Total timeout including JS execution
                    "crawl_depth": depth,         # Track how deep we are in the crawl
                    "source_url": source_url,     # Which page linked to this one
                    "discovery_reason": discovery_reason,  # Why we're visiting (e.g. "seed", "link")
                },
        )

    async def parse_page(self, response):
        # This is the main callback — it runs once per loaded page.
        # `response` is Scrapy's response object; we also get the live
        # Playwright page object from response.meta.
        page = response.meta["playwright_page"]

        if page is None:
            self.logger.error("No Playwright page attached. url=%s", response.url)
            return

        # For Debugging: collect any API calls the page makes in the background.
        # Useful for finding if the site fetches offer data from a separate API endpoint.
        api_responses = []

        # Register a listener that fires every time the browser receives a response.
        # We only care about /api/ URLs — those are backend data calls.
        def capture_response(playwright_response):
            url = playwright_response.url

            if "/api/" in url:
                api_responses.append(
                    {
                        "url": url,
                        "status": playwright_response.status,
                    }
                )

        page.on("response", capture_response)

        depth = response.meta.get("crawl_depth",0)

        try:
            self.logger.info("Opened page: %s", response.url)
            self.logger.info("Initial Scrapy status: %s", response.status)

            # Small pause to let the page settle before we interact with it
            await page.wait_for_timeout(750)

            # Step 1: Dismiss cookie consent banners so they don't block content
            await self.handle_cookie_banner(page)
            # Step 2: Fill in location if the site asks (e.g. chain restaurants
            #         that show a "find your nearest location" dialog)
            await self.handle_location(page)

            # Wait for any location-triggered reloads or redirects to settle
            await page.wait_for_timeout(1000)

            # page.url may differ from response.url if the site redirected
            final_url = page.url
            title = await page.title()

            self.logger.info(
                "Extracting page depth=%d url=%s",
                depth,
                final_url,
            )

            # Core extraction: find all offer-related content blocks on the page
            candidates = await self.extract_offer_candidates(page)

            # Yield each candidate as a Scrapy item (dict) — Scrapy will
            # pass these to the pipeline and ultimately write them to JSON output
            for candidate in candidates:
                yield {
                    "record_type": "offer_candidate",
                    # "venue": self.identify_venue(final_url),
                    "page_url": final_url,
                    "requested_url": response.url,
                    "source_url": response.meta.get("source_url"),
                    "page_title": title,
                    "crawl_depth": depth,
                    "discovery_reason":
                        response.meta.get("discovery_reason", []),
                    **candidate,   # Spread all fields from the candidate dict in
                }

        finally:
            # Always close the browser tab, even if something threw an error.
            # Without this, tabs accumulate and memory usage grows unbounded.
            await page.close()

    async def handle_cookie_banner(self, page):
        # Many venue sites show a GDPR/cookie consent popup on first load.
        # This tries to click the "Accept" button using common button labels.
        # If none match, it logs a message and moves on — not a fatal error.
        cookie_patterns = (
            re.compile(r"accept(?: all)?", re.I),
            re.compile(r"allow all", re.I),
            re.compile(r"agree", re.I),
            re.compile("Accept", re.I),
        )

        try:
            for pattern in cookie_patterns:
                clicked = await self.safe_click(
                    page.get_by_role("button", name=pattern).first,
                    timeout=1200,
                    label=f"cookie button: {pattern.pattern}",
                )

                if clicked:
                    break  # Stop trying once we successfully clicked one
            else:
                # The `else` on a for loop runs only if we never `break` —
                # meaning no cookie button was found or clicked
                raise LookupError("No cookie banner matched.")
            return True

        except LookupError as exc:
            self.logger.info("%s", exc)
            return False

    async def handle_location(self, page):
        # Some chain restaurant sites (like Yard House, Lazy Dog) show a
        # "search for your location" dialog before showing local menu/offers.
        # This fills in "Los Angeles, CA", picks the first suggestion, then
        # clicks SELECT to confirm.
        try:
            # Look for any input whose placeholder contains "Search"
            search_box = page.get_by_placeholder(
                re.compile("Search", re.I)
            ).first

            await page.wait_for_timeout(250)

            await search_box.fill("Los Angeles, CA")
            await page.wait_for_timeout(250)
            # Press ArrowDown to highlight the first autocomplete suggestion
            await search_box.press("ArrowDown")
            await search_box.press("Enter")
            await page.wait_for_timeout(250)
            select_button = page.get_by_role(
                "button",
                name=re.compile("SELECT", re.I)
            ).first
            await select_button.wait_for(timeout=1000)
            await select_button.click(timeout=1000)

            self.logger.info("Location selected successfully")
            return True

        except PlaywrightTimeoutError:
            # No location dialog appeared — that's fine, just continue
            self.logger.info("Input location interaction was unavailable.")
            return False

        except Exception:
            self.logger.exception("Unexpected error while location selecting.")
            return False

    async def safe_click(self, locator, timeout=3000, label="element"):
        # A helper that attempts a click and swallows the timeout error if
        # the element isn't found. Returns True if clicked, False if not found.
        # This prevents cookie/location handling from crashing the whole spider.
        try:
            await locator.click(timeout=timeout)
            self.logger.info("Clicked %s.", label)
            return True
        except PlaywrightTimeoutError:
            self.logger.info("Did not find %s. Continuing.", label)
            return False

    async def extract_offer_candidates(self, page):
        """
        Find promotional headings, then select the smallest useful ancestor
        containing both the heading and its supporting descriptive text.

        Strategy:
          - Search for headings (h1-h6) that match offer keywords (e.g. "happy hour")
          - For each match, run a JavaScript snippet IN the browser that walks
            UP the DOM tree (heading → parent → grandparent → ...) to find the
            best containing block
          - Score each ancestor based on how much descriptive text it adds,
            what HTML tag it is, and how far up the tree it is
          - Return only the highest-scoring block per heading
        """
        results = []

        for keyword_name, pattern in self.offer_patterns.items():
            # Locate all heading elements whose visible text matches the pattern.
            # This is smarter than searching all elements — headings signal
            # intentional section labels, not just passing mentions in body text.
            matches = page.locator(
                "h1, h2, h3, h4, h5, h6"
            ).filter(
                has_text=pattern
            )

            count = await matches.count()

            self.logger.info("Found %d heading matches for keyword=%s", count, keyword_name)

            # Cap at 50 matches per keyword to avoid runaway loops on noisy pages
            for index in range(min(count, 50)):
                heading = matches.nth(index)

                try:
                    # `evaluate()` runs a JavaScript function directly inside
                    # the browser, with the heading DOM element passed in.
                    # The JS walks up the DOM and returns the best ancestor block.
                    candidate = await heading.evaluate(
                        """
                        heading => {
                            // Normalize whitespace: collapse multiple spaces/newlines,
                            // replace non-breaking spaces ( ) with regular spaces
                            const normalize = value =>
                                (value || "")
                                    .replace(/\\u00a0/g, " ")
                                    .replace(/\\s+/g, " ")
                                    .trim();

                            // Count words in a string after normalizing it
                            const wordCount = value => {
                                const normalized = normalize(value);

                                if (!normalized) {
                                    return 0;
                                }

                                return normalized
                                    .split(/\\s+/)
                                    .filter(Boolean)
                                    .length;
                            };

                            const headingText = normalize(heading.innerText);
                            const headingWords = wordCount(headingText);

                            const candidates = [];  // Will hold all ancestor blocks we examine

                            let current = heading;

                            // Walk up the DOM tree up to 7 levels above the heading.
                            // level=0 is the heading itself; level=6 is 6 parents up.
                            for (
                                let level = 0;
                                current && level < 7;
                                level += 1
                            ) {
                                const text = normalize(current.innerText);
                                const words = wordCount(text);
                                const tag = current.tagName;

                                // Skip nodes that are empty or unreasonably large
                                // (>180 words = probably a whole page section, too noisy)
                                if (!text || words === 0 || words > 180) {
                                    current = current.parentElement;
                                    continue;
                                }

                                /*
                                * Supporting text means that this ancestor adds
                                * useful text beyond the heading itself.
                                * e.g. heading = "Happy Hour" (2 words),
                                * ancestor = "Happy Hour Mon-Fri 3-6pm $5 wells" (8 words)
                                * → addedWords = 6, hasSupportingText = true
                                */
                                const addedWords = words - headingWords;
                                const hasSupportingText = addedWords >= 3;

                                /*
                                * Count how many heading and paragraph/span elements
                                * are nested inside this ancestor.
                                * We use these counts in scoring below.
                                */
                                const headingCount = current.querySelectorAll(
                                    "h1, h2, h3, h4, h5, h6"
                                ).length;

                                const descriptionCount =
                                    current.querySelectorAll(
                                        "p, span"
                                    ).length;

                                // ── Scoring ─────────────────────────────────
                                // Higher score = better candidate block.
                                let score = 0;

                                // +50 if this ancestor adds descriptive text beyond the heading
                                if (hasSupportingText) {
                                    score += 50;
                                }

                                // +25 for semantic content containers (not layout or nav elements)
                                if (
                                    tag === "DIV" ||
                                    tag === "SECTION" ||
                                    tag === "ARTICLE"
                                ) {
                                    score += 25;
                                }

                                // +25 if this block looks like a "card" (has a heading + body text)
                                if (
                                    headingCount >= 1 &&
                                    descriptionCount >= 1
                                ) {
                                    score += 25;
                                }

                                // Penalize ancestors that are farther up the tree —
                                // we want the smallest block that still has useful content
                                score -= level * 3;
                                // Penalize very long blocks — they're probably page-level wrappers
                                score -= Math.max(0, words - 40) * 0.5;

                                // Penalize interactive/navigational elements —
                                // their text describes UI structure, not offer content
                                if (tag === "BUTTON") {
                                    score -= 30;
                                }

                                if (tag === "LI") {
                                    score -= 25;
                                }

                                if (
                                    tag === "UL" ||
                                    tag === "OL" ||
                                    tag === "NAV"
                                ) {
                                    score -= 50;
                                }

                                // Add this ancestor to our candidates list with its score
                                candidates.push({
                                    text,
                                    words,
                                    added_words: addedWords,
                                    tag,
                                    class_name:
                                        typeof current.className === "string" ? current.className
                                            : "",
                                    dom_level: level,
                                    score,
                                    has_supporting_text: hasSupportingText,
                                    heading_count: headingCount,
                                    description_count: descriptionCount
                                });

                                current = current.parentElement;  // Move one level up
                            }

                            // Filter to only ancestors that add useful text,
                            // then sort by score descending and return the best one
                            const useful = candidates.filter(
                                candidate =>
                                    candidate.has_supporting_text
                            );

                            useful.sort(
                                (a, b) => b.score - a.score
                            );

                            return useful.length > 0 ? useful[0] : null;
                        }
                        """
                    )

                except Exception as exc:
                    self.logger.warning("Candidate evaluation failed: %s", exc)
                    continue

                if not candidate:
                    continue

                text = self.clean_text(candidate["text"])

                if not text:
                    continue

                # Build the output record for this candidate block
                results.append({
                    "matched_keyword": keyword_name,        # Which pattern triggered this (e.g. "happy_hour")
                    "raw_text": text,                       # The full visible text of the block
                    "word_count": candidate["words"],       # Total words in the block
                    "added_word_count": candidate["added_words"],  # Words beyond the heading itself
                    "tag": candidate["tag"],                # HTML tag of the block (DIV, SECTION, etc.)
                    "class_name": candidate["class_name"],  # CSS class — useful for debugging
                    "dom_level": candidate["dom_level"],    # How many levels above the heading
                    "candidate_score": candidate["score"],  # The score used to rank this block
                    "heading_count": candidate["heading_count"],
                    "description_count": candidate["description_count"],
                    "extraction_method": "heading_context_container",
                })

        return self.deduplicate_candidates(results)

    def deduplicate_candidates(self, candidates):
        """
        Two-pass deduplication to avoid returning the same offer content twice.

        Pass 1 — Exact dedup: if two candidates have the same keyword and the
        same normalized text, keep only the one with fewer words (more focused).

        Pass 2 — Subset dedup: if candidate B is more than 2x longer than
        candidate A and A's text is fully contained within B's text, drop B.
        It's just a noisier version of A.
        """
        # Pass 1: exact dedup keyed on (keyword, normalized_text)
        exact = {}

        for candidate in candidates:
            normalized = self.normalize_for_comparison(candidate["raw_text"])

            key = (
                candidate["matched_keyword"],
                normalized,
            )

            previous = exact.get(key)

            # Keep the shorter (more focused) version if there's a duplicate
            if (previous is None or candidate["word_count"] < previous["word_count"]):
                exact[key] = candidate

        # Sort by word count ascending so shorter (more precise) blocks come first
        ordered = sorted(
            exact.values(),
            key=lambda row: row["word_count"],
        )

        # Pass 2: subset dedup — drop any candidate whose text is already
        # covered by a shorter, already-retained candidate
        retained = []

        for candidate in ordered:
            candidate_text = self.normalize_for_comparison(candidate["raw_text"])

            redundant = False

            for existing in retained:
                existing_text = self.normalize_for_comparison(existing["raw_text"])

                # If existing text is a substring of this candidate AND
                # this candidate is more than 2x longer → it's just a bigger
                # wrapper around content we already have; drop it
                if (existing["matched_keyword"] == candidate["matched_keyword"]
                    and existing_text in candidate_text
                    and candidate["word_count"] > existing["word_count"] * 2):
                    redundant = True
                    break

            if not redundant:
                retained.append(candidate)

        return retained

    def clean_text(self, text):
        # Replace non-breaking spaces and collapse all whitespace to single spaces.
        # This is applied to every piece of text before it's stored.
        if not text:
            return ""
        text = text.replace("\xa0", " ")          # \xa0 = non-breaking space (common in HTML)
        text = re.sub(r"\s+", " ", text)           # Collapse tabs, newlines, multiple spaces
        return text.strip()

    def normalize_for_comparison(self, text):
        # A stricter version of clean_text used only for comparing/deduplicating.
        # Lowercases everything and strips punctuation (except price/url chars)
        # so "Happy Hour!" and "happy hour" are treated as the same.
        text = self.clean_text(text).lower()
        text = re.sub(r"[^\w$%:/.-]+", " ", text)  # Keep word chars + $, %, :, /, ., -
        return re.sub(r"\s+", " ", text).strip()

    async def errback_close_page(self, failure):
        # Called by Scrapy if a request fails (network error, timeout, etc.)
        # We still need to close the Playwright page to free browser resources.
        page = failure.request.meta.get("playwright_page")
        if page is not None and not page.is_closed():
            await page.close()