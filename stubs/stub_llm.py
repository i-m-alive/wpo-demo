"""stub-llm: stands in for Azure OpenAI, no API key needed. Every chat completion gets the same canned answer.

The Azure OpenAI client the agents use posts to /openai/deployments/<deployment>/chat/completions?api-version=...;
a plain OpenAI client posts to /chat/completions. Both are answered the same way."""
from fastapi import FastAPI

from stubs._common import add_health
from stubs.stub_responses import CHAT_COMPLETION

app = add_health(FastAPI(title="stub-llm", docs_url=None, redoc_url=None))


@app.post("/chat/completions")
def chat_completions(body: dict) -> dict:
    return CHAT_COMPLETION


@app.post("/openai/deployments/{deployment}/chat/completions")
def azure_chat_completions(deployment: str, body: dict) -> dict:
    return CHAT_COMPLETION
