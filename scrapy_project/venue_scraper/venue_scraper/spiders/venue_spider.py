import re
import scrapy
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

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

        # This replaces browser.new_context(...)
        "PLAYWRIGHT_CONTEXTS": {
            "la_context": {
                "viewport": {
                    "width": 1920,
                    "height": 1080,
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
                    "timeout" : 15000,
                },
                "dont_cache": True,
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

            # Get Body Text from URL:
            body_text = await page.locator("body").inner_text(timeout=1000)
            body_text = self.clean_text(body_text)

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
            await select_button.click()
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