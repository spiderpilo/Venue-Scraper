import csv
import re
from urllib.parse import urlparse

import os
import random
import scrapy
from scrapy.linkextractors import LinkExtractor

class VenueScraperSpider(scrapy.Spider):
    name = "venue_scraper"

    custom_settings = {
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

        # Write on CSV File without -O output.csv
        "FEEDS" : {
            'output_file.csv' : {
                'format' : 'csv',
                'encoding' : 'utf8',
            }
        },

        # Write one clean JSON file without needing -O output.json.
        # "FEEDS": {
        #     "output.json": {
        #         "format": "json",
        #         "overwrite": True,
        #         "indent": 2,
        #         "encoding": "utf-8",
        #     }
        # },

        "LOG_LEVEL": "INFO",
        "COOKIES_ENABLED": True,
        "ITEM_PIPELINES": {},
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.start_url = [
            # "https://www.novaoc.com/",
            # "https://lazydogrestaurants.com/",
            "https://m.yardhouse.com/happy-hour",

        ]

    async def start(self):
        for url in self.start_url:
            yield scrapy.Request(
                url=url,
                callback=self.parse,
                meta={
                    "playwright" : True,
                    "playwright_include_page" : True,
                    "playwright_context" : "la_context",
                    "playwright_page_goto_kwargs" : {
                        "wait_until" : "domcontentloaded",
                        "timeout" : 6000,
                    },
                }
            )

    async def parse(self, response):
        page = response.meta["playwright_page"]

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

        try:
            self.logger.info("Opened page: %s", response.url)
            self.logger.info("Initial Scrapy status: %s", response.status)

            # Give the cookie modal and app shell time to appear.
            await page.wait_for_timeout(1000)

            await self.safe_click(
                page.get_by_role("button", name=re.compile("Accept", re.I)),
                timeout=1000,
                label="cookie accept button",
            )

            await self.safe_search_bar(
                search_box=page.get_by_placeholder(re.compile("Search", re.I)).first,
                timeout=1000,
                search_location="Los Angeles, CA",
                get_page=page
            )

            # This matters. Your sync script waits 8000 ms here.
            # Your spider was effectively waiting 0 ms because it was missing await.
            await page.wait_for_timeout(1000)

            # Get Body Text from URL:
            body_text = await page.locator("body").inner_text(timeout=1000)
            body_text = self.clean_text(body_text)

            # local_storage = await page.evaluate(
            #     () => Object.fromEntries(Object.entries(window.localStorage))
            # )

            # cookies = await page.context.cookies()

            #! === Objective: ===
            #! Figure out how to get the text & the div 
            #! Figure out how to get the parents and/or children from divs

            #! Figure Out How to Use: 'div:has-text()' & 'xpath=..'

            #^  target_text_locator = page.locator("div:has-text('Half Off')")
            # parent_locator = target_text_locator.locator("xpath=..")

            #! Sketch Implementation: 
            # s_text = await parent_locator.all_inner_texts()
            # child_locator = target_text_locator.locator("xpath=./child::")
            #! Better:
            #^ s_text = await target_text_locator.all_inner_texts()
            #^ await page.wait_for_timeout(1000)
            #^ # s_text_class = await target_text_locator.get_attribute("class")
            #^ s_text_class = await target_text_locator.evaluate_all(
            #^     "elements => elements.map(el => el.className)"
            #^ )
            #^ await page.wait_for_timeout(1000)

            #! Consider: 
            #! Extra Note: These two give the same errors, because there are 
            #! a lot of elements that exist...
            # NOTE:
            # Alternatives:
            # .all_inner_texts()
            # .evaluate_all(func), where func = JavaScript expression 
            # parent_options = await parent_locator.inner_text()
            # s_text_class = await target_text_locator.get_attribute("class")

            self.logger.info("==================================BEGIN==================================")
            self.logger.info("Final URL: %s", page.url)

            """
            #& Print out Attributes of Searched Text (Match to Keyword(s)):
            self.logger.info("Searched Length: %d", len(s_text))
            for num, in_text in enumerate(s_text):
                self.logger.info(f"Searched Text[{num}]: {in_text}")

            #& Print out Attributes of Searched Text's Classes:
            self.logger.info("Searched Class Length: %d", len(s_text_class))
            self.logger.info("Searched Class: %s", s_text_class)

            result = dict(zip(s_text, s_text_class))
            self.logger.info(f">>>Dictionary<<<\n:")
            for key, val in result.items():
                self.logger.info(f"Searched Text[{key or "None"}]: {val or "None"}")
            """
            # yield result

            self.logger.info("===============Method 1================")
            keyword = "Half Off"
            method_1 = await page.locator(f"div:has-text('{keyword}')").all_inner_texts()
            candidates = [
                t for t in method_1 
                if 20 < len(t.split()) <= 120
            ]
            self.logger.info(f"Candidates: {candidates}")

            # self.logger.info("===============Method 2================")
            # method_2 = page.locator("xpath=//div[contains(., 'Half Off')]")
            # texts = await method_2.all_inner_texts()
            # classes = await method_2.get_attribute("class")
            # self.logger.info(f"Find all divs with Half Off: {texts}, {classes}") # NOTE: Example shows texts[:2]
            # parent_text = await method_2.locator("xpath=ancestor::div[1]").inner_text()
            # self.logger.info(f"Parent Text: {parent_text}")

            self.logger.info("===============Method 3================")
            method_3 = page.locator("text=Half Off").first
            for n in range(1, 4):
                txt = await method_3.locator(f"xpath=ancestor::div[{n}]").inner_text()
                self.logger.info(f"XPath Parent Climb: {n}, {len(txt.split())}, {txt[:80]}")

            self.logger.info("===============Method 4================")
            method_4 = await page.locator("div:has-text('Half Off')").evaluate_all("""
                els => els.map(el => ({
                    text: el.innerText.slice(0, 120),
                    classNamew: el.className
                }))
            """)
            self.logger.info(f"JS + Text Together {method_4[:2]}")

            self.logger.info("===============Method 5================")


from keyword_bank import (
    INCENTIVE_KEYWORDS,
    LINK_KEYWORDS,
    NOISE_PHRASES,
    MENU_FOOD_WORDS
)

PATH = "data/src/golden_model.csv"

class VenueSpider(scrapy.Spider):
    name = "venues"
    # Scrape:
    #   NOVA Kitchen & Bar
    #   Lazy Dog Restaurant & Bar
    #   Rancho Capistrano Winery
    # allowed_domains = ["https://www.novaoc.com/", "https://lazydogrestaurants.com/", "https://www.ranchocapwinery.com/"]
    # start_urls = ["https://www.novaoc.com/", "https://lazydogrestaurants.com/", "https://www.ranchocapwinery.com/"]
    start_urls = ["https://www.novaoc.com/"]

    def parse_homepage(self, response):
        homepage_chunks = self.extract_candidate_chunks(response)
        pass

    def extract_candidate_chunks(self, response):
        chunks = []

        selectors = response.css(
            "h1, h2, h3, h4, p, li, article, section, div"
        )

        for idx, selector in enumerate(selectors):
            text = " ".join(selector.css("::text").getall())
            text = self.clean_text(text)

    def clean_text(self, text):
        text = text or ""
        text = re.sub(r"\s+", " ", text)
        return text.strip()

"""
    def __init__(self, csv_path=PATH, limit=10, random_seed=42, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.csv_path = csv_path
        self.limit = int(limit)
        self.random_seed = int(random_seed)
        self.records_by_url = {}
"""
"""
    async def start(self):
        records = self.load_golden_records(self.csv_path, self.limit)

        for record in records:
            url = record["Source URL"].strip()
            self.records_by_url[url] = record

            yield scrapy.Request(
                url=url,
                callback=self.parse_homepage,
                errback=self.errback_venue,
                meta={
                    "gold_record": record,
                    "base_url": url,
                    "stage": "homepage",
                    "candidate_chunks": [],
                    "visited_count": 0,
                },
                dont_filter=True,
            )
"""
"""
    def load_golden_records(self, csv_path, limit):
        self.logger.info("Current working directory: %s", os.getcwd())
        self.logger.info("CSV path argument: %s", csv_path)
        self.logger.info("CSV exists: %s", os.path.exists(csv_path))

        required = [
            "venue_name",
            "Source URL",
            "Business Type",
            # "Experience Category",
            "Incentive Category",
            "Incentive Teaser",
            "Full Incentive Description",
        ]

        candidates = []
        seen_urls = set()

        with open(csv_path, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            self.logger.info("CSV columns: %s", reader.fieldnames)

            total_rows = 0
            missing_required = 0
            bad_url = 0
            duplicate_url = 0

            for row in reader:
                total_rows += 1

                if not all((row.get(col) or "").strip() for col in required):
                    missing_required += 1
                    continue

                url = row["Source URL"].strip()

                if not url.startswith("http") or re.search(r"\s", url):
                    bad_url += 1
                    continue

                if url in seen_urls:
                    duplicate_url += 1
                    continue

                seen_urls.add(url)
                candidates.append(row)

        rng = random.Random(getattr(self, "random_seed", 42))
        rng.shuffle(candidates)
        output = candidates[:limit]

        self.logger.info("Total CSV rows seen: %d", total_rows)
        self.logger.info("Rows skipped missing required fields: %d", missing_required)
        self.logger.info("Rows skipped bad URL: %d", bad_url)
        self.logger.info("Rows skipped duplicate URL: %d", duplicate_url)
        self.logger.info("Candidate rows after cleaning: %d", len(candidates))
        self.logger.info("Rows selected for scraping: %d", len(output))

        for r in output:
            self.logger.info("Selected venue: %s | %s", r.get("venue_name"), r.get("Source URL"))

        return output
"""
"""
    def parse_homepage(self, response):
        gold = response.meta["gold_record"]
        base_url = response.meta["base_url"]

        homepage_chunks = self.extract_candidate_chunks(response)
        candidate_chunks = list(homepage_chunks)

        # Always yield the homepage result first so every input URL produces a row.
        yield self.build_item(
            response=response,
            gold=gold,
            candidate_chunks=candidate_chunks,
            scrape_stage="homepage_debug",
        )

        likely_links = self.extract_likely_internal_links(response, base_url)
        likely_links = likely_links[:4]

        for link in likely_links:
            yield scrapy.Request(
                url=link,
                callback=self.parse_candidate_page,
                errback=self.errback_venue,
                meta={
                    "gold_record": gold,
                    "base_url": base_url,
                    "stage": "candidate_page",
                    "candidate_chunks": candidate_chunks,
                    "visited_count": 1,
                    "handle_httpstatus_all": True,
                },
                dont_filter=True,
            )
"""
"""
    def parse_candidate_page(self, response):
        gold = response.meta["gold_record"]
        existing_chunks = response.meta.get("candidate_chunks", [])

        page_chunks = self.extract_candidate_chunks(response)
        all_chunks = existing_chunks + page_chunks

        yield self.build_item(
            response=response,
            gold=gold,
            candidate_chunks=all_chunks,
            scrape_stage="homepage_plus_candidate_page",
        )

    def extract_likely_internal_links(self, response, base_url):
        base_domain = urlparse(base_url).netloc.lower().replace("www.", "")

        extractor = LinkExtractor(
            allow_domains=[base_domain],
            deny_extensions=[
                "jpg", "jpeg", "png", "gif", "webp", "svg",
                "pdf", "zip", "mp4", "mov", "mp3",
            ],
            unique=True,
        )

        scored_links = []

        for link in extractor.extract_links(response):
            href = link.url
            text = f"{link.text or ''} {href}".lower()

            score = self.score_link_text(text)

            if score <= 0:
                continue

            scored_links.append((href, score))

        scored_links.sort(key=lambda x: x[1], reverse=True)

        return [href for href, score in scored_links]

    def extract_candidate_chunks(self, response):
        chunks = []

        selectors = response.css(
            "h1, h2, h3, h4, p, li, article, section, div"
        )

        for idx, selector in enumerate(selectors):
            text = " ".join(selector.css("::text").getall())
            text = self.clean_text(text)

            if len(text) < 30:
                continue

            if self.is_noise(text):
                continue

            if self.is_menu_block(text):
                continue

            score = self.score_text(text)

            if score <= 0:
                continue

            chunks.append({
                "chunk_id": idx,
                "text": text[:1000],
                "chars": len(text),
                "score": score,
                "keyword_hits": self.keyword_hits(text),
                "has_price": bool(re.search(r"\$\s?\d+", text)),
                "has_percent": bool(re.search(r"\d+\s?%", text)),
                "has_time": bool(re.search(r"\b(mon|tue|wed|thu|fri|sat|sun|daily|weekly|happy hour|\d{1,2}\s?(am|pm))\b", text, re.I)),
            })

        chunks.sort(key=lambda c: c["score"], reverse=True)
        return chunks[:20]

    def build_item(self, response, gold, candidate_chunks, scrape_stage):
        best = candidate_chunks[0] if candidate_chunks else None

        page_text = self.clean_text(" ".join(response.css("body ::text").getall()))
        page_score = self.score_text(page_text)
        keyword_hits = self.keyword_hits(page_text)

        item = VenueScrapeItem()
        item["venue_id"] = gold.get("venue_id", "")
        item["venue_name"] = gold.get("venue_name", "")
        item["source_url"] = gold.get("Source URL", "")
        item["business_type_gold"] = gold.get("Business Type", "")
        # item["experience_category_gold"] = gold.get("Experience Category", "")
        item["incentive_category_gold"] = gold.get("Incentive Category", "")
        item["teaser_gold"] = gold.get("Incentive Teaser", "")
        item["description_gold"] = gold.get("Full Incentive Description", "")

        item["scraped_url"] = response.url
        item["final_url"] = response.url
        item["status"] = response.status
        item["scrape_stage"] = scrape_stage

        item["page_title"] = self.clean_text(" ".join(response.css("title::text").getall()))
        item["text_chars"] = len(page_text)
        item["incentive_score"] = page_score
        item["keyword_hits"] = ", ".join(keyword_hits)

        item["top_candidate_text"] = best["text"] if best else ""
        item["top_candidate_score"] = best["score"] if best else 0
        item["all_candidate_chunks"] = " ||| ".join(
            c["text"] for c in candidate_chunks[:8]
        )

        item["failure_type"] = self.classify_failure(response, page_text, candidate_chunks)
        item["notes"] = ""

        return item

    def classify_failure(self, response, page_text, candidate_chunks):
        if response.status in {401, 403, 429}:
            return "blocked_or_forbidden"

        if response.status >= 400:
            return "request_fail"

        title = self.clean_text(" ".join(response.css("title::text").getall())).lower()
        lower_text = page_text.lower()

        stale_markers = [
            "domain for sale",
            "buy this domain",
            "parkingcrew",
            "sedo",
            "this domain is parked",
        ]

        if any(marker in title or marker in lower_text for marker in stale_markers):
            return "wrong_or_stale_url"

        if len(page_text) < 300:
            return "js_required_or_low_text"

        if not candidate_chunks:
            return "no_incentive_keywords"

        return "ok"

    def errback_venue(self, failure):
        request = failure.request
        gold = request.meta.get("gold_record", {})

        item = VenueScrapeItem()
        item["venue_id"] = gold.get("venue_id", "")
        item["venue_name"] = gold.get("venue_name", "")
        item["source_url"] = gold.get("Source URL", "")
        item["business_type_gold"] = gold.get("Business Type", "")
        # item["experience_category_gold"] = gold.get("Experience Category", "")
        item["incentive_category_gold"] = gold.get("Incentive Category", "")
        item["teaser_gold"] = gold.get("Incentive Teaser", "")
        item["description_gold"] = gold.get("Full Incentive Description", "")

        item["scraped_url"] = request.url
        item["final_url"] = ""
        item["status"] = ""
        item["scrape_stage"] = request.meta.get("stage", "unknown")

        item["page_title"] = ""
        item["text_chars"] = 0
        item["incentive_score"] = 0
        item["keyword_hits"] = ""

        item["top_candidate_text"] = ""
        item["top_candidate_score"] = 0
        item["all_candidate_chunks"] = ""

        # item["failure_type"] = "request_fail"
        item["failure_type"] = self.classify_exception_failure(failure)
        item["notes"] = repr(failure.value)

        yield item

    def clean_text(self, text):
        text = text or ""
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    def score_text(self, text):
        lower = text.lower()
        score = 0

        for kw in INCENTIVE_KEYWORDS:
            if kw in lower:
                score += 1

        if re.search(r"\$\s?\d+", text):
            score += 2

        if re.search(r"\d+\s?%", text):
            score += 2

        if re.search(r"\b(mon|tue|wed|thu|fri|sat|sun|daily|weekly)\b", text, re.I):
            score += 1

        return score

    def keyword_hits(self, text):
        lower = text.lower()
        return sorted({kw for kw in INCENTIVE_KEYWORDS if kw in lower})

    def score_link_text(self, text):
        lower = text.lower()
        return sum(1 for kw in LINK_KEYWORDS if kw in lower)

    def is_noise(self, text):
        lower = text.lower()

        if any(phrase in lower for phrase in NOISE_PHRASES):
            return True

        words = lower.split()
        if len(words) > 8 and len(set(words)) / max(len(words), 1) < 0.35:
            return True

        return False

    def is_menu_block(self, text):
        lower = text.lower()
        dollar_count = text.count("$")

        if dollar_count < 2:
            return False

        has_food_word = any(word in lower for word in MENU_FOOD_WORDS)
        has_deal_word = any(
            word in lower
            for word in [
                "deal",
                "special",
                "discount",
                "happy hour",
                "half off",
                "free",
                "promo",
                "offer",
            ]
        )

        return has_food_word and not has_deal_word
    
    def classify_exception_failure(self, failure):
        text = repr(failure.value).lower()

        if "dns lookup failed" in text or "cannotresolvehost" in text:
            return "dns_unresolved"

        if "timeout" in text:
            return "timeout"

        if "connection refused" in text:
            return "connection_refused"

        if "certificate" in text or "ssl" in text:
            return "ssl_error"

        return "request_fail"
"""