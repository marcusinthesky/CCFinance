"""Parse first-publication evidence from supported captured publisher bodies."""

import re
from datetime import datetime, time
from zoneinfo import ZoneInfo

PARSER_VERSION = "publisher-first-published-v1"
INDIA = ZoneInfo("Asia/Kolkata")
NEW_YORK = ZoneInfo("America/New_York")
PUBLISHERS = {
    "business-standard.com": (
        re.compile(
            r"First Published:\s*([a-z]{3} \d{1,2} 20\d{2}\s*\|\s*"
            r"\d{1,2}:\d{2} [AP]M) IST",
            re.I,
        ),
        "%b %d %Y | %I:%M %p",
    ),
    "lifestyle.livemint.com": (
        re.compile(
            r"First Published\s*(\d{2}\.\d{2}\.20\d{2}\s*\|\s*\d{1,2}:\d{2} [AP]M) IST",
            re.I,
        ),
        "%d.%m.%Y | %I:%M %p",
    ),
}


def first_publication(host: str, body: str) -> tuple[str, datetime | None]:
    """Return the verbatim first-publication match and its timezone-aware instant."""
    if host not in PUBLISHERS:
        return "", None
    pattern, date_format = PUBLISHERS[host]
    match = pattern.search(body)
    if match is None:
        return "", None
    try:
        value = datetime.strptime(re.sub(r"\s*\|\s*", " | ", match[1]), date_format)
    except ValueError:
        return match[0], None
    return match[0], value.replace(tzinfo=INDIA)


def overnight_status(
    publication: datetime, capture: datetime, previous_close: datetime, cutoff: datetime
) -> str:
    """Classify timing against the preceding exchange close and 09:00 cutoff."""
    if capture < publication:
        return "capture_before_publication"
    if not previous_close < publication < cutoff:
        return "outside_overnight"
    if capture > cutoff:
        return "capture_after_cutoff"
    return "eligible"


def cutoff_time() -> time:
    """Return the New York morning deadline for overnight classification."""
    return time(9)
