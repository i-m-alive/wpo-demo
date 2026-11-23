"""Shared pieces of the stand-in systems: a health route, and the failure mode a stand-in runs in.

Nothing here talks to a real system. Every answer is a hard-coded constant from stubs/stub_responses.py, the same on
every call, with no delay.

Failure modes. A stand-in that has one reads it from its own variable (WORKDAY_MODE, MES_MODE, LMS_MODE, CUOPT_MODE,
POLICY_MODE): "normal" (the default) or the stand-in's failure mode. Compose sets the variable, so a mode is switched by
recreating that one container (`make mode SYSTEM=workday MODE=throttle`). A value the stand-in does not know stops it
at start-up instead of letting it answer normally by mistake.
"""
from __future__ import annotations

import os

from fastapi import FastAPI

NORMAL = "normal"


def add_health(app: FastAPI) -> FastAPI:
    @app.get("/healthz")
    def healthz() -> dict:
        return {"ok": True, "service": app.title}
    return app


def mode(variable: str, *failure_modes: str) -> str:
    """The mode this stand-in runs in: "normal" or one of its failure modes. Raises ValueError for anything else."""
    value = os.getenv(variable, NORMAL).strip().lower() or NORMAL
    allowed = (NORMAL, *failure_modes)
    if value not in allowed:
        raise ValueError(f"{variable} must be one of {', '.join(allowed)}, not {value!r}")
    return value
