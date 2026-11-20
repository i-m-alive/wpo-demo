"""Business hours for the manager copilot. COPILOT_HOURS="07:00-19:00" (the default) in COPILOT_TZ (default
Europe/London); "00:00-24:00" means always open, which the Compose file sets so a demo works at any hour.

A window may cross midnight ("22:00-06:00"). 24:00 is allowed only as an end time (end of the day).
"""
from __future__ import annotations

import os
import re
from datetime import datetime
from zoneinfo import ZoneInfo

SPEC = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)-(?:([01]\d|2[0-3]):([0-5]\d)|(24):(00))$")
DAY = 24 * 60


def window() -> tuple[int, int, str, str]:
    """(start, end) in minutes since midnight, the spec as written, and the time zone. Raises ValueError for a bad
    setting, e.g. "24:00-06:00" or "07:00-24:30"."""
    spec = os.getenv("COPILOT_HOURS", "07:00-19:00").strip()
    tz = os.getenv("COPILOT_TZ", "Europe/London")
    m = SPEC.match(spec)
    if not m:
        raise ValueError(f"COPILOT_HOURS must look like 07:00-19:00 (24:00 only as an end time), not {spec!r}")
    ZoneInfo(tz)  # an unknown time zone raises here
    start = int(m.group(1)) * 60 + int(m.group(2))
    end = DAY if m.group(5) else int(m.group(3)) * 60 + int(m.group(4))
    return start, end, spec, tz


def is_open(now: datetime | None = None) -> bool:
    start, end, _, tz = window()
    if start == 0 and end == DAY:
        return True
    local = (now or datetime.now(ZoneInfo(tz))).astimezone(ZoneInfo(tz))
    minute = local.hour * 60 + local.minute
    return start <= minute < end if start < end else (minute >= start or minute < end)


def describe() -> str:
    start, end, spec, tz = window()
    if start == 0 and end == DAY:
        return "always"
    a, b = spec.split("-")
    return f"between {a} and {b} ({tz})"
