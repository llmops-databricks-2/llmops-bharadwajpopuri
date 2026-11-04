"""Tests for the gateway client factory: no workspace needed, a stub stands in for `WorkspaceClient`."""

import pytest

from evidence_curator.gateway import GATEWAY_PATH, gateway_client, split_content


class _Config:
    host = "https://example.cloud.databricks.com/"

    @staticmethod
    def authenticate() -> dict[str, str]:
        return {"Authorization": "Bearer test-token"}


class _Workspace:
    config = _Config()


def test_gateway_client_targets_unity_gateway_and_uses_sdk_auth() -> None:
    """The client points at <host>/ai-gateway/mlflow/v1 and gets its bearer header from the SDK, not from code."""
    client = gateway_client(_Workspace(), timeout=5.0)  # type: ignore[arg-type]

    assert client.timeout == 5.0

    assert str(client.base_url).rstrip("/") == "https://example.cloud.databricks.com" + GATEWAY_PATH
    assert client.api_key == "databricks-sdk"
    request = client._client.build_request("GET", "https://example.cloud.databricks.com/x")
    authed = next(client._client.auth.auth_flow(request))
    assert authed.headers["Authorization"] == "Bearer test-token"


def test_split_content_handles_strings_and_reasoning_parts() -> None:
    """GPT-OSS through the gateway returns content parts; the answer and the reasoning summary come apart cleanly."""
    assert split_content("plain answer") == ("plain answer", "")
    assert split_content(None) == ("", "")
    parts = [
        {"type": "reasoning", "summary": [{"type": "summary_text", "text": "Need five lines. Cite."}]},
        {"type": "text", "text": "- **Population**: Adults (NCT03548935, minimum_age)."},
    ]
    text, reasoning = split_content(parts)
    assert text == "- **Population**: Adults (NCT03548935, minimum_age)."
    assert reasoning == "Need five lines. Cite."


class _Usage:
    def __init__(self, prompt_tokens: int) -> None:
        self.prompt_tokens = prompt_tokens
        self.total_tokens = prompt_tokens


class _Datum:
    def __init__(self, index: int, embedding: list[float]) -> None:
        self.index = index
        self.embedding = embedding


class _Response:
    def __init__(self, data: list[_Datum], prompt_tokens: int) -> None:
        self.data = data
        self.usage = _Usage(prompt_tokens)


