import re
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

        "HTTPCACHE_ENABLED": False,
        "COOKIES_ENABLED": True,
        "LOG_LEVEL": "INFO",
        "ITEM_PIPELINES": {},
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.start_url = "https://m.yardhouse.com/happy-hour"

    async def start(self):
        yield scrapy.Request(
            url=self.start_url,
            callback=self.parse,
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
            },
        )

    async def parse(self, response):
        page = response.meta["playwright_page"]

        if page is None:
            self.logger.error(
                "No Playwright page attached. flags=%s meta_keys=%s url=%s",
                response.flags,
                list(response.meta.keys()),
                response.url,
            )
            return

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

            self.logger.info("==================================BEGIN==================================")
            self.logger.info("Final URL: %s", page.url)

            match_half_off = page.locator("div").filter(
                has_text = re.compile("half off", re.I)
            )

            # Filter by Length:
            # Evaluates all values from match_half_off.
            # This maps text, word length, and the children of the div/class
            # to {text, word, children } data structure.
            # NOTE: Children might not be necessary for the final result.
            filter_by_length = await match_half_off.evaluate_all("""
                els => els.map(el => {
                    const text = (el.innerText || "").trim();
                    return { className: el.className, words: text.split(/\\s+/).length, text };
                }).filter(row => row.words > 2 && row.words <= 180)
            """)

            # Pass filter_by_length Into Function:
            self.logger.info(filter_by_length)

            for item in filter_by_length:
                yield item

        finally:
            await page.close()

    async def safe_click(self, locator, timeout=3000, label="element"):
        try:
            await locator.click(timeout=timeout)
            self.logger.info("Clicked %s.", label)
            return True
        except:
            self.logger.info("Did not find %s. Continuing.", label)
            return False
    async def safe_search_bar(self, search_box, timeout=1000, search_location="Los Angeles, CA", get_page=None):
        try:
            await search_box.wait_for(timeout=1000)
            await search_box.fill(search_location)
            await get_page.wait_for_timeout(1000)
            await search_box.press("ArrowDown")
            await search_box.press("Enter")
            await get_page.wait_for_timeout(1000)
            select_button = get_page.get_by_role("button", name=re.compile("SELECT", re.I)).first
            await select_button.wait_for(timeout=1000)
            await select_button.click(timeout=timeout)
            return True 
        except:
            self.logger.info("Did not find Search Bar. Continuing")
            return False

    def clean_text(self, text):
        if not text:
            return ""
        text = text.replace("\xa0", " ")
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    async def errback_close_page(self, failure):
        page = failure.request.meta.get("playwright_page")
        if page is not None and not page.is_closed():
            await page.close()