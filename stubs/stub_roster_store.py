"""stub-roster-store: stands in for the roster store: the last published roster (read) and a roster to store (write).

No agent writes to it today (the brief's writeback publishes to Workday, SAP and Teams); POST /roster answers as the
canned list says, for a later variant."""
from fastapi import FastAPI

from stubs._common import add_health
from stubs.stub_responses import ROSTER_STORE_GET, ROSTER_STORE_OK

app = add_health(FastAPI(title="stub-roster-store", docs_url=None, redoc_url=None))


@app.get("/roster")
def roster() -> dict:
    """The last published roster, for every site."""
    return ROSTER_STORE_GET


@app.post("/roster")
def store(body: dict) -> dict:
    return ROSTER_STORE_OK
