"""stub-sap: stands in for SAP S/4. Production plan (read) and shift confirmation (write)."""
from fastapi import FastAPI

from stubs._common import add_health, load

app = add_health(FastAPI(title="stub-sap", docs_url=None, redoc_url=None))


@app.get("/production_plan")
def production_plan() -> list[str]:
    """The 14 site ids planned for production."""
    return load("sites")


@app.post("/shift_confirm")
def shift_confirm(body: dict) -> dict:
    return {"status": "ok"}
