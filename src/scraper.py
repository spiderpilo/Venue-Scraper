import os
import re
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
    "/promotions",
    "/events",
    "/menu",
    "",           # homepage last
]

EARLY_STOP_PATHS = {"/happy-hour", "/happyhour", "/specials", "/deals"}

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


def _incentive_score(text: str) -> int:
    """Count how many distinct incentive keywords appear in the text."""
    if not text:
        return 0
    lower = text.lower()
    return sum(1 for kw in INCENTIVE_KEYWORDS if kw in lower)


def _extract_relevant_text(html: str) -> str:
    """
    Return only the paragraphs/blocks that contain incentive keywords,
    capped at MAX_TEXT_CHARS. Falls back to full page text if nothing matches.
    """
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "noscript", "header"]):
        tag.decompose()

    # Gather meaningful text blocks that mention incentives
    relevant = []
    for el in soup.find_all(["p", "li", "h1", "h2", "h3", "div", "section", "span"]):
        block = el.get_text(" ", strip=True)
        if len(block) >= 20 and _incentive_score(block) >= 1:
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
        return _extract_relevant_text(r.text)
    except Exception:
        return ""


_LINK_KEYWORDS = [
    "happy-hour", "happyhour", "happy_hour", "specials", "special",
    "deals", "deal", "promo", "promotion", "offer", "offers", "discount",
    "events", "entertainment", "menu", "drinks", "drink",
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


def _fetch_raw_html_playwright(url: str) -> str:
    """Render a single URL with Playwright and return raw HTML."""
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            ctx = browser.new_context(user_agent=_HEADERS["User-Agent"])
            page = ctx.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=15_000)
            page.wait_for_timeout(1_200)
            html = page.content()
            browser.close()
            return html
    except Exception:
        return ""


def _fetch_paths_with_playwright(base: str, paths: list) -> dict:
    """Open one browser, navigate each path, return {path: relevant_text}."""
    results = {p: "" for p in paths}
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            ctx  = browser.new_context(user_agent=_HEADERS["User-Agent"])
            page = ctx.new_page()
            for path in paths:
                url = base + path
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=15_000)
                    page.wait_for_timeout(1_200)
                    results[path] = _extract_relevant_text(page.content())
                except Exception:
                    results[path] = ""
            browser.close()
    except Exception:
        pass
    return results


# ── public API ────────────────────────────────────────────────────────────────

def scrape_venue_pages(base_url: str) -> str:
    if not base_url:
        return ""

    base = _clean_base(base_url)
    page_texts: dict[str, str] = {}

    # ── Pass 1: requests, priority order, early-stop ──────────────────────────
    for path in INCENTIVE_PATHS:
        url = base + path
        print(f"Scraping: {url}")
        text = _fetch_with_requests(url)
        page_texts[path] = text

        score = _incentive_score(text)
        if path in EARLY_STOP_PATHS and score >= 3:
            print(f"  → strong incentive content at {path} (score {score}), stopping early")
            break

    # ── Pass 1.5: homepage link discovery ────────────────────────────────────
    best_so_far = max((_incentive_score(t) for t in page_texts.values()), default=0)
    if best_so_far < 3:
        homepage_html = _fetch_raw_html(base)
        discovered = _extract_internal_links(homepage_html, base)

        # If requests got no useful links, try Playwright-rendered homepage
        if not discovered and _check_playwright():
            print(f"  → JS homepage for link discovery…")
            homepage_html = _fetch_raw_html_playwright(base)
            discovered = _extract_internal_links(homepage_html, base)

        discovered = discovered[:5]
        if discovered:
            print(f"  → crawling {len(discovered)} discovered link(s)…")
            for link_url, _ in discovered:
                path_key = urlparse(link_url).path.rstrip("/") or "/"
                if path_key not in page_texts:
                    text = _fetch_with_requests(link_url)
                    page_texts[path_key] = text
                    score = _incentive_score(text)
                    if score >= 3:
                        print(f"    strong content at {path_key} (score {score}), stopping")
                        break

    # ── Pass 2: JS fallback — only on paths where requests returned little ────
    sparse = [p for p, t in page_texts.items() if len(t) < MIN_USEFUL_CHARS]
    if sparse and _check_playwright():
        # Only bother with the highest-priority sparse paths (cap at 4)
        priority_sparse = [p for p in INCENTIVE_PATHS if p in sparse][:4]
        print(f"  → JS renderer for {len(priority_sparse)} sparse path(s)…")
        js = _fetch_paths_with_playwright(base, priority_sparse)
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


def fallback_search(venue_name: str, city: str = "") -> str:
    """
    Search Google via Serper.dev for the venue's specials/happy hour info.
    Used when the venue's own website can't be scraped.
    Returns combined snippet text, or empty string if nothing found.
    """
    api_key = os.environ.get("SERPER_API_KEY", "")
    if not api_key:
        return ""

    query = f'"{venue_name}" {city} happy hour specials deals'.strip()
    print(f"  → Serper fallback: {query}")
    try:
        r = requests.post(
            "https://google.serper.dev/search",
            headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
            json={"q": query, "num": 5},
            timeout=10,
        )
        if r.status_code != 200:
            return ""

        data = r.json()
        parts = []
        for result in data.get("organic", []):
            title = result.get("title", "")
            snippet = result.get("snippet", "")
            if snippet:
                parts.append(f"{title}. {snippet}")

        # Also include answer box if present
        answer = data.get("answerBox", {}).get("answer") or data.get("answerBox", {}).get("snippet", "")
        if answer:
            parts.insert(0, answer)

        return " ".join(parts)[:MAX_TEXT_CHARS]
    except Exception:
        return ""
