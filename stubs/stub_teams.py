"""stub-teams: stands in for Microsoft Teams. Notify (write)."""
from fastapi import FastAPI

from stubs._common import add_health

app = add_health(FastAPI(title="stub-teams", docs_url=None, redoc_url=None))


@app.post("/notify")
def notify(body: dict) -> dict:
    return {"status": "ok"}
