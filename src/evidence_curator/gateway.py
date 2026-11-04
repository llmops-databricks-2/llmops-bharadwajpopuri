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
from collections import deque
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from typing import Any

import httpx
from databricks.sdk import WorkspaceClient
from openai import BadRequestError, OpenAI, RateLimitError
from openai.types import CreateEmbeddingResponse

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


@dataclass
class EmbeddingUsage:
    """What the embedding step records: calls, tokens, seconds, and how much the gateway's rate limit cost."""

    model: str
    n_texts: int = 0
    n_calls: int = 0
    prompt_tokens: int = 0
    latency_s: float = 0.0
    dimension: int | None = None
    rate_limit_hits: int = 0  # 429 responses from the gateway
    rate_limit_wait_s: float = 0.0  # time spent waiting for the per-minute window to reopen
    batch_splits: int = 0  # batches halved because they exceeded the per-minute budget on their own

    def add(self, n_texts: int, prompt_tokens: int | None, latency_s: float, dimension: int | None) -> None:
        """Accumulate one call's accounting."""
        self.n_texts += n_texts
        self.n_calls += 1
        self.prompt_tokens += prompt_tokens or 0
        self.latency_s = round(self.latency_s + latency_s, 2)
        self.dimension = self.dimension or dimension


# The course's model services carry a tokens-per-minute limit per user. A limiter measured by the
# minute cannot be out-waited by the OpenAI client's own retries (a few seconds), so 429s are handled
# here: wait, retry the same batch, and halve a batch that keeps failing because it alone is over budget.
RATE_LIMIT_FIRST_WAIT_S = 15.0
RATE_LIMIT_MAX_WAIT_S = 60.0
RATE_LIMIT_BUDGET_S = 2700.0  # give up after this much waiting in total (the job's timeout is longer)
SPLIT_AFTER_HITS = 3


def _next_wait(previous: float) -> float:
    return min(previous * 2, RATE_LIMIT_MAX_WAIT_S)


def is_transient_bad_request(exc: BaseException) -> bool:
    """Whether a 400 from the gateway is its 'try again later' condition rather than a bad request."""
    return "try again later" in str(exc).lower()


def create_embeddings(
    client: OpenAI,
    model: str,
    inputs: Sequence[str],
    usage: EmbeddingUsage | None = None,
    max_wait_s: float = RATE_LIMIT_BUDGET_S,
) -> CreateEmbeddingResponse:
    """One embeddings call that waits out the gateway's per-minute rate limit instead of failing on it.

    The gateway also answers with a 400 `BAD_REQUEST: Cannot create or query foundation model
    endpoints, please try again later` while its backing endpoint is unavailable (seen 2026-11-04);
    that is a transient condition dressed as a client error, so it is waited out the same way,
    within the same budget. Any other 400 is a real request error and surfaces at once.
    """
    usage = usage or EmbeddingUsage(model=model)
    delay = RATE_LIMIT_FIRST_WAIT_S
    while True:
        try:
            return client.embeddings.create(model=model, input=list(inputs))
        except (RateLimitError, BadRequestError) as exc:
            if isinstance(exc, BadRequestError) and not is_transient_bad_request(exc):
                raise
            if usage.rate_limit_wait_s + delay > max_wait_s:
                raise
            usage.rate_limit_hits += 1
            usage.rate_limit_wait_s = round(usage.rate_limit_wait_s + delay, 1)
            time.sleep(delay)
            delay = _next_wait(delay)


def embed_texts(
    client: OpenAI,
    model: str,
    texts: Sequence[str],
    batch_size: int = 32,
    max_wait_s: float = RATE_LIMIT_BUDGET_S,
    pause_s: float = 0.0,
    log_every: int = 0,
) -> tuple[list[list[float]], EmbeddingUsage]:
    """Embed texts through the gateway's embeddings API in batches; vectors come back in input order.

    The same client and model service must embed the documents and, later, the queries: vectors from
    different models are not comparable even when their dimension matches. The gateway reports
    `usage.prompt_tokens` per call, which is the model's own token count of the batch, the number to
    trust over the four-characters-per-token estimate.

    Rate limits: on a 429 the batch waits (15 s, doubling to 60 s) and is retried; after three
    consecutive 429s a batch of more than one text is split in two, since it may exceed the
    per-minute budget by itself. `usage` records the hits, the waiting time and the splits, which
    is the throughput story the lecture asked to measure for batch ingestion. `pause_s` spaces calls
    out when the budget is known to be tight; `log_every` prints a progress line every N calls, so a
    throttled run shows it is alive.
    """
    usage = EmbeddingUsage(model=model)
    vectors: list[list[float] | None] = [None] * len(texts)
    pending: deque[tuple[int, int]] = deque(
        (s, min(s + batch_size, len(texts))) for s in range(0, len(texts), batch_size)
    )
    delay = RATE_LIMIT_FIRST_WAIT_S
    hits_in_a_row = 0
    while pending:
        start, end = pending[0]
        batch = list(texts[start:end])
        began = time.perf_counter()
        try:
            response = client.embeddings.create(model=model, input=batch)
        except RateLimitError:
            if usage.rate_limit_wait_s + delay > max_wait_s:
                raise
            hits_in_a_row += 1
            usage.rate_limit_hits += 1
            usage.rate_limit_wait_s = round(usage.rate_limit_wait_s + delay, 1)
            time.sleep(delay)
            delay = _next_wait(delay)
            if hits_in_a_row >= SPLIT_AFTER_HITS and end - start > 1:
                middle = (start + end) // 2
                pending.popleft()
                pending.appendleft((middle, end))
                pending.appendleft((start, middle))
                usage.batch_splits += 1
                hits_in_a_row = 0
            continue
        pending.popleft()
        hits_in_a_row = 0
        delay = RATE_LIMIT_FIRST_WAIT_S
        latency = time.perf_counter() - began
        ordered = sorted(response.data, key=lambda d: d.index)
        if len(ordered) != len(batch):
            raise RuntimeError(f"embedding call returned {len(ordered)} vectors for {len(batch)} inputs")
        for offset, datum in enumerate(ordered):
            vectors[start + offset] = list(datum.embedding)
        usage.add(
            n_texts=len(batch),
            prompt_tokens=getattr(response.usage, "prompt_tokens", None) if response.usage else None,
            latency_s=latency,
            dimension=len(ordered[0].embedding) if ordered else None,
        )
        if log_every and usage.n_calls % log_every == 0:
            print(
                f"  embedded {usage.n_texts}/{len(texts)} texts in {usage.n_calls} calls, {usage.prompt_tokens} tokens; "
                f"rate limit: {usage.rate_limit_hits} hits, {usage.rate_limit_wait_s} s waited, {usage.batch_splits} splits"
            )
        if pause_s and pending:
            time.sleep(pause_s)
    if any(v is None for v in vectors):
        raise RuntimeError("some texts were not embedded")
    return [v for v in vectors if v is not None], usage


def count_tokens(client: OpenAI, model: str, text: str) -> int | None:
    """Measure the model's token count of one text by embedding it alone and reading the usage report."""
    response = create_embeddings(client, model, [text])
    return getattr(response.usage, "prompt_tokens", None) if response.usage else None
