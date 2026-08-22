"""
Llama 3.1 8B incentive extractor via Ollama.
Drop-in replacement for extract_incentive_with_model() in model_extractor.py.
"""

import json
import os
import re
import time

import requests

from src.model_extractor import _has_incentive_keywords

OLLAMA_MODEL = "llama3.1:8b"

_OLLAMA_URLS = [
    os.environ.get("OLLAMA_URL", ""),
    "http://localhost:11434/api/generate",
    "http://host.docker.internal:11434/api/generate",
]

_active_url = None

_PROMPT = """\
You are extracting promotional incentives from venue website text.

CATEGORY DEFINITIONS:
- Happy Hour: drink/food specials at specific times (e.g. "$5 beers 3-6pm", "half price appetizers weekdays")
- Early Entry: no cover charge, free/reduced admission before a certain time (e.g. "free before 10pm", "no cover on guest list")
- Live Music: live bands, DJs, concerts, open mic (e.g. "live jazz every Friday", "DJ Saturday nights")
- Discount: % off, reduced pricing, promo codes, loyalty rewards (e.g. "20% off Tuesdays", "student discount")
- Free: free admission, free events, free item with no time restriction (e.g. "free entry all night", "free hot dog day")
- Group Booking: group rates, party packages, private events (e.g. "groups of 10+ get 15% off")
- Matinee Deal: time-based admission pricing, twilight tickets (e.g. "matinee tickets $8 before 4pm")
- No Incentive: opening hours, address, phone number, general descriptions, menu items, boilerplate

EXAMPLES OF INCENTIVES:
- "Join us for happy hour Monday-Friday 4-7pm, $5 wells and $6 craft beers" → Happy Hour, timing: Mon-Fri 4-7pm, value: $5
- "No cover charge before 10pm on Fridays and Saturdays" → Early Entry, timing: Fri-Sat before 10pm
- "Live music every Thursday night starting at 8pm, no cover" → Live Music, timing: Thursday 8pm
- "Twilight tickets available after 5pm for just $9" → Matinee Deal, timing: after 5pm, value: $9
- "Kids bowl free every Sunday morning" → Free, timing: Sunday morning
- "Group rates available for parties of 15 or more, 20% off" → Group Booking, value: 20% off
- "3 course summer special available now" → Discount

EXAMPLES OF NO INCENTIVE:
- "Monday to Thursday 10am-9pm, Friday to Sunday 9am-9pm" → No Incentive (just hours)
- "Located at 450 Main Street. Call us at (310) 555-1234" → No Incentive (contact info)
- "Award-winning cuisine crafted from locally sourced seasonal ingredients" → No Incentive (marketing copy)
- "Must be 21 or older to enter. Valid ID required." → No Incentive (policy)
- "View Menu Reserve Now Welcome To Taqueria Las Milpas" → No Incentive (nav/boilerplate)
- "Become a member and enjoy exclusive benefits" → No Incentive (membership upsell)
- "Subscribe to our newsletter for updates" → No Incentive (newsletter/subscription)
- "Join our loyalty program and earn points" → No Incentive (loyalty program signup)
- "Annual membership includes unlimited visits" → No Incentive (membership plan)

Analyze the text below. Extract the single BEST incentive if one exists.
If the text only contains hours, location, menu items, generic descriptions, membership plans, or newsletter signups — return No Incentive.

You MUST attempt to fill in ALL THREE of: teaser, timing, and value. Search the text carefully.
- timing: look for days of the week, time ranges, "daily", "every Friday", "weekends", etc.
- value: look for prices ($5, $9), percentages (20% off), or words like "free", "half price", "no cover"
- teaser: one sentence describing what the offer is (not just repeating timing or price)

Respond with JSON only, no explanation:
{{
  "category": "<one of: Happy Hour | Live Music | Early Entry | Discount | Free | Group Booking | Matinee Deal | No Incentive>",
  "teaser": "<one sentence max 10 words describing the offer, empty string if No Incentive>",
  "timing": "<days and times the incentive applies, or Unknown if not mentioned>",
  "value": "<price or discount e.g. $9 or 50% off or 'free', or Unknown if not mentioned>"
}}

Venue type: {business_type}
Text:
{text}
"""

