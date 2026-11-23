"""stub-sap: stands in for SAP S/4. Production plan (read) and shift confirmation (write)."""
from fastapi import FastAPI

from stubs._common import add_health
from stubs.stub_responses import PRODUCTION_PLAN, SHIFT_CONFIRM_OK

app = add_health(FastAPI(title="stub-sap", docs_url=None, redoc_url=None))


@app.get("/production_plan")
def production_plan() -> dict:
    """Tonight's plan for the 14 sites: line, shift, planned units and the headcount each needs."""
    return PRODUCTION_PLAN


@app.post("/shift_confirm")
def shift_confirm(body: dict) -> dict:
    return SHIFT_CONFIRM_OK
