"""The agents service: the nightly roster (the supervisor graph) and the manager copilot (its own graph)."""
from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from langchain_core.tools import ToolException
from pydantic import BaseModel, Field

from .hours import describe, is_open, window
from .manager_copilot import copilot
from .supervisor import supervisor

window()  # a bad COPILOT_HOURS or COPILOT_TZ stops the service at start-up, not on the first question
app = FastAPI(title="wpo-agents", docs_url=None, redoc_url=None)


class RunIn(BaseModel):
    site: str | None = Field(None, pattern=r"^site-\d{2}$", description="One site, or none for all 14")


class AskIn(BaseModel):
    question: str = Field("Who is on shift tomorrow at site-01?", min_length=3, max_length=500)


@app.exception_handler(ToolException)
async def system_failed(request: Request, exc: ToolException) -> JSONResponse:
    """A system the agents need failed in a way they do not retry (e.g. Teams refused a notification): say which."""
    return JSONResponse(status_code=502, content={"detail": {"error": "system_failed", "message": str(exc)}})


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True, "service": "wpo-agents"}


@app.post("/roster/run")
async def run_roster(body: RunIn) -> dict:
    """The nightly roster: forecast, optimize, check, write back. One site, or all 14."""
    out = await supervisor.ainvoke({"only_site": body.site} if body.site else {})
    if body.site and not out.get("sites"):
        raise HTTPException(404, {"error": "unknown_site", "message": f"{body.site} is not in the production plan."})
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
