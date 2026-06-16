import os
import re
import time
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urlunparse, quote_plus

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

_playwright_available = None

# Highest-signal paths tried first; early-stop on these if content is good
INCENTIVE_PATHS = [
    "/happy-hour",
    "/happyhour",
    "/specials",
    "/deals",
    "/entertainment",
    "/live-music",
    "/events",
    "/menu",
    "",           # homepage last
]

EARLY_STOP_PATHS = {
    "/happy-hour", "/happyhour", "/specials", "/deals",
    "/entertainment", "/live-music",
}

# Keyword list used for per-page scoring and relevant-paragraph extraction
INCENTIVE_KEYWORDS = [
    "happy hour", "discount", "deal", "special", "promo",
    "free", "live music", "no cover", "% off", "half off",
    "early entry", "matinee", "early bird", "cover charge",
    "admission", "save", "unlimited", "twilight",
    "tasting", "wristband", "group booking", "group event",
    "wednesday", "thursday", "friday", "saturday", "sunday",
    "$",
]

# Min chars for a page to be considered useful
MIN_USEFUL_CHARS = 300

# Max chars to pass onward per page (keeps inference fast)
MAX_TEXT_CHARS = 8_000

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}


# ── helpers ───────────────────────────────────────────────────────────────────

def _check_playwright():
    global _playwright_available
    if _playwright_available is None:
        try:
            from playwright.sync_api import sync_playwright  # noqa: F401
            _playwright_available = True
        except ImportError:
            _playwright_available = False
    return _playwright_available


def _clean_base(url: str) -> str:
    """Strip query string and fragment so subpaths append cleanly."""
    p = urlparse(url)
    return urlunparse((p.scheme, p.netloc, p.path.rstrip("/"), "", "", ""))


_DEAL_KEYWORDS = {
    "happy hour", "discount", "deal", "special", "promo", "free",
    "no cover", "% off", "half off", "cover charge", "admission",
    "save", "unlimited", "early entry", "matinee", "early bird",
    "twilight", "group booking", "wristband", "guest list",
}

_MENU_FOOD_WORDS = re.compile(
    r"\b(gluten.?free|vegetarian|vegan|entree|appetizer|"
    r"salad|soup|pasta|burger|sandwich|tacos?|pizza|sushi|"
    r"steak|chicken|salmon|shrimp|fries|dessert|brunch menu|"
    r"add.on|sides?|combo|platter)\b",
    re.IGNORECASE,
)


def _incentive_score(text: str) -> int:
    """Count how many distinct incentive keywords appear in the text."""
    if not text:
        return 0
    lower = text.lower()
    return sum(1 for kw in INCENTIVE_KEYWORDS if kw in lower)


def _is_menu_block(text: str) -> bool:
    """
    Return True if this block looks like a food/drink menu item rather than
    a deal description. A block is a menu dump if it has multiple $ amounts
    but no deal-context words.
    """
    dollar_count = text.count("$")
    if dollar_count < 2:
        return False
    lower = text.lower()
    has_deal_context = any(kw in lower for kw in _DEAL_KEYWORDS)
    has_food_words   = bool(_MENU_FOOD_WORDS.search(text))
    return has_food_words and not has_deal_context


def _extract_relevant_text(html: str) -> str:
    """
    Return only the paragraphs/blocks that contain incentive keywords,
    capped at MAX_TEXT_CHARS. Falls back to full page text if nothing matches.
    Filters out pure menu-price blocks (many $ amounts with food words, no deal context).
    """
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "noscript", "header"]):
        tag.decompose()

    # Gather meaningful text blocks that mention incentives
    relevant = []
    for el in soup.find_all(["p", "li", "h1", "h2", "h3", "div", "section", "span"]):
        block = el.get_text(" ", strip=True)
        if len(block) >= 20 and _incentive_score(block) >= 1:
            if not _is_menu_block(block):
                relevant.append(block)

    if relevant:
        return " ".join(relevant)[:MAX_TEXT_CHARS]

    # Fallback: whole page text, capped
    return soup.get_text(" ", strip=True)[:MAX_TEXT_CHARS]


def _fetch_raw_html(url: str) -> str:
    try:
        r = requests.get(url, headers=_HEADERS, timeout=10)
        if r.status_code != 200:
            return ""
        return r.text
    except Exception:
        return ""


