"""Tests for the gateway client factory: no workspace needed, a stub stands in for `WorkspaceClient`."""

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
