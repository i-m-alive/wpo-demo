"""The chat model the forecast and copilot agents use: Azure OpenAI.

WPO_LLM=auto (the default) uses Azure OpenAI when AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_API_KEY are both set, and an
offline stand-in with fixed answers when they are not, so the demo runs anywhere and nothing leaves the machine.
WPO_LLM=offline always uses the stand-in; WPO_LLM=azure insists on Azure OpenAI. Both are called the same way.
In a NaviStorm sandbox run the endpoint and key point at NaviStorm's LLM stub, so the agents' model calls are real
HTTP calls to the stub (and can be faulted from M5), never to Azure.
"""
from __future__ import annotations

import os

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_openai import AzureChatOpenAI


class OfflineAnswers(BaseChatModel):
    """Fixed answers: the line of the prompt that starts with "DRAFT:" (the agent's own summary of the data), or a
    short default. Deterministic, so every run repeats exactly."""

    @property
    def _llm_type(self) -> str:
        return "offline-fixed-answers"

    def _generate(self, messages: list[BaseMessage], stop=None, run_manager=None, **kwargs) -> ChatResult:
        text = "\n".join(str(m.content) for m in messages)
        draft = next((line[6:].strip() for line in text.splitlines() if line.startswith("DRAFT:")), "")
        answer = draft or "No answer: the offline model only restates the data it is given."
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=answer))])


def chat_model() -> BaseChatModel:
    mode = os.getenv("WPO_LLM", "auto")
    configured = bool(os.getenv("AZURE_OPENAI_ENDPOINT") and os.getenv("AZURE_OPENAI_API_KEY"))
    if mode == "azure" and not configured:
        raise RuntimeError("WPO_LLM=azure needs AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_API_KEY")
    if mode == "azure" or (mode == "auto" and configured):
        return AzureChatOpenAI(azure_deployment=os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o"), api_version="2024-10-21")
    return OfflineAnswers()


llm = chat_model()
