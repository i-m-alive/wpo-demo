"""The chat model the forecast and copilot agents use: Azure OpenAI.

WPO_LLM=auto (the default) uses Azure OpenAI when AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_API_KEY are both set, and an
offline stand-in with a fixed answer when they are not. WPO_LLM=offline always uses the offline stand-in; WPO_LLM=azure
insists on Azure OpenAI. Both are called the same way.
Docker Compose points the endpoint at the LLM stand-in service (no key needed), so in every Compose run the agents'
model calls are real HTTP calls that a fault can be injected into, and nothing leaves the machine. A real Azure OpenAI
deployment is used only when .env sets its endpoint and key.

The model checks, it does not write: each agent hands it its own draft and asks for {"ok": true} or {"ok": false},
which is also the LLM stand-in's canned answer. The agent's answer is the draft; `verdict` reads the model's check.
"""
from __future__ import annotations

import json
import os

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_openai import AzureChatOpenAI

CHECK = 'Answer only with the JSON {"ok": true} if it holds up, or {"ok": false} if it does not.'


class OfflineAnswers(BaseChatModel):
    """The same answer every time, as the LLM stand-in gives: {"ok": true}. Deterministic, so every run repeats."""

    @property
    def _llm_type(self) -> str:
        return "offline-fixed-answers"

    def _generate(self, messages: list[BaseMessage], stop=None, run_manager=None, **kwargs) -> ChatResult:
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content='{"ok": true}'))])


def chat_model() -> BaseChatModel:
    mode = os.getenv("WPO_LLM", "auto")
    configured = bool(os.getenv("AZURE_OPENAI_ENDPOINT") and os.getenv("AZURE_OPENAI_API_KEY"))
    if mode == "azure" and not configured:
        raise RuntimeError("WPO_LLM=azure needs AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_API_KEY")
    if mode == "azure" or (mode == "auto" and configured):
        # max_retries=0: the OpenAI client would otherwise retry twice by itself and honour Retry-After, hiding the
        # forecast agent's own retry behaviour (W1) that the demo is about.
        return AzureChatOpenAI(azure_deployment=os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o-mini"),
                               api_version="2024-10-21", max_retries=0)
    return OfflineAnswers()


def verdict(content) -> bool | None:
    """The model's check, {"ok": true|false}, as True or False; None when it answered anything else."""
    try:
        value = json.loads(content)
    except (TypeError, ValueError):
        return None
    ok = value.get("ok") if isinstance(value, dict) else None
    return ok if isinstance(ok, bool) else None


llm = chat_model()
