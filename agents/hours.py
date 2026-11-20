"""Business hours for the manager copilot. COPILOT_HOURS="07:00-19:00" (the default) in COPILOT_TZ (default
Europe/London); "00:00-24:00" means always open, which the Compose file sets so a demo works at any hour."""
from __future__ import annotations

import os
import re
from datetime import datetime, time
from zoneinfo import ZoneInfo

SPEC = re.compile(r"^([01]\d|2[0-4]):([0-5]\d)-([01]\d|2[0-4]):([0-5]\d)$")


def window() -> tuple[time | None, time | None, str, str]:
    spec = os.getenv("COPILOT_HOURS", "07:00-19:00").strip()
    tz = os.getenv("COPILOT_TZ", "Europe/London")
    m = SPEC.match(spec)
    if not m:
        raise ValueError(f"COPILOT_HOURS must look like 07:00-19:00, not {spec!r}")
    start, end = (int(m.group(1)), int(m.group(2))), (int(m.group(3)), int(m.group(4)))
    if start == (0, 0) and end == (24, 0):
        return None, None, spec, tz
    return time(*start), time(min(end[0], 23), end[1] if end[0] < 24 else 59), spec, tz


def is_open(now: datetime | None = None) -> bool:
    start, end, _, tz = window()
    if start is None:
        return True
    local = (now or datetime.now(ZoneInfo(tz))).astimezone(ZoneInfo(tz)).time()
    return start <= local < end if start <= end else (local >= start or local < end)


def describe() -> str:
    _, _, spec, tz = window()
    a, b = spec.split("-")
    return "always" if spec == "00:00-24:00" else f"between {a} and {b} ({tz})"
