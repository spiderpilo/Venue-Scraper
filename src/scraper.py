def scrape_multiple_pages(base_url):
    if not base_url:
        return ""

    paths = [
        "",
        "/happy-hour",
        "/specials",
        "/events",
        "/promotions",
        "/deals"
    ]

    full_text = ""

    for path in paths:
        try:
            url = base_url.rstrip("/") + path

            headers = {
                "User-Agent": "Mozilla/5.0"
            }

            response = requests.get(url, headers=headers, timeout=5)

            if response.status_code != 200:
                continue

            soup = BeautifulSoup(response.text, "html.parser")

            for tag in soup(["script", "style", "nav", "footer"]):
                tag.decompose()

            text = soup.get_text(" ", strip=True)
            full_text += " " + text

        except:
            continue

    return full_text