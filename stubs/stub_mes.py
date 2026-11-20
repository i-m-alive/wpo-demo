"""stub-mes: stands in for the manufacturing execution system. Line availability (read)."""
from fastapi import FastAPI

from stubs._common import add_health, load

app = add_health(FastAPI(title="stub-mes", docs_url=None, redoc_url=None))


@app.get("/line_availability")
def line_availability() -> list[dict]:
    """Lines running, and planned maintenance."""
    return load("line_availability")
