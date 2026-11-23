"""stub-teams: stands in for Microsoft Teams. Notify (write): HTTP 202, the message is accepted for delivery."""
from fastapi import FastAPI

from stubs._common import add_health
from stubs.stub_responses import NOTIFY_ACCEPTED

app = add_health(FastAPI(title="stub-teams", docs_url=None, redoc_url=None))


@app.post("/notify", status_code=202)
def notify(body: dict) -> dict:
    return NOTIFY_ACCEPTED