class _Embeddings:
    """A stub of `client.embeddings` that returns vectors out of order and counts tokens by length."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def create(self, model: str, input: list[str]) -> _Response:  # noqa: A002 - the OpenAI parameter name
        self.calls.append(list(input))
        data = [_Datum(i, [float(len(text)), float(i)]) for i, text in enumerate(input)]
        return _Response(list(reversed(data)), prompt_tokens=sum(len(t) // 4 + 1 for t in input))


class _Client:
    def __init__(self) -> None:
        self.embeddings = _Embeddings()


def test_embed_texts_batches_keeps_input_order_and_accounts_usage() -> None:
    """Vectors come back in input order whatever the API's order, batches are counted, and tokens summed."""
    from evidence_curator.gateway import count_tokens, embed_texts

    client = _Client()
    texts = ["a", "bb", "ccc", "dddd", "eeeee"]

    vectors, usage = embed_texts(client, "course_ops.gateway.embed", texts, batch_size=2)  # type: ignore[arg-type]

    assert [v[0] for v in vectors] == [1.0, 2.0, 3.0, 4.0, 5.0]
    assert client.embeddings.calls == [["a", "bb"], ["ccc", "dddd"], ["eeeee"]]
    assert usage.n_texts == 5 and usage.n_calls == 3 and usage.dimension == 2
    assert usage.prompt_tokens == sum(len(t) // 4 + 1 for t in texts)
    assert usage.model == "course_ops.gateway.embed"
    assert count_tokens(client, "course_ops.gateway.embed", "MLOps is awesome") == 5  # type: ignore[arg-type]


def _rate_limit_error() -> Exception:
    import httpx
    from openai import RateLimitError

    request = httpx.Request("POST", "https://example.cloud.databricks.com/ai-gateway/mlflow/v1/embeddings")
    response = httpx.Response(429, request=request, json={"error_code": "REQUEST_LIMIT_EXCEEDED"})
    return RateLimitError("Tokens-per-minute (TPM) rate limit exceeded", response=response, body=None)


class _ThrottledEmbeddings(_Embeddings):
    """A stub gateway with a token budget per 'minute': calls over budget get a 429 until a wait resets it."""

    def __init__(self, budget_tokens: int) -> None:
        super().__init__()
        self.budget = budget_tokens
        self.spent = 0
        self.resets = 0

    def reset(self) -> None:
        self.spent = 0
        self.resets += 1

    def create(self, model: str, input: list[str]) -> _Response:  # noqa: A002 - the OpenAI parameter name
        tokens = sum(len(t) // 4 + 1 for t in input)
        if self.spent + tokens > self.budget:
            self.calls.append(["429"] + list(input))
            raise _rate_limit_error()
        self.spent += tokens
        return super().create(model, input)


def test_embed_texts_waits_out_rate_limits_and_splits_oversized_batches(monkeypatch: pytest.MonkeyPatch) -> None:
    """A 429 is waited out (the sleep stands in for the minute window); a batch over budget by itself is halved."""
    import evidence_curator.gateway as gateway

    embeddings = _ThrottledEmbeddings(budget_tokens=60)
    client = type("Client", (), {"embeddings": embeddings})()
    waited: list[float] = []

    def fake_sleep(seconds: float) -> None:
        waited.append(seconds)
        embeddings.reset()  # time passes, the window reopens

    monkeypatch.setattr(gateway.time, "sleep", fake_sleep)
    # 8 texts of ~25 tokens: a batch of 4 (~100 tokens) never fits the 60-token budget; halves of 2 (~50) do.
    texts = ["x" * 100] * 8

    vectors, usage = gateway.embed_texts(client, "course_ops.gateway.embed", texts, batch_size=4)  # type: ignore[arg-type]

    assert len(vectors) == 8 and all(v[0] == 100.0 for v in vectors)
    assert usage.n_texts == 8 and usage.batch_splits == 2 and usage.rate_limit_hits >= 6
    assert usage.rate_limit_wait_s == pytest.approx(sum(waited))
    assert waited[:3] == [15.0, 30.0, 60.0]  # doubling, capped at a minute
    assert [c for c in embeddings.calls if c[0] != "429"] == [["x" * 100] * 2] * 4


def test_embed_texts_gives_up_after_the_waiting_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    """When the limiter never reopens within the budget, the RateLimitError surfaces instead of looping forever."""
    from openai import RateLimitError

    import evidence_curator.gateway as gateway

    embeddings = _ThrottledEmbeddings(budget_tokens=0)
    client = type("Client", (), {"embeddings": embeddings})()
    monkeypatch.setattr(gateway.time, "sleep", lambda _: None)

    with pytest.raises(RateLimitError):
        gateway.embed_texts(client, "course_ops.gateway.embed", ["a"], batch_size=1, max_wait_s=100)  # type: ignore[arg-type]


def test_create_embeddings_retries_single_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    """The single-call helper used for queries and token counts waits out a 429 as well."""
    import evidence_curator.gateway as gateway

    embeddings = _ThrottledEmbeddings(budget_tokens=10)
    embeddings.spent = 10  # the window is exhausted when the call arrives
    client = type("Client", (), {"embeddings": embeddings})()
    slept: list[float] = []

    def fake_sleep(seconds: float) -> None:
        slept.append(seconds)
        embeddings.reset()

    monkeypatch.setattr(gateway.time, "sleep", fake_sleep)

    assert gateway.count_tokens(client, "course_ops.gateway.embed", "MLOps is awesome") == 5  # type: ignore[arg-type]
    assert slept == [15.0] and embeddings.resets == 1


def test_create_embeddings_waits_out_the_gateways_transient_400(monkeypatch: pytest.MonkeyPatch) -> None:
    """The gateway's 'Cannot create or query foundation model endpoints, please try again later' is retried; other 400s are not."""
    import httpx
    from openai import BadRequestError

    import evidence_curator.gateway as gateway

    def bad_request(message: str) -> BadRequestError:
        response = httpx.Response(400, request=httpx.Request("POST", "https://example/ai-gateway/mlflow/v1/embeddings"))
        return BadRequestError(message, response=response, body={"error_code": "BAD_REQUEST", "message": message})

    class _Flaky(_Embeddings):
        def __init__(self, failures: list[BadRequestError]) -> None:
            super().__init__()
            self.failures = failures

        def create(self, model: str, input: list[str]) -> _Response:  # noqa: A002 - the OpenAI parameter name
            if self.failures:
                raise self.failures.pop(0)
            return super().create(model, input)

    slept: list[float] = []
    monkeypatch.setattr(gateway.time, "sleep", lambda seconds: slept.append(seconds))

    transient = bad_request("BAD_REQUEST: Cannot create or query foundation model endpoints, please try again later.")
    client = type("Client", (), {"embeddings": _Flaky([transient])})()
    usage = gateway.EmbeddingUsage(model="course_ops.gateway.embed")
    gateway.create_embeddings(client, "course_ops.gateway.embed", ["a query"], usage=usage)  # type: ignore[arg-type]
    assert slept == [15.0] and usage.rate_limit_hits == 1

    client = type("Client", (), {"embeddings": _Flaky([bad_request("BAD_REQUEST: input must not be empty")])})()
    with pytest.raises(BadRequestError, match="must not be empty"):
        gateway.create_embeddings(client, "course_ops.gateway.embed", [""])  # type: ignore[arg-type]
