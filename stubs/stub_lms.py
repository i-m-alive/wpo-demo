"""stub-lms: stands in for the learning system. Training currency (read)."""
from fastapi import FastAPI

from stubs._common import add_health, load

app = add_health(FastAPI(title="stub-lms", docs_url=None, redoc_url=None))


@app.get("/training_currency")
def training_currency() -> list[dict]:
    """Who is qualified for which line today."""
    return load("training_currency")