def _fetch_with_requests(url: str) -> str:
    try:
        r = requests.get(url, headers=_HEADERS, timeout=10)
        if r.status_code != 200:
            return ""
        if _is_spa_shell(r.text):
            return ""   # let Playwright handle it
        return _extract_relevant_text(r.text)
    except Exception:
        return ""


_LINK_KEYWORDS = [
    "happy-hour", "happyhour", "happy_hour", "specials", "special",
    "deals", "deal", "promo", "promotion", "offer", "offers", "discount",
    "live-music", "live-entertainment", "live_music", "entertainment",
    "music", "shows", "nightlife", "drink-specials", "drink_specials",
    "events", "menu", "drinks", "drink",
    "dining", "nightly", "weekly", "daily", "food-drink", "food-and-drink",
]


def _score_link(href: str, anchor: str) -> int:
    text = (href + " " + anchor).lower()
    return sum(1 for kw in _LINK_KEYWORDS if kw in text)


def _extract_internal_links(html: str, base: str) -> list:
    """Return (full_url, score) for internal links with score > 0, sorted desc."""
    soup = BeautifulSoup(html, "html.parser")
    parsed_base = urlparse(base)
    seen, links = set(), []

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        anchor = a.get_text(" ", strip=True)

        if href.startswith("/"):
            full_url = f"{parsed_base.scheme}://{parsed_base.netloc}{href}"
        elif href.startswith("http"):
            full_url = href
        else:
            continue

        if urlparse(full_url).netloc != parsed_base.netloc:
            continue

        clean = full_url.rstrip("/").split("?")[0].split("#")[0]
        if clean in seen or clean == base:
            continue
        seen.add(clean)

        score = _score_link(href, anchor)
        if score > 0:
            links.append((clean, score))

    return sorted(links, key=lambda x: -x[1])


_CHROMIUM_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--no-sandbox",
    "--disable-dev-shm-usage",
    "--disable-gpu",
    "--no-first-run",
]

_PW_CONTEXT_OPTS = {
    "user_agent": _HEADERS["User-Agent"],
    "viewport": {"width": 1920, "height": 1080},
    "locale": "en-US",
    "timezone_id": "America/Los_Angeles",
    "java_script_enabled": True,
}

_stealth_available = None

# Root div IDs used by popular JS frameworks — page body is empty until JS runs
_SPA_ROOT_IDS = {"root", "app", "__next", "__nuxt", "gatsby-focus-wrapper", "react-root"}


def _is_spa_shell(html: str) -> bool:
    """
    Return True if the HTML looks like an unrendered SPA shell.
    Heuristic: very little visible text AND a known framework root div present.
    """
    if not html:
        return False
    soup = BeautifulSoup(html, "html.parser")
    if len(soup.get_text(" ", strip=True)) > 300:
        return False  # enough content — not a shell
    return any(
        tag.get("id", "") in _SPA_ROOT_IDS
        for tag in soup.find_all("div", id=True)
    )


def _try_apply_stealth(page):
    """Apply playwright-stealth if installed; silently skip if not."""
    global _stealth_available
    if _stealth_available is None:
        try:
            from playwright_stealth import stealth_sync  # noqa: F401
            _stealth_available = True
        except ImportError:
            _stealth_available = False
    if _stealth_available:
        from playwright_stealth import stealth_sync
        stealth_sync(page)


def _pw_wait_for_content(page) -> None:
    """
    Wait for a JS-rendered page to fully populate.
    Strategy: try networkidle (catches SPA data fetches) with a 3s cap,
    then scroll to trigger lazy-loaded sections, then a short settle buffer.
    Sites with continuous ad/analytics traffic never reach networkidle, so
    the timeout fallback ensures we don't hang.
    """
    try:
        page.wait_for_load_state("networkidle", timeout=3_000)
    except Exception:
        page.wait_for_timeout(1_200)
    try:
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(500)
    except Exception:
        pass


def _fetch_raw_html_playwright(url: str, deadline: float = 0) -> str:
    """Render a single URL with Playwright and return raw HTML."""
    if deadline and time.time() > deadline:
        return ""
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True, args=_CHROMIUM_ARGS)
            ctx = browser.new_context(**_PW_CONTEXT_OPTS)
            page = ctx.new_page()
            _try_apply_stealth(page)
            page.goto(url, wait_until="domcontentloaded", timeout=10_000)
            _pw_wait_for_content(page)
            html = page.content()
            browser.close()
            return html
    except Exception:
        return ""


