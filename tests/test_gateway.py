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
