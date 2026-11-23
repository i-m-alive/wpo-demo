"""stub-cuopt: stands in for NVIDIA cuOpt. Solve (read: it computes a roster and changes nothing).

CUOPT_MODE=infeasible: HTTP 200 with status INFEASIBLE and no roster. A solver refusing is not an HTTP error.
solver_time_ms is only a field of the canned answer: the stand-in never waits."""
from fastapi import FastAPI

from stubs._common import add_health, mode
from stubs.stub_responses import SOLVE_INFEASIBLE, SOLVE_OK

app = add_health(FastAPI(title="stub-cuopt", docs_url=None, redoc_url=None))
mode("CUOPT_MODE", "infeasible")  # a bad setting stops the stand-in at start-up


@app.post("/solve")
def solve(body: dict) -> dict:
    return SOLVE_INFEASIBLE if mode("CUOPT_MODE", "infeasible") == "infeasible" else SOLVE_OK