_CATEGORY_MOTIVATOR = {
    "Happy Hour":    "Value",
    "Discount":      "Value",
    "Matinee Deal":  "Value",
    "Free":          "Free",
    "Early Entry":   "FOMO",
    "Live Music":    "Social",
    "Group Booking": "Social",
}

_TIME_FRAME_RE = re.compile(
    r"\b(mon|tue|wed|thu|fri|sat|sun|daily|nightly|weekday|weekend|"
    r"\d{1,2}(:\d{2})?\s*(am|pm)|every\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday|week|night|day))\b",
    re.IGNORECASE,
)

_VALID_CATEGORIES = {
    "Happy Hour", "Live Music", "Early Entry", "Discount",
    "Free", "Group Booking", "Matinee Deal", "No Incentive",
}

_MEMBERSHIP_PHRASES = {
    "membership", "become a member", "member sign", "member login",
    "members only", "member exclusive", "membership plan",
    "membership fee", "monthly membership", "annual membership",
    "membership required", "membership includes", "member benefits",
    "member benefit", "join as a member", "member pricing",
    "loyalty program", "loyalty points", "subscribe to our",
    "subscribe for", "join our mailing", "sign up for", "sign-up for",
    "newsletter", "rewards program", "points program", "rewards points",
    "reward points", "rewards app", "app rewards", "vip club",
    "earn points", "collect points", "redeem points", "cash back points",
}

# Matches "reward"/"rewards"/"rewarded" etc. as a whole word — bare
# substring matching would be fine here (unlike "point", nothing in real
# venue text collides with "reward").
_REWARD_RE = re.compile(r"\breward(s|ed|ing)?\b", re.IGNORECASE)

# "member(s)" preceded by one of these means "a person belonging to a
# group" (service members, family members, guest list members), not "a
# paying loyalty-club member" — don't flag those as membership pitches.
_MEMBER_EXCLUDE_QUALIFIERS = {
    "service", "military", "family", "team", "staff", "crew",
    "community", "board", "committee", "faculty", "congregation",
    "cast", "band",
}

# Bare "point"/"points" collides with real words ("appointment", "Point
# Loma"), so only flag it alongside a loyalty-points-scheme signal word —
# e.g. "earn double points", "75 base points for a gift", "points per $1
# spent". A sports score ("21+ point wins") won't have any of these nearby.
_POINTS_RE = re.compile(r"\bpoints?\b", re.IGNORECASE)
_POINTS_CONTEXT_WORDS = (
    "earn", "collect", "redeem", "spent", "toward", "club", "gift",
    "cash back", "loyalty", "bonus", "double", "base",
)


def _has_club_member_mention(text: str) -> bool:
    words = re.findall(r"[a-z]+", text.lower())
    for i, w in enumerate(words):
        if w not in ("member", "members"):
            continue
        prev = words[i - 1] if i > 0 else ""
        prev2 = " ".join(words[max(0, i - 2):i])
        if prev in _MEMBER_EXCLUDE_QUALIFIERS or prev2 == "guest list":
            continue
        return True
    return False


def _has_loyalty_points_mention(text: str) -> bool:
    if not _POINTS_RE.search(text):
        return False
    return any(w in text for w in _POINTS_CONTEXT_WORDS)


def _is_membership(*texts: str) -> bool:
    combined = " ".join(t for t in texts if t)
    lower = combined.lower()
    if any(p in lower for p in _MEMBERSHIP_PHRASES):
        return True
    if _REWARD_RE.search(lower):
        return True
    if _has_loyalty_points_mention(lower):
        return True
    return _has_club_member_mention(lower)


def missing_ollama_models(required, timeout: float = 3.0):
    """
    Check which of `required` model names are missing from the reachable Ollama
    instance. Returns None if Ollama itself couldn't be reached on any candidate URL.
    """
    global _active_url
    for url in [u for u in _OLLAMA_URLS if u]:
        tags_url = url.replace("/api/generate", "/api/tags")
        try:
            r = requests.get(tags_url, timeout=timeout)
            if r.status_code == 200:
                _active_url = url
                available = {m.get("name", "") for m in r.json().get("models", [])}
                return [m for m in required if m not in available]
        except Exception:
            continue
    return None


