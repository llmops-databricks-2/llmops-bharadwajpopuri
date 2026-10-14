"""Call the course's model services through Unity Gateway with Databricks SDK authentication.

Model services (`course_ops.gateway.chat`, `course_ops.gateway.embed`) are Unity Catalog objects
behind the workspace's gateway, which speaks the OpenAI API at `<host>/ai-gateway/mlflow/v1`.
Authentication is delegated to `WorkspaceClient`: the same code works in a Databricks notebook
(notebook credentials), on a laptop (OAuth profile from the Databricks CLI/VS Code extension) and
in a job run by a service principal, and no token ever appears in code or notebook output.

The pattern mirrors `databricks.sdk`'s own OpenAI helper: an `httpx.Auth` hook asks the SDK for
fresh headers on every request, so OAuth tokens are refreshed rather than copied.
"""

import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

import httpx
from databricks.sdk import WorkspaceClient
from openai import OpenAI

GATEWAY_PATH = "/ai-gateway/mlflow/v1"


class _DatabricksAuth(httpx.Auth):
    """Attach fresh Databricks auth headers to every request."""

    def __init__(self, workspace: WorkspaceClient) -> None:
        self._workspace = workspace

    def auth_flow(self, request: httpx.Request) -> Iterator[httpx.Request]:
        request.headers["Authorization"] = self._workspace.config.authenticate()["Authorization"]
        yield request


def gateway_client(workspace: WorkspaceClient | None = None, timeout: float = 120.0, max_retries: int = 2) -> OpenAI:
    """Build an OpenAI client pointed at the workspace's Unity Gateway, authenticated by the SDK.

    Args:
        workspace: An existing `WorkspaceClient`; a default one is created otherwise, which picks up
            notebook credentials, `DATABRICKS_CONFIG_PROFILE`, or `DATABRICKS_HOST`/`DATABRICKS_TOKEN`.
        timeout: Per-request timeout in seconds; reasoning models can take a while on long prompts.
        max_retries: Retries on 429/5xx, which the OpenAI client applies with backoff.

    """
    workspace = workspace or WorkspaceClient()
    return OpenAI(
        base_url=workspace.config.host.rstrip("/") + GATEWAY_PATH,
        api_key="databricks-sdk",  # placeholder: the real credential is added per request by _DatabricksAuth
        http_client=httpx.Client(auth=_DatabricksAuth(workspace)),
        timeout=timeout,
        max_retries=max_retries,
    )


@dataclass
class ChatResult:
    """What an experiment records about one chat call."""

    model: str
    prompt_label: str
    content: str
    prompt_tokens: int | None
    completion_tokens: int | None
    total_tokens: int | None
    latency_s: float
    finish_reason: str | None
    reasoning: str = ""
    raw_usage: dict[str, Any] = field(default_factory=dict)


def split_content(content: str | list[Any] | None) -> tuple[str, str]:
    """Separate the answer text from the reasoning summary in a message's content.

    Through the gateway, GPT-OSS returns `message.content` as a list of parts rather than a string:
    `{"type": "reasoning", "summary": [{"type": "summary_text", "text": ...}]}` followed by
    `{"type": "text", "text": ...}`. Agent code that assumes a string breaks on it, so the two are
    split here once: the text parts joined as the answer, the reasoning summaries joined separately.
    A plain string passes through unchanged.
    """
    if content is None:
        return "", ""
    if isinstance(content, str):
        return content, ""
    texts: list[str] = []
    reasoning: list[str] = []
    for part in content:
        item = part.model_dump() if hasattr(part, "model_dump") else dict(part)
        if item.get("type") == "text":
            texts.append(item.get("text") or "")
        elif item.get("type") == "reasoning":
            reasoning.extend((s.get("text") or "") for s in item.get("summary") or [])
    return "\n".join(t for t in texts if t), "\n".join(r for r in reasoning if r)


def chat(
    client: OpenAI,
    model: str,
    messages: list[dict[str, str]],
    prompt_label: str = "",
    max_tokens: int = 1024,
    reasoning_effort: str | None = "low",
    temperature: float | None = None,
) -> ChatResult:
    """One chat completion with timing and token accounting, for recording experiments.

    `reasoning_effort` is passed because the course chat service routes to GPT-OSS-120B, a reasoning
    model: its hidden reasoning tokens are billed as completion tokens, which is one of the things
    worth measuring.
    """
    params: dict[str, Any] = {"model": model, "messages": messages, "max_tokens": max_tokens}
    if reasoning_effort is not None:
        params["reasoning_effort"] = reasoning_effort
    if temperature is not None:
        params["temperature"] = temperature
    started = time.perf_counter()
    response = client.chat.completions.create(**params)
    latency = time.perf_counter() - started
    usage = response.usage
    choice = response.choices[0]
    text, reasoning = split_content(choice.message.content)
    return ChatResult(
        model=model,
        prompt_label=prompt_label,
        content=text,
        prompt_tokens=getattr(usage, "prompt_tokens", None),
        completion_tokens=getattr(usage, "completion_tokens", None),
        total_tokens=getattr(usage, "total_tokens", None),
        latency_s=round(latency, 2),
        finish_reason=choice.finish_reason,
        reasoning=reasoning,
        raw_usage=usage.model_dump() if usage is not None else {},
    )
