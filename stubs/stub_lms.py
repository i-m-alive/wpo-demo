"""stub-lms: stands in for the learning system. Training currency (read).

LMS_MODE=empty: HTTP 200 with no qualifications at all (an empty result, not an error)."""
from fastapi import FastAPI

from stubs._common import add_health, mode
from stubs.stub_responses import TRAINING_CURRENCY, TRAINING_CURRENCY_EMPTY

app = add_health(FastAPI(title="stub-lms", docs_url=None, redoc_url=None))
mode("LMS_MODE", "empty")  # a bad setting stops the stand-in at start-up


@app.get("/training_currency")
def training_currency() -> dict:
    """Each worker's qualifications and whether they are current."""
    return TRAINING_CURRENCY_EMPTY if mode("LMS_MODE", "empty") == "empty" else TRAINING_CURRENCY