def _fetch_paths_with_playwright(base: str, paths: list, deadline: float = 0) -> dict:
    """Open one browser, navigate each path, return {path: relevant_text}."""
    results = {p: "" for p in paths}
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True, args=_CHROMIUM_ARGS)
            ctx = browser.new_context(**_PW_CONTEXT_OPTS)
            page = ctx.new_page()
            _try_apply_stealth(page)
            for path in paths:
                if deadline and time.time() > deadline:
                    print(f"  -> scrape budget hit, skipping remaining JS paths")
                    break
                url = base + path
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=10_000)
                    _pw_wait_for_content(page)
                    results[path] = _extract_relevant_text(page.content())
                except Exception:
                    results[path] = ""
            browser.close()
    except Exception:
        pass
    return results


# ── public API ────────────────────────────────────────────────────────────────

# Extra subpaths tried for specific venue types when the main scrape is sparse.
# These are low-traffic paths that often surface admission/ticket/drink pricing.
_EXTRA_PATHS_BY_TYPE: dict[str, list] = {
    "nightclub": ["/tickets", "/bottle-service", "/vip", "/admission", "/pricing"],
    "bar":       ["/drink-specials", "/bar-specials", "/pricing", "/drinks-menu"],
    "live_music":["/tickets", "/admission", "/pricing", "/shows"],
    "entertainment": ["/tickets", "/admission", "/pricing"],
}


def _extra_paths_for_type(business_type: str) -> list:
    bt = (business_type or "").lower()
    if any(kw in bt for kw in ("nightclub", "night club", "casino")):
        return _EXTRA_PATHS_BY_TYPE["nightclub"]
    if "live music" in bt:
        return _EXTRA_PATHS_BY_TYPE["live_music"]
    if "bar" in bt and "restaurant" not in bt:
        return _EXTRA_PATHS_BY_TYPE["bar"]
    if "entertainment" in bt:
        return _EXTRA_PATHS_BY_TYPE["entertainment"]
    return []


def scrape_venue_pages(base_url: str, business_type: str = "", max_time: float = 45.0) -> str:
    if not base_url:
        return ""

    deadline = time.time() + max_time
    base = _clean_base(base_url)
    page_texts: dict[str, str] = {}

    # ── Pass 1: requests, priority order, early-stop ──────────────────────────
    for path in INCENTIVE_PATHS:
        if time.time() > deadline:
            print(f"  -> scrape budget ({max_time:.0f}s) exceeded in pass 1, stopping")
            break
        url = base + path
        print(f"Scraping: {url}")
        text = _fetch_with_requests(url)
        page_texts[path] = text

        score = _incentive_score(text)
        if path in EARLY_STOP_PATHS and score >= 3:
            print(f"  -> strong incentive content at {path} (score {score}), stopping early")
            break

    # ── Pass 1.5: homepage link discovery ────────────────────────────────────
    best_so_far = max((_incentive_score(t) for t in page_texts.values()), default=0)
    if best_so_far < 3 and time.time() < deadline:
        homepage_html = _fetch_raw_html(base)
        discovered = _extract_internal_links(homepage_html, base)

        # If requests got no useful links, try Playwright-rendered homepage
        if not discovered and _check_playwright() and time.time() < deadline:
            print(f"  -> JS homepage for link discovery...")
            homepage_html = _fetch_raw_html_playwright(base, deadline=deadline)
            discovered = _extract_internal_links(homepage_html, base)

        discovered = discovered[:5]
        if discovered:
            print(f"  -> crawling {len(discovered)} discovered link(s)...")
            for link_url, _ in discovered:
                if time.time() > deadline:
                    break
                path_key = urlparse(link_url).path.rstrip("/") or "/"
                if path_key not in page_texts:
                    text = _fetch_with_requests(link_url)
                    page_texts[path_key] = text
                    score = _incentive_score(text)
                    if score >= 3:
                        print(f"    strong content at {path_key} (score {score}), stopping")
                        break

    # ── Pass 1.6: venue-type deep paths — pricing/admission subpages ─────────
    best_so_far = max((_incentive_score(t) for t in page_texts.values()), default=0)
    if best_so_far < 3 and time.time() < deadline:
        extra = _extra_paths_for_type(business_type)
        unseen_extra = [p for p in extra if p not in page_texts]
        if unseen_extra:
            print(f"  -> deep type paths ({business_type}): {unseen_extra}")
            for path in unseen_extra:
                if time.time() > deadline:
                    break
                text = _fetch_with_requests(base + path)
                page_texts[path] = text
                score = _incentive_score(text)
                if score >= 3:
                    print(f"    strong content at {path} (score {score}), stopping")
                    break

    # ── Pass 2: JS fallback — only on paths where requests returned little ────
    sparse = [p for p, t in page_texts.items() if len(t) < MIN_USEFUL_CHARS]
    if sparse and _check_playwright() and time.time() < deadline:
        priority_sparse = [p for p in INCENTIVE_PATHS if p in sparse][:3]
        print(f"  -> JS renderer for {len(priority_sparse)} sparse path(s)...")
        js = _fetch_paths_with_playwright(base, priority_sparse, deadline=deadline)
        for path, js_text in js.items():
            if _incentive_score(js_text) > _incentive_score(page_texts.get(path, "")):
                page_texts[path] = js_text

    # ── Pick the single best page rather than concatenating everything ─────────
    if not page_texts:
        return ""

    best_path = max(page_texts, key=lambda p: _incentive_score(page_texts[p]))
    best_text = page_texts[best_path]
    best_score = _incentive_score(best_text)

    # If the best dedicated page is strong, use it alone.
    # Otherwise blend the top 2 pages to give the model more signal.
    if best_score >= 3 or len(page_texts) == 1:
        return best_text

    ranked = sorted(page_texts.items(), key=lambda kv: -_incentive_score(kv[1]))
    combined = " ".join(t for _, t in ranked[:2] if t)
    return combined[:MAX_TEXT_CHARS]


