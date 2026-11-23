"""The nine stand-ins answer exactly as stubs/stub_responses.py says, the same on every call; their failure modes
answer as it says too; and the canned answers hang together where the agents rely on it."""
import importlib
import pathlib

import pytest
from fastapi.testclient import TestClient

from stubs import stub_responses as R
from stubs._common import mode

STUBS = ["sap", "workday", "mes", "lms", "cuopt", "teams", "policy", "roster_store", "llm"]


def client(name: str) -> TestClient:
    return TestClient(importlib.import_module(f"stubs.stub_{name}").app)


@pytest.mark.parametrize("name", STUBS)
def test_health(name):
    r = client(name).get("/healthz")
    assert r.status_code == 200 and r.json() == {"ok": True, "service": f"stub-{name.replace('_', '-')}"}


READS = [  # stand-in, path, canned answer
    ("sap", "/production_plan", R.PRODUCTION_PLAN),
    ("workday", "/absences", R.ABSENCES),
    ("workday", "/workers", R.WORKERS),
    ("mes", "/line_availability", R.LINE_AVAILABILITY),
    ("lms", "/training_currency", R.TRAINING_CURRENCY),
    ("policy", "/rules", R.POLICY_RULES),
    ("roster_store", "/roster", R.ROSTER_STORE_GET),
]


@pytest.mark.parametrize("name,path,canned", READS, ids=[f"{r[0]}{r[1]}" for r in READS])
def test_reads_answer_the_canned_response(name, path, canned):
    c = client(name)
    first = c.get(path)
    assert first.status_code == 200 and first.json() == canned
    assert c.get(path).json() == first.json()  # the same on every call


WRITES = [  # stand-in, path, status, canned answer
    ("sap", "/shift_confirm", 200, R.SHIFT_CONFIRM_OK),
    ("workday", "/schedules", 200, R.SCHEDULES_OK),
    ("cuopt", "/solve", 200, R.SOLVE_OK),
    ("teams", "/notify", 202, R.NOTIFY_ACCEPTED),
    ("roster_store", "/roster", 200, R.ROSTER_STORE_OK),
    ("llm", "/chat/completions", 200, R.CHAT_COMPLETION),
    ("llm", "/openai/deployments/gpt-4o-mini/chat/completions?api-version=2024-10-21", 200, R.CHAT_COMPLETION),
]


@pytest.mark.parametrize("name,path,status,canned", WRITES, ids=[f"{w[0]}{w[1].split('?')[0]}" for w in WRITES])
def test_posts_answer_the_canned_response(name, path, status, canned):
    c = client(name)
    for payload in ({}, {"anything": [1, 2]}):
        r = c.post(path, json=payload)
        assert r.status_code == status and r.json() == canned
    assert c.post(path, json=[1, 2]).status_code == 422  # a JSON object is expected


def test_the_production_plan_is_14_sites():
    sites = client("sap").get("/production_plan").json()["sites"]
    assert [s["site_id"] for s in sites] == [f"S{i:02d}" for i in range(1, 15)]


# ------------------------------------------------------------------------------------------------ failure modes

@pytest.mark.parametrize("path,method", [("/absences", "get"), ("/workers", "get"), ("/schedules", "post")])
@pytest.mark.parametrize("wait", ["30", "60", "120"])
def test_workday_throttle_is_a_429_with_retry_after_on_every_route(monkeypatch, path, method, wait):
    monkeypatch.setenv("WORKDAY_MODE", "throttle")
    monkeypatch.setenv("WORKDAY_RETRY_AFTER", wait)
    c = client("workday")
    r = c.get(path) if method == "get" else c.post(path, json={})
    assert r.status_code == 429 and r.headers["retry-after"] == wait and r.json() == R.THROTTLED


def test_workday_throttle_waits_60_s_by_default(monkeypatch):
    monkeypatch.setenv("WORKDAY_MODE", "throttle")
    monkeypatch.delenv("WORKDAY_RETRY_AFTER", raising=False)
    assert client("workday").get("/absences").headers["retry-after"] == "60"


@pytest.mark.parametrize("name,variable,value,path,method,canned", [
    ("mes", "MES_MODE", "empty", "/line_availability", "get", R.LINE_AVAILABILITY_EMPTY),
    ("lms", "LMS_MODE", "empty", "/training_currency", "get", R.TRAINING_CURRENCY_EMPTY),
    ("policy", "POLICY_MODE", "empty", "/rules", "get", R.POLICY_RULES_EMPTY),
    ("cuopt", "CUOPT_MODE", "infeasible", "/solve", "post", R.SOLVE_INFEASIBLE),
])
def test_empty_and_infeasible_modes_are_http_200(monkeypatch, name, variable, value, path, method, canned):
    monkeypatch.setenv(variable, value)
    c = client(name)
    r = c.get(path) if method == "get" else c.post(path, json={})
    assert r.status_code == 200 and r.json() == canned  # a result, not an error
    monkeypatch.setenv(variable, "normal")
    r = c.get(path) if method == "get" else c.post(path, json={})
    assert r.json() != canned  # switched back


@pytest.mark.parametrize("variable,value", [("WORKDAY_MODE", "empty"), ("MES_MODE", "throttle"), ("CUOPT_MODE", "slow")])
def test_an_unknown_mode_is_refused(monkeypatch, variable, value):
    monkeypatch.setenv(variable, value)
    allowed = {"WORKDAY_MODE": ("throttle",), "MES_MODE": ("empty",), "CUOPT_MODE": ("infeasible",)}[variable]
    with pytest.raises(ValueError, match=variable):
        mode(variable, *allowed)


def test_a_bad_retry_after_is_refused(monkeypatch):
    from stubs.stub_workday import retry_after
    monkeypatch.setenv("WORKDAY_RETRY_AFTER", "45")
    with pytest.raises(ValueError, match="30, 60, 120"):
        retry_after()


# ------------------------------------------------------------------------------------------- the canned answers

def test_the_canned_answers_hang_together():
    """Where the agents join one system's answer to another's, the ids match."""
    plan = {s["site_id"]: s["line_id"] for s in R.PRODUCTION_PLAN["sites"]}
    assert len(plan) == 14
    assert {x["line_id"] for x in R.LINE_AVAILABILITY["lines"]} == set(plan.values())
    assert {(r["site_id"], r["line_id"]) for r in R.SOLVE_OK["roster"]} == set(plan.items())
    assert {(r["site_id"], r["line_id"]) for r in R.ROSTER_STORE_GET["sites"]} == set(plan.items())
    workers = {w["worker_id"] for w in R.WORKERS["workers"]}
    assert {q["worker_id"] for q in R.TRAINING_CURRENCY["qualifications"]} == workers
    assert {a["worker_id"] for a in R.ABSENCES["absences"]} <= workers
    assert {w for r in R.SOLVE_OK["roster"] for w in r["assigned"]} <= workers
    assert [r["type"] for r in R.POLICY_RULES["rules"]] == ["MAX_CONSECUTIVE_DAYS", "MIN_REST_HOURS",
                                                          "MAX_HOURS_PER_WEEK", "SKILL_REQUIRED"]


def test_stubs_call_nothing_else():
    for f in pathlib.Path("stubs").glob("*.py"):
        text = f.read_text()
        assert "httpx" not in text and "requests" not in text, f.name
