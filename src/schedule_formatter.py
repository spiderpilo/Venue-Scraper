"""
Converts pipeline timing strings into the structured incentives schedule format
expected by the backend.

Types:
  recurring  — repeats on specific days/times each week
  always     — no time restriction (student discount, ongoing deal)
  date_range — bounded to a specific date window
"""

import re

# ISO weekday numbers: Mon=1 ... Sun=7
_DAY_NUMS = {
    "monday": 1, "mon": 1,
    "tuesday": 2, "tue": 2,
    "wednesday": 3, "wed": 3,
    "thursday": 4, "thu": 4,
    "friday": 5, "fri": 5,
    "saturday": 6, "sat": 6,
    "sunday": 7, "sun": 7,
}

_RANGE_RE = re.compile(
    r"\b(mon(?:day)?|tue(?:sday)?|wed(?:nesday)?|thu(?:rsday)?|fri(?:day)?|sat(?:urday)?|sun(?:day)?)"
    r"\s*(?:-|–|through|to)\s*"
    r"(mon(?:day)?|tue(?:sday)?|wed(?:nesday)?|thu(?:rsday)?|fri(?:day)?|sat(?:urday)?|sun(?:day)?)\b",
    re.IGNORECASE,
)

_TIME_RANGE_RE = re.compile(
    r"(\d{1,2}(?::\d{2})?\s*(?:am|pm))\s*(?:-|–|to)\s*(\d{1,2}(?::\d{2})?\s*(?:am|pm))",
    re.IGNORECASE,
)

_SINGLE_TIME_RE = re.compile(
    r"\b(\d{1,2}:\d{2}\s*(?:am|pm)?|\d{1,2}\s*(?:am|pm))\b",
    re.IGNORECASE,
)

_DATE_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def _day_num(abbr: str) -> int | None:
    abbr = abbr.lower().strip()
    for key, val in _DAY_NUMS.items():
        if abbr.startswith(key[:3]):
            return val
    return None


def _day_range(start: int, end: int) -> list[int]:
    if start <= end:
        return list(range(start, end + 1))
    # wrap-around e.g. Fri(5) – Mon(1)
    return list(range(start, 8)) + list(range(1, end + 1))


def parse_days(timing: str) -> list[int]:
    lower = timing.lower()

    if any(w in lower for w in ("daily", "every day", "each day", "all week", "7 days", "nightly", "every night")):
        return [1, 2, 3, 4, 5, 6, 7]
    if any(w in lower for w in ("weekdays", "weekday", "monday-friday", "mon-fri")):
        return [1, 2, 3, 4, 5]
    if "monday through friday" in lower or "monday - friday" in lower or "monday – friday" in lower:
        return [1, 2, 3, 4, 5]
    if any(w in lower for w in ("weekends", "weekend")):
        return [6, 7]

    # Explicit day range: "Wednesday-Sunday"
    m = _RANGE_RE.search(lower)
    if m:
        s = _day_num(m.group(1))
        e = _day_num(m.group(2))
        if s and e:
            return _day_range(s, e)

    # Individual day names (handles plurals like "Tuesdays")
    days = set()
    for name, num in _DAY_NUMS.items():
        if re.search(r"\b" + name + r"s?\b", lower):
            days.add(num)

    return sorted(days)


def _to_24h(t: str) -> str | None:
    t = t.strip()
    m = re.match(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", t, re.IGNORECASE)
    if not m:
        return None
    h, mi = int(m.group(1)), int(m.group(2) or 0)
    mer = (m.group(3) or "").lower()
    if mer == "pm" and h != 12:
        h += 12
    elif mer == "am" and h == 12:
        h = 0
    return f"{h:02d}:{mi:02d}:00" if 0 <= h <= 23 else None


def parse_periods(timing: str) -> list[dict]:
    periods = []

    # Time ranges first: "3pm-7pm", "3:00 PM to 6:00 PM"
    for m in _TIME_RANGE_RE.finditer(timing):
        start = _to_24h(m.group(1))
        end = _to_24h(m.group(2))
        if start:
            p = {"start": start}
            if end:
                p["end"] = end
            periods.append(p)

    if not periods:
        # Single time: "5pm", "before 4:00 PM"
        m = _SINGLE_TIME_RE.search(timing)
        if m:
            t = _to_24h(m.group(1))
            if t:
                # "before X" → treat as end time
                if re.search(r"\bbefore\b", timing[:m.start()], re.IGNORECASE):
                    periods.append({"end": t})
                else:
                    periods.append({"start": t})

    return periods


def _determine_type(timing: str, expiry: str) -> str:
    lower = timing.lower()

    # Explicit date range
    if expiry == "Limited Time" and _DATE_RE.search(timing):
        return "date_range"

    # No real timing info → always
    if not timing or timing.lower() in ("unknown", ""):
        return "always"

    # Has real day or time info → recurring
    if parse_days(timing) or parse_periods(timing):
        return "recurring"

    # Named period words without a parseable time
    if any(w in lower for w in (
        "happy hour", "daily", "weekly", "nightly", "every", "each",
        "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
        "weekday", "weekend", "lunch", "dinner", "brunch",
    )):
        return "recurring"

    return "always"


def build_incentives(record: dict) -> list[dict]:
    """
    Returns the 'incentives' array to be appended to a venue record.
    Returns [] for No Incentive venues.
    """
    category = record.get("Incentive Category", "")
    if not category or category in ("No Incentive", "Unknown"):
        return []

    timing  = record.get("Days / Timing Restrictions", "")
    expiry  = record.get("Expiration / Ongoing", "Unknown")
    desc    = record.get("Full Incentive Description", "")

    inc_type = _determine_type(timing or "", expiry)

    entry = {
        "id":          _slug(category),
        "title":       category,
        "description": desc,
        "type":        inc_type,
        "priority":    None,
    }

    if inc_type == "recurring" and timing:
        schedule = {}
        days    = parse_days(timing)
        periods = parse_periods(timing)
        if days:
            schedule["days"] = days
        if periods:
            schedule["periods"] = periods
        if schedule:
            schedule["timezone"] = "America/Los_Angeles"
            entry["schedule"] = schedule

    elif inc_type == "date_range":
        dates = _DATE_RE.findall(timing)
        if len(dates) >= 2:
            entry["schedule"] = {"start_date": dates[0], "end_date": dates[1]}
        elif len(dates) == 1:
            entry["schedule"] = {"start_date": dates[0], "end_date": dates[0]}

    return [entry]