# Review/aggregator domains whose snippets are about nearby venues, not this one
_AGGREGATOR_DOMAINS = {
    "yelp.com", "tripadvisor.com", "google.com", "maps.google.com",
    "yellowpages.com", "foursquare.com", "zomato.com", "opentable.com",
    "happyhour.io", "doordash.com", "grubhub.com", "ubereats.com",
    "menupages.com", "allmenus.com", "restaurantji.com",
}

# Yelp FAQ patterns that are noise (venue doesn't have the thing being asked about)
_YELP_FAQ_NOISE = re.compile(
    r"does .{3,50} have a happy hour\?|"
    r"does .{3,50} serve alcohol\?|"
    r"does .{3,50} take reservations\?|"
    r"\d+ photos.{0,5}\d+ reviews",
    re.IGNORECASE,
)

# SERP titles from aggregators that refer to *nearby* venues, not this one
_AGGREGATOR_TITLE = re.compile(
    r"(top \d+ best|best .{3,30} near|happy hour near|specials near|"
    r"restaurants near|bars near|updated 20\d\d)",
    re.IGNORECASE,
)


def fallback_search(venue_name: str, city: str = "") -> str:
    """
    Search Google via Serper.dev for the venue's specials/happy hour info.
    Filters out Yelp/aggregator results that describe nearby venues, not this one.
    Returns combined snippet text, or empty string if nothing found.
    """
    api_key = os.environ.get("SERPER_API_KEY", "")
    if not api_key:
        return ""

    query = f'"{venue_name}" {city} happy hour specials deals'.strip()
    print(f"  -> Serper fallback: {query}")
    try:
        r = requests.post(
            "https://google.serper.dev/search",
            headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
            json={"q": query, "num": 8},
            timeout=10,
        )
        if r.status_code != 200:
            return ""

        data = r.json()
        parts = []
        for result in data.get("organic", []):
            link    = result.get("link", "")
            title   = result.get("title", "")
            snippet = result.get("snippet", "")

            # Skip results from review/aggregator sites
            domain = urlparse(link).netloc.lower().lstrip("www.")
            if any(domain == agg or domain.endswith("." + agg) for agg in _AGGREGATOR_DOMAINS):
                continue

            # Skip SERP titles that clearly refer to nearby/other venues
            if _AGGREGATOR_TITLE.search(title):
                continue

            # Skip Yelp-style FAQ noise even if it slips through
            combined = f"{title}. {snippet}"
            if _YELP_FAQ_NOISE.search(combined):
                continue

            # Skip results where the venue name doesn't appear in the content —
            # these are about nearby venues, not this one (e.g. listicles, articles)
            if venue_name and venue_name.lower() not in combined.lower():
                continue

            if snippet:
                parts.append(combined)

        # Answer box — include only if it looks venue-specific (not a FAQ no-answer)
        answer = data.get("answerBox", {}).get("answer") or data.get("answerBox", {}).get("snippet", "")
        if answer and not _YELP_FAQ_NOISE.search(answer):
            parts.insert(0, answer)

        return " ".join(parts)[:MAX_TEXT_CHARS]
    except Exception:
        return ""


