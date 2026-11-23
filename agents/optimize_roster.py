"""Node 2 · optimize_roster: workers and training currency from Workday and the learning system, demand from node 1,
one roster from NVIDIA cuOpt. Retry 2, max_iter 4."""
from __future__ import annotations

from .mcp_client import data, tools_named

MAX_RETRIES = 2  # 3 attempts in all
MAX_ITER = 4  # solver passes per attempt before giving up on an answer


async def optimize_roster(state: dict) -> dict:
    tools = await tools_named("workday.workers", "lms.training_currency", "cuopt.solve")
    workers = data(await tools["workers"].ainvoke({}))["workers"]
    current = [q for q in data(await tools["training_currency"].ainvoke({}))["qualifications"]
               if q["status"] == "CURRENT"]
    sites = set(state.get("sites", []))
    # Deliberate weakness W2 (see README): one solve for every site at once, so the optimizer waits until the
    # forecast for all 14 sites is in. One slow site holds up every site. Leave it as it is.
    payload = {"demand": state.get("demand", {}), "workers": workers, "training": current,
               "round": state.get("rounds", 0) + 1}
    for attempt in range(MAX_RETRIES + 1):
        try:
            for _ in range(MAX_ITER):
                result = data(await tools["solve"].ainvoke({"payload": payload}))
                if result.get("status") == "OK":
                    # the solver answers for every site it knows; keep the sites of this run (one, or all 14)
                    return {"roster": [r for r in result.get("roster", []) if r.get("site_id") in sites],
                            "solver_status": "OK",
                            "hours": {w["worker_id"]: w["contract_hours"] for w in workers}}
            return {"roster": [], "solver_status": f"no answer after max_iter ({result.get('status')})"}
        except Exception:
            if attempt == MAX_RETRIES:
                raise
    return {"roster": [], "solver_status": "failed"}
