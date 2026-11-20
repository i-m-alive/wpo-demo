"""The agents service: the nightly roster (the supervisor graph) and the manager copilot (its own graph)."""
from __future__ import annotations

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from .hours import describe, is_open
from .manager_copilot import copilot
from .supervisor import supervisor

app = FastAPI(title="wpo-agents", docs_url=None, redoc_url=None)


class RunIn(BaseModel):
    site: str | None = Field(None, pattern=r"^site-\d{2}$", description="One site, or none for all 14")


class AskIn(BaseModel):
    question: str = Field("Who is on shift tomorrow at site-01?", min_length=3, max_length=500)


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True, "service": "wpo-agents"}


@app.post("/roster/run")
async def run_roster(body: RunIn) -> dict:
    """The nightly roster: forecast, optimize, check, write back. One site, or all 14."""
    out = await supervisor.ainvoke({"only_site": body.site} if body.site else {})
    return {"sites": len(out.get("sites", [])), "published": bool(out.get("published")),
            "compliant": bool(out.get("compliant")), "rounds": out.get("rounds", 0), "breaches": out.get("breaches", []),
            "solver_status": out.get("solver_status", ""), "forecast": out.get("forecast_note", "")}


@app.post("/copilot/ask")
async def ask(body: AskIn) -> dict:
    """The manager copilot, in business hours."""
    if not is_open():
        raise HTTPException(423, {"error": "closed", "message": f"The copilot answers {describe()}."})
    out = await copilot.ainvoke({"question": body.question})
    return {"site": out.get("site"), "answer": out.get("answer")}
