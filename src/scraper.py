import requests
from bs4 import BeautifulSoup


COMMON_INCENTIVE_PATHS = [
    "",
    "/happy-hour",
    "/happyhour",
    "/specials",
    "/events",
    "/promotions",
    "/deals",
    "/menu",
]


def scrape_page_text(url):
    try:
        headers = {
            "User-Agent": "Mozilla/5.0"
        }

        response = requests.get(url, headers=headers, timeout=8)

        if response.status_code != 200:
            return ""

        soup = BeautifulSoup(response.text, "html.parser")

        for tag in soup(["script", "style", "nav", "footer"]):
            tag.decompose()

        return soup.get_text(" ", strip=True)

    except Exception:
        return ""


def scrape_venue_pages(base_url):
    if not base_url:
        return ""

    all_text = ""

    for path in COMMON_INCENTIVE_PATHS:
        url = base_url.rstrip("/") + path
        print(f"Scraping: {url}")

        page_text = scrape_page_text(url)

        if page_text:
            all_text += " " + page_text

    return all_text