"""The six stand-in systems answer exactly as the brief says, the same on every call, and their data hangs together."""
import importlib

import pytest
from fastapi.testclient import TestClient

from stubs._common import load

STUBS = ["sap", "workday", "mes", "lms", "cuopt", "teams"]


def client(name: str) -> TestClient:
    return TestClient(importlib.import_module(f"stubs.stub_{name}").app)


@pytest.mark.parametrize("name", STUBS)
def test_health(name):
    r = client(name).get("/healthz")
    assert r.status_code == 200 and r.json() == {"ok": True, "service": f"stub-{name}"}


@pytest.mark.parametrize("name,path,body", [
    ("sap", "/shift_confirm", {"status": "ok"}),
    ("workday", "/schedules", {"status": "ok"}),
    ("cuopt", "/solve", {"status": "OK", "roster": {}}),
    ("teams", "/notify", {"status": "ok"}),
])
def test_writes_answer_exactly_as_the_brief(name, path, body):
    c = client(name)
    for payload in ({}, {"anything": [1, 2]}):
        r = c.post(path, json=payload)
        assert r.status_code == 200 and r.json() == body
    assert c.post(path, json=[1, 2]).status_code == 422  # a JSON object is expected


@pytest.mark.parametrize("name,path,size", [
    ("sap", "/production_plan", 14), ("workday", "/absences", 12), ("workday", "/workers", 56),
    ("mes", "/line_availability", 28), ("lms", "/training_currency", 84),
])
def test_reads_return_the_canned_lists(name, path, size):
    c = client(name)
    first = c.get(path)
    assert first.status_code == 200 and len(first.json()) == size
    assert c.get(path).json() == first.json()  # the same on every call


def test_production_plan_is_14_site_ids():
    sites = client("sap").get("/production_plan").json()
    assert sites == [f"site-{i:02d}" for i in range(1, 15)]


def test_the_data_hangs_together():
    sites = set(load("sites"))
    workers = {w["id"]: w for w in load("workers")}
    assert {w["site"] for w in workers.values()} == sites and len(workers) == 56
    for a in load("absences"):
        assert a["worker_id"] in workers and workers[a["worker_id"]]["site"] == a["site"]
    assert {(r["site"], r["line"]) for r in load("line_availability")} == {(s, l) for s in sites for l in ("line-A", "line-B")}
    for t in load("training_currency"):
        assert t["line"] in workers[t["worker_id"]]["lines"]
    assert sum(not t["current"] for t in load("training_currency")) == 5
    assert {r["site"] for r in load("roster_published")} == sites
    assert [r["id"] for r in load("policy_rules")] == ["max_weekly_hours", "rest_between_shifts", "one_shift_per_day",
                                                       "current_training"]


def test_stubs_call_nothing_else():
    import pathlib
    for f in pathlib.Path("stubs").glob("*.py"):
        text = f.read_text()
        assert "httpx" not in text and "requests" not in text, f.name
