"""stub-policy: stands in for the roster policy service: working-time, rest and skill rules (read).

POLICY_MODE=empty: HTTP 200 with no rules at all (an empty result, not an error)."""
from fastapi import FastAPI

from stubs._common import add_health, mode
from stubs.stub_responses import POLICY_RULES, POLICY_RULES_EMPTY

app = add_health(FastAPI(title="stub-policy", docs_url=None, redoc_url=None))
mode("POLICY_MODE", "empty")  # a bad setting stops the stand-in at start-up


@app.get("/rules")
def rules() -> dict:
    """The rules every roster must keep."""
    return POLICY_RULES_EMPTY if mode("POLICY_MODE", "empty") == "empty" else POLICY_RULES
