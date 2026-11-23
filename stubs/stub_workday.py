"""stub-workday: stands in for Workday. Absences and workers (read), schedules (write).

WORKDAY_MODE=throttle: every route answers HTTP 429 with the THROTTLED body and a Retry-After header of
WORKDAY_RETRY_AFTER seconds (30, 60 or 120; default 60), the way a Workday tenant answers once its request limit is hit.
"""
import os

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from stubs._common import add_health, mode
from stubs.stub_responses import ABSENCES, SCHEDULES_OK, THROTTLED, WORKERS

app = add_health(FastAPI(title="stub-workday", docs_url=None, redoc_url=None))
RETRY_AFTER_CHOICES = ("30", "60", "120")


def retry_after() -> str:
    value = os.getenv("WORKDAY_RETRY_AFTER", "60").strip()
    if value not in RETRY_AFTER_CHOICES:
        raise ValueError(f"WORKDAY_RETRY_AFTER must be one of {', '.join(RETRY_AFTER_CHOICES)}, not {value!r}")
    return value


def throttled() -> JSONResponse | None:
    """The tenant-wide throttle, when it is on: HTTP 429 with Retry-After."""
    if mode("WORKDAY_MODE", "throttle") == "throttle":
        return JSONResponse(THROTTLED, status_code=429, headers={"Retry-After": retry_after()})
    return None


mode("WORKDAY_MODE", "throttle")  # a bad setting stops the stand-in at start-up
retry_after()


@app.get("/absences", response_model=None)
def absences() -> dict | JSONResponse:
    """Approved leave and sickness."""
    return throttled() or ABSENCES


@app.get("/workers", response_model=None)
def workers() -> dict | JSONResponse:
    """Every worker: site, contract hours and skills."""
    return throttled() or WORKERS


@app.post("/schedules", response_model=None)
def schedules(body: dict) -> dict | JSONResponse:
    return throttled() or SCHEDULES_OK
