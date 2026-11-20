"""The agents service's routes, with the offline model and fake tools."""
import pytest
from fastapi.testclient import TestClient

from agents.main import app

from .fakes import canned, patch_tools


@pytest.fixture
def api(monkeypatch):
    patch_tools(monkeypatch, canned())
    return TestClient(app)


def test_health(api):
    assert api.get("/healthz").json() == {"ok": True, "service": "wpo-agents"}


def test_roster_for_all_sites_and_one(api):
    r = api.post("/roster/run", json={})
    body = r.json()
    assert r.status_code == 200 and body["sites"] == 14 and body["published"] and body["rounds"] == 1
    assert body["forecast"].startswith("Demand site-01:")
    one = api.post("/roster/run", json={"site": "site-07"}).json()
    assert one["sites"] == 1 and one["published"]
    assert api.post("/roster/run", json={"site": "berlin"}).status_code == 422


def test_copilot_open_and_closed(api, monkeypatch):
    monkeypatch.setenv("COPILOT_HOURS", "00:00-24:00")
    r = api.post("/copilot/ask", json={"question": "Who is on shift at site-02?"})
    assert r.status_code == 200 and r.json()["site"] == "site-02"
    from datetime import datetime
    from zoneinfo import ZoneInfo
    h = datetime.now(ZoneInfo("Europe/London")).hour
    monkeypatch.setenv("COPILOT_HOURS", f"{(h + 2) % 24:02d}:00-{(h + 3) % 24:02d}:00")  # a window that is not now
    r = api.post("/copilot/ask", json={"question": "Who is on shift?"})
    assert r.status_code == 423 and "The copilot answers between" in r.json()["detail"]["message"]
    assert api.post("/copilot/ask", json={"question": "x"}).status_code == 422
