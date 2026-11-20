"""stub-workday: stands in for Workday. Absences and workers (read), schedules (write)."""
from fastapi import FastAPI

from stubs._common import add_health, load

app = add_health(FastAPI(title="stub-workday", docs_url=None, redoc_url=None))


@app.get("/absences")
def absences() -> list[dict]:
    """Approved leave and sickness."""
    return load("absences")


@app.get("/workers")
def workers() -> list[dict]:
    """Contracts, hours, lines and site of every worker."""
    return load("workers")


@app.post("/schedules")
def schedules(body: dict) -> dict:
    return {"status": "ok"}
