"""stub-mes: stands in for the manufacturing execution system. Line availability (read).

MES_MODE=empty: HTTP 200 with no lines at all (an empty result, not an error)."""
from fastapi import FastAPI

from stubs._common import add_health, mode
from stubs.stub_responses import LINE_AVAILABILITY, LINE_AVAILABILITY_EMPTY

app = add_health(FastAPI(title="stub-mes", docs_url=None, redoc_url=None))
mode("MES_MODE", "empty")  # a bad setting stops the stand-in at start-up


@app.get("/line_availability")
def line_availability() -> dict:
    """Which lines are running, and any maintenance window."""
    return LINE_AVAILABILITY_EMPTY if mode("MES_MODE", "empty") == "empty" else LINE_AVAILABILITY
