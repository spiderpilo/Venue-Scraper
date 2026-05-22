import os
import json
from pathlib import Path
import anthropic
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

CATEGORIES = [
    "No Incentive", "Live Music", "Early Entry", "Group Booking",
    "Matinee Deal", "Happy Hour", "Free", "Discount",
]

_FEW_SHOT = [
    {
        "text": "$4 draft beers during live music nights Wed–Sun 4:00 PM – 7:00 PM",
        "result": {
            "category": "Live Music",
            "value": "$4 draft beers",
            "timing": "Wed–Sun 4:00 PM – 7:00 PM",
            "teaser": "Live Music Happy Hour",
            "description": "$4 draft beers during live music nights Wed–Sun 4:00 PM – 7:00 PM",
        },
    },
    {
        "text": "$10 cover before 10 PM (regular $20) Thu–Sat",
        "result": {
            "category": "Early Entry",
            "value": "$10 cover (save $10)",
            "timing": "Thu–Sat before 10:00 PM",
            "teaser": "Early Entry Discount",
            "description": "$10 cover before 10 PM (regular $20) Thu–Sat",
        },
    },
    {
        "text": "Free live country music performances every Friday and Saturday night, no cover charge",
        "result": {
            "category": "Live Music",
            "value": "Free, no cover",
            "timing": "Fri & Sat",
            "teaser": "Free Live Music Nights",
            "description": "Free live country music performances every Friday and Saturday night, no cover charge",
        },
    },
    {
        "text": "Happy hour specials: half-price appetizers and $5 cocktails Monday through Friday 3–6 PM",
        "result": {
            "category": "Happy Hour",
            "value": "Half-price appetizers, $5 cocktails",
            "timing": "Mon–Fri 3:00 PM – 6:00 PM",
            "teaser": "Happy Hour Specials",
            "description": "Half-price appetizers and $5 cocktails Monday through Friday 3–6 PM",
        },
    },
]

_SYSTEM_BASE = """\
You extract venue incentive information from scraped website text.

Return ONLY a JSON object with these fields:
- category: one of """ + json.dumps(CATEGORIES) + """
- value: what the deal is, e.g. "30% off popcorn", "$4 draft beers", "free entry"
- timing: days and times, e.g. "Tue 7:00 PM – 10:00 PM", "Fri & Sat 8:00 PM – 12:00 AM"
- teaser: 2–5 word label, e.g. "Happy Hour Specials", "Free Live Music Nights"
- description: one clean sentence describing the full incentive

If no incentive is present, set category to "No Incentive" and leave other fields empty strings.

Category guidance by venue type:
- Nightclub / bar: prefer "Early Entry" (reduced/free cover before a certain time) over "Happy Hour"
- Live Music venue: prefer "Live Music" when free or discounted entry for live performances
- Bowling / Movie Theater / Museum / Aquarium: prefer "Matinee Deal" for time-based discounts, "Group Booking" for group rates
- Restaurant / dining: prefer "Happy Hour" for drink/food specials
- When the deal is simply a % or $ discount with no specific category signal, use "Discount"
"""


def _build_messages(text: str, business_type: str = "") -> list:
    messages = []
    for ex in _FEW_SHOT:
        messages.append({"role": "user", "content": ex["text"]})
        messages.append({"role": "assistant", "content": json.dumps(ex["result"])})
    user_content = text[:4000]
    if business_type:
        user_content = f"[Venue type: {business_type}]\n\n{user_content}"
    messages.append({"role": "user", "content": user_content})
    return messages


def extract_with_claude(text: str, business_type: str = "") -> dict:
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key or api_key == "your_key_here":
        return _empty("ANTHROPIC_API_KEY not set")

    client = anthropic.Anthropic(api_key=api_key)

    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=256,
            system=_SYSTEM_BASE,
            messages=_build_messages(text, business_type),
        )
        raw = response.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        data = json.loads(raw)
        return {
            "category":    data.get("category", "No Incentive"),
            "value":       data.get("value", ""),
            "timing":      data.get("timing", ""),
            "teaser":      data.get("teaser", ""),
            "description": data.get("description", ""),
            "source":      "claude",
        }
    except Exception as e:
        return _empty(f"Claude error: {e}")


def _empty(note: str) -> dict:
    return {
        "category": "No Incentive",
        "value": "",
        "timing": "",
        "teaser": "",
        "description": "",
        "source": "error",
        "error": note,
    }