def fallback_search_pricing(venue_name: str, city: str = "", category: str = "") -> str:
    """
    Pricing-targeted Serper search, run only when initial extraction has Unknown value.
    Uses category-specific price keywords rather than generic deal language.
    """
    api_key = os.environ.get("SERPER_API_KEY", "")
    if not api_key:
        return ""

    if category in ("Early Entry", "Free"):
        price_terms = "cover charge admission price tickets"
    elif category in ("Happy Hour", "Discount"):
        price_terms = "drink prices happy hour menu specials"
    elif category == "Live Music":
        price_terms = "tickets admission cover charge price"
    elif category == "Group Booking":
        price_terms = "group pricing packages price per person"
    else:
        price_terms = "price admission tickets cover"

    query = f'"{venue_name}" {city} {price_terms}'.strip()
    print(f"  -> Serper pricing search: {query}")
    try:
        r = requests.post(
            "https://google.serper.dev/search",
            headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
            json={"q": query, "num": 6},
            timeout=10,
        )
        if r.status_code != 200:
            return ""

        data = r.json()
        parts = []
        for result in data.get("organic", []):
            link    = result.get("link", "")
            title   = result.get("title", "")
            snippet = result.get("snippet", "")

            domain = urlparse(link).netloc.lower().lstrip("www.")
            if any(domain == agg or domain.endswith("." + agg) for agg in _AGGREGATOR_DOMAINS):
                continue
            if _AGGREGATOR_TITLE.search(title):
                continue

            combined = f"{title}. {snippet}"
            if _YELP_FAQ_NOISE.search(combined):
                continue
            if venue_name and venue_name.lower() not in combined.lower():
                continue
            if snippet:
                parts.append(combined)

        answer = data.get("answerBox", {}).get("answer") or data.get("answerBox", {}).get("snippet", "")
        if answer and not _YELP_FAQ_NOISE.search(answer):
            parts.insert(0, answer)

        return " ".join(parts)[:MAX_TEXT_CHARS]
    except Exception:
        return ""

# -- Wayback Machine cache fallback -------------------------------------------

# Only check these paths — each one is an API call; keep it tight to avoid 429s
_WAYBACK_PATHS = ["/specials", "/happy-hour", "/deals", "/events", ""]

_WAYBACK_API = "https://archive.org/wayback/available?url={}"
_WAYBACK_DELAY = 1.0   # archive.org rate-limits ~5 req/min; 1s keeps us safe


def _get_wayback_snapshot(url: str) -> str:
    """Return the most recent archived snapshot URL, or '' on failure / 429."""
    try:
        r = requests.get(_WAYBACK_API.format(url), headers=_HEADERS, timeout=8)
        if r.status_code == 429:
            time.sleep(2)
            r = requests.get(_WAYBACK_API.format(url), headers=_HEADERS, timeout=8)
        if r.status_code != 200:
            return ""
        snap = r.json().get("archived_snapshots", {}).get("closest", {})
        if snap.get("available") and snap.get("status") == "200":
            return snap.get("url", "")
    except Exception:
        pass
    return ""


def scrape_wayback(base_url: str, deadline: float = 0) -> str:
    """
    Try Wayback Machine snapshots for key incentive subpaths.
    Last-resort fallback when the live site is fully bot-blocked.
    Returns the highest-scoring snapshot text, or '' if nothing archived.
    """
    if not base_url:
        return ""

    base = _clean_base(base_url)
    best_text = ""
    best_score = -1

    for path in _WAYBACK_PATHS:
        if deadline and time.time() > deadline:
            print(f"  -> scrape budget hit, skipping remaining Wayback paths")
            break
        target = base + path
        snapshot_url = _get_wayback_snapshot(target)
        time.sleep(_WAYBACK_DELAY)   # stay under archive.org rate limit
        if not snapshot_url:
            continue

        print(f"  -> Wayback ({path or '/'}) {snapshot_url[30:72]}...")
        text = _fetch_with_requests(snapshot_url)
        if not text:
            continue

        score = _incentive_score(text)
        if score > best_score:
            best_score = score
            best_text = text
            if score >= 3:
                break

    return best_text
