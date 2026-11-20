"""Shared pieces of the six stand-in systems: canned answers from data/, and a health route.

Nothing here talks to a real system. Every answer is hard-coded JSON, the same on every call, with no delay.
"""
from __future__ import annotations

import json
from functools import cache
from pathlib import Path

from fastapi import FastAPI

DATA = Path(__file__).resolve().parent.parent / "data"


@cache
def load(name: str):
    """One canned answer, read once from data/<name>.json."""
    return json.loads((DATA / f"{name}.json").read_text())


def add_health(app: FastAPI) -> FastAPI:
    @app.get("/healthz")
    def healthz() -> dict:
        return {"ok": True, "service": app.title}
    return app
