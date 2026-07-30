import re
from collections import defaultdict
from urllib.parse import urljoin, urlparse, urldefrag

import scrapy
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

class VenueScraperSpider(scrapy.Spider):
    name = "venue_scraper"

    custom_settings = {
        # Scrapy-Playwright Custom Settings:
        "TWISTED_REACTOR": "twisted.internet.asyncioreactor.AsyncioSelectorReactor",

        "DOWNLOAD_HANDLERS": {
            "http": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
            "https": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
        },

        # Keep the browser visible while debugging.
        "PLAYWRIGHT_LAUNCH_OPTIONS": {
            "headless": False,
            "slow_mo": 250,
        },

        # This replaces browser.new_context(...)
        "PLAYWRIGHT_CONTEXTS": {
            "la_context": {
                "viewport": {
                    "width": 820,
                    "height": 780,
                },
                "locale": "en-US",
                "geolocation": {
                    "latitude": 34.0522,
                    "longitude": -118.2437,
                },
                "permissions": ["geolocation"],
            }
        },

        # "PLAYWRIGHT_MAX_PAGES_PER_CONTEXT": 2,
        "HTTPCACHE_ENABLED": False,
        "COOKIES_ENABLED": True,
        "LOG_LEVEL": "INFO",
        "ITEM_PIPELINES": {},
    }

    offer_patterns = {
        "happy_hour": re.compile(r"\bhappy\s*hour\b", re.I),
        "half_off": re.compile(
            r"\b(?:half[\s-]*off|1\s*/\s*2\s*off|50\s*%\s*off)\b",
            re.I,
        ),
    }

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

    max_depth = 2
    max_followed_links_per_page = 5
    min_link_score = 40

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Start at the homepage for testing
        # Start with 1 URL link
        # self.start_url = "https://www.yardhouse.com/happy-hour"
        # self.start_url = "https://m.yardhouse.com/happy-hour"
        self.start_url = "https://orders.lazydogrestaurants.com/menu?_gl=1*15zth8s*_gcl_au*MTAxNDc5NDA4NC4xNzgxNTQxNzk5"

    async def start(self):
        yield self.make_playwright_request(
            url=self.start_url,
            depth=0,
            source_url=None,
            discovery_reason=["seed"],
        )
        """
        Uncomment later for multiply links:
        for url in self.start_urls:
            yield scrapy.make_playwright_request(
                url=url,
                depth=0,
                source_url=None,
                discovery_reason=["seed"], 
            )
        """
    def make_playwright_request(self, url, depth, source_url, discovery_reason):
        return scrapy.Request(
            url=url, 
            callback=self.parse_page,
            errback=self.errback_close_page,
            meta={
                    "playwright" : True,
                    "playwright_include_page" : True,
                    "playwright_context" : "la_context",
                    "playwright_page_goto_kwargs" : {
                        "wait_until" : "domcontentloaded",
                        "timeout" : 6000,
                    },
                    "dont_cache": True,
                    "download_timeout": 90,
                    "crawl_depth": depth,
                    "source_url": source_url,
                    "discovery_reason": discovery_reason,
                },
        )

    async def parse_page(self, response):
        page = response.meta["playwright_page"]

        if page is None:
            self.logger.error("No Playwright page attached. url=%s", response.url)
            return

        # For Debugging:
        api_responses = []

        # ***Playwright Open URL & Observe Response:***
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
            # Print URL & Page Status
            self.logger.info("Opened page: %s", response.url)
            self.logger.info("Initial Scrapy status: %s", response.status)

            await page.wait_for_timeout(750)

            await self.handle_cookie_banner(page)
            await self.handle_location(page)

            await page.wait_for_timeout(1000)

            final_url = page.url
            title = await page.title()

            self.logger.info(
                "Extracting page depth=%d url=%s",
                depth,
                final_url,
            )

            candidates = await self.extract_offer_candidates(page)

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
                    **candidate,
                }

        finally:
            await page.close()

    async def handle_cookie_banner(self, page):
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
                    break
            else:
                raise LookupError("No cookie banner matched.")
            return True

        except LookupError as exc:
            self.logger.info("%s", exc)
            return False
    
    async def handle_location(self, page):
        # Find a searchbar
        try:
            search_box = page.get_by_placeholder(
                re.compile("Search", re.I)
            ).first

            await page.wait_for_timeout(250)

            await search_box.fill("Los Angeles, CA")
            await page.wait_for_timeout(250)
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
            self.logger.info("Input location interaction was unavailable.")
            return False

        except Exception: 
            self.logger.exception("Unexpected error while location selecting.")
            return False

    async def safe_click(self, locator, timeout=3000, label="element"):
        try:
            await locator.click(timeout=timeout)
            self.logger.info("Clicked %s.", label)
            return True
        except PlaywrightTimeoutError:
            self.logger.info("Did not find %s. Continuing.", label)
            return False
    async def extract_offer_candidates(self, page):
        """
        Extract minimal or near-minimal semantic blocks instead of every
        ancestor div containing a matching descendant.
        """
        results = []

        for keyword_name, pattern in self.offer_patterns.items():
            matches = page.get_by_text(pattern)

            count = await matches.count()

            for index in range(min(count, 50)):
                match = matches.nth(index)

                try:
                    candidate = await match.evaluate("""
                        node => {
                            const preferredTags = new Set([
                                "ARTICLE",
                                "SECTION",
                            ]);

                            const isHeaing = /^H[1-6]$/.test(current.tagName);
                            const isSpan = current.tagName === "SPAN";

                            const maxWords = 180;
                            const minWords = 2;

                            const normalize = value =>
                                (value || "")
                                    .replace(/\\u00a0/g, " ")
                                    .replace(/\\s+/g, " ")
                                    .trim();

                            const wordCount = value =>
                                normalize(value)
                                    .split(/\\s+/)
                                    .filter(Boolean)
                                    .length;

                            let current = node;
                            let best = null;

                            for (let level = 0;
                                 current && level < 7;
                                 level += 1) {

                                const text = normalize(current.innerText);
                                const words = wordCount(text);

                                if (
                                    words >= minWords &&
                                    words <= maxWords
                                ) {
                                    best = {
                                        text,
                                        words,
                                        tag: current.tagName,
                                        class_name:
                                            typeof current.className === "string"
                                                ? current.className
                                                : "",
                                        dom_level: level,
                                        semantic:
                                            preferredTags.has(current.tagName)
                                    };

                                    /*
                                     * Prefer the first useful semantic
                                     * container. Otherwise continue upward
                                     * briefly to collect nearby details.
                                     */
                                    // if (best.semantic && words >= 5 && !isHeading && !isSpan) {
                                    //     break;
                                    // }
                                }

                                current = current.parentElement;
                            }

                            return best;
                        }
                    """)

                except Exception:
                    continue

                if not candidate:
                    continue

                text = self.clean_text(candidate["text"])

                if not text:
                    continue

                results.append({
                    "matched_keyword": keyword_name,
                    "raw_text": text,
                    "word_count": candidate["words"],
                    "tag": candidate["tag"],
                    "class_name": candidate["class_name"],
                    "dom_level": candidate["dom_level"],
                    "extraction_method": "keyword_ancestor_search",
                })

        return self.deduplicate_candidates(results)

     
    """
    async def extract_offer_candidates(self, page):
        results = []

        for keyword_name, pattern in self.offer_patterns.items():
            # Start from headings rather than every element containing the text.
            matches = page.locator(
                "h1, h2, h3, h4, h5, h6"
            ).filter(
                has_text=pattern
            )

            count = await matches.count()

            self.logger.info("Found %d heading matches for keyword=%s", count, keyword_name)

            for index in range(min(count, 50)):
                heading = matches.nth(index)

                try:
                    candidate = await heading.evaluate(
                        heading => {
                            const normalize = value =>
                                (value || "")
                                    .replace(/\\u00a0/g, " ")
                                    .replace(/\\s+/g, " ")
                                    .trim();

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

                            const candidates = [];

                            let current = heading;

                            for (
                                let level = 0;
                                current && level < 7;
                                level += 1
                            ) {
                                const text = normalize(current.innerText);
                                const words = wordCount(text);
                                const tag = current.tagName;

                                if (!text || words === 0 || words > 180) {
                                    current = current.parentElement;
                                    continue;
                                }

                                /*
                                * Supporting text means that this ancestor adds
                                * useful text beyond the heading itself.
                                */
                                const addedWords = words - headingWords;
                                const hasSupportingText = addedWords >= 3;

                                /*
                                * Count descendants that commonly represent
                                * headings or descriptive text.
                                */
                                const headingCount = current.querySelectorAll(
                                    "h1, h2, h3, h4, h5, h6"
                                ).length;

                                const descriptionCount =
                                    current.querySelectorAll(
                                        "p, span"
                                    ).length;

                                let score = 0;

                                /*
                                * We want a container that adds a description.
                                */
                                if (hasSupportingText) {
                                    score += 50;
                                }

                                /*
                                * Prefer common content-container elements.
                                */
                                if (
                                    tag === "DIV" ||
                                    tag === "SECTION" ||
                                    tag === "ARTICLE"
                                ) {
                                    score += 25;
                                }

                                /*
                                * A heading plus nearby text is a strong sign
                                * that this is the intended content card.
                                */
                                if (
                                    headingCount >= 1 &&
                                    descriptionCount >= 1
                                ) {
                                    score += 25;
                                }

                                /*
                                * Prefer smaller, more local containers.
                                */
                                score -= level * 3;
                                score -= Math.max(0, words - 40) * 0.5;

                                /*
                                * Penalize interactive and navigational wrappers.
                                * Their text may be correct, but they usually
                                * describe UI structure rather than the offer.
                                */
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

                                current = current.parentElement;
                            }

                            /*
                            * Only consider nodes that include useful supporting
                            * text. Sort by score and return the best one.
                            */
                            const useful = candidates.filter(
                                candidate =>
                                    candidate.has_supporting_text
                            );

                            useful.sort(
                                (a, b) => b.score - a.score
                            );

                            return useful.length > 0 ? useful[0] : null;
                        }
                    )

                except Exception as exc:
                    self.logger.warning("Candidate evaluation failed: %s", exc)
                    continue

                if not candidate:
                    continue

                text = self.clean_text(candidate["text"])

                if not text:
                    continue

                results.append({
                    "matched_keyword": keyword_name,
                    "raw_text": text,
                    "word_count": candidate["words"],
                    "added_word_count": candidate["added_words"],
                    "tag": candidate["tag"],
                    "class_name": candidate["class_name"],
                    "dom_level": candidate["dom_level"],
                    "candidate_score": candidate["score"],
                    "heading_count": candidate["heading_count"],
                    "description_count":
                        candidate["description_count"],
                    "extraction_method":
                        "heading_context_container",
                })

        return self.deduplicate_candidates(results)
    """

    def deduplicate_candidates(self, candidates):
        """
        First remove exact duplicates, then remove larger blocks that add
        little information beyond an already-retained smaller block.
        """
        exact = {}

        for candidate in candidates:
            normalized = self.normalize_for_comparison(candidate["raw_text"])

            key = (
                candidate["matched_keyword"],
                normalized,
            )

            previous = exact.get(key)

            if (previous is None or candidate["word_count"] < previous["word_count"]):
                exact[key] = candidate

        ordered = sorted(
            exact.values(),
            key=lambda row: row["word_count"],
        )

        retained = []

        for candidate in ordered:
            candidate_text = self.normalize_for_comparison(candidate["raw_text"])

            redundant = False

            for existing in retained:
                existing_text = self.normalize_for_comparison(existing["raw_text"])

                if (existing["matched_keyword"] == candidate["matched_keyword"]
                    and existing_text in candidate_text
                    and candidate["word_count"] > existing["word_count"] * 2):
                    redundant = True
                    break

            if not redundant:
                retained.append(candidate)

        return retained    

    def clean_text(self, text):
        if not text:
            return ""
        text = text.replace("\xa0", " ")
        text = re.sub(r"\s+", " ", text)
        return text.strip()
    
    def normalize_for_comparison(self, text):
        text = self.clean_text(text).lower()
        text = re.sub(r"[^\w$%:/.-]+", " ", text)
        return re.sub(r"\s+", " ", text).strip()

    async def errback_close_page(self, failure):
        page = failure.request.meta.get("playwright_page")
        if page is not None and not page.is_closed():
            await page.close()