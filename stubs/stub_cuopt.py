"""stub-cuopt: stands in for NVIDIA cuOpt. Solve (read: it computes a roster and changes nothing)."""
from fastapi import FastAPI

from stubs._common import add_health

app = add_health(FastAPI(title="stub-cuopt", docs_url=None, redoc_url=None))


@app.post("/solve")
def solve(body: dict) -> dict:
    return {"status": "OK", "roster": {}}