def _call_ollama(prompt: str, timeout: float = 30.0) -> str:
    global _active_url
    urls = [_active_url] if _active_url else [u for u in _OLLAMA_URLS if u]
    for url in urls:
        try:
            r = requests.post(
                url,
                json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
                timeout=timeout,
            )
            if r.status_code == 200:
                _active_url = url
                return r.json().get("response", "").strip()
        except Exception:
            continue
    return ""


def _parse_response(raw: str) -> dict | None:
    start = raw.find("{")
    end = raw.rfind("}") + 1
    if start == -1 or end == 0:
        return None
    try:
        return json.loads(raw[start:end])
    except json.JSONDecodeError:
        return None


def _derive_motivator(category: str, text: str) -> str:
    lower = text.lower()
    if re.search(r"\b(limited time|tonight only|today only|last chance|selling fast)\b", lower):
        return "FOMO"
    base = _CATEGORY_MOTIVATOR.get(category, "Value")
    if base == "Value" and category in ("Happy Hour", "Discount", "Matinee Deal"):
        if _TIME_FRAME_RE.search(text):
            return "FOMO"
    return base


def _infer_status(text: str) -> str:
    lower = text.lower()
    if any(w in lower for w in ("limited time", "while supplies last", "today only", "tonight only", "expires")):
        return "Limited Time"
    if re.search(r"\b(daily|weekly|every|each|nightly|mon|tue|wed|thu|fri|sat|sun)(day)?\b", lower, re.IGNORECASE):
        return "Ongoing"
    if text.strip():
        return "Ongoing"
    return "Unknown"


def _empty() -> dict:
    return {
        "category":         "No Incentive",
        "teaser":           "No incentive found",
        "description":      "No incentive found",
        "timing":           "Unknown",
        "motivator":        "Unknown",
        "cuisine":          "Unknown",
        "value":            "Unknown",
        "status":           "Unknown",
        "notes":            "",
        "model_confidence": 0.0,
        "all_predictions":  [],
        "source":           "no_result",
    }


def extract_incentive_with_llama(text: str, business_type: str = "", timing_metrics=None) -> dict:
    """
    Drop-in replacement for extract_incentive_with_model().
    Returns the same dict format consumed by run_model_pipeline.py.
    """
    t0 = time.time()

    if not text:
        if timing_metrics is not None:
            timing_metrics["model_inference_time"] = 0.0
        return _empty()

    # Pre-filter to keyword-matched sentences so incentive content isn't
    # buried past the 3000-char window when the scraper returns a full page fallback
    sentences = re.split(r"[.!?\n]", text)
    matched = []
    seen = set()
    for s in sentences:
        s = s.strip()
        if len(s) >= 10 and _has_incentive_keywords(s) and s not in seen:
            seen.add(s)
            matched.append(s)

    filtered_text = " ".join(matched) if matched else text
    prompt = _PROMPT.format(
        business_type=business_type or "Unknown",
        text=filtered_text[:3000],
    )

    raw = _call_ollama(prompt)
    elapsed = time.time() - t0

    if timing_metrics is not None:
        timing_metrics["model_inference_time"] = elapsed

    if not raw:
        return _empty()

    parsed = _parse_response(raw)
    if not parsed:
        return _empty()

    category = parsed.get("category", "No Incentive")
    if category not in _VALID_CATEGORIES:
        category = "No Incentive"

    if category == "No Incentive":
        return _empty()

    teaser = parsed.get("teaser", "").strip()
    timing = parsed.get("timing", "Unknown") or "Unknown"
    value  = parsed.get("value", "Unknown") or "Unknown"

    if _is_membership(teaser, timing, value):
        return _empty()

    motivator = _derive_motivator(category, teaser + " " + timing)
    status    = _infer_status(teaser + " " + timing)

    description = f"{teaser} | {timing} | {value}"

    return {
        "category":         category,
        "teaser":           teaser,
        "description":      description,
        "timing":           timing,
        "motivator":        motivator,
        "cuisine":          "Unknown",
        "value":            value,
        "status":           status,
        "notes":            f"llama ({OLLAMA_MODEL})",
        "model_confidence": 1.0,
        "all_predictions":  [],
        "source":           "llama",
    }
