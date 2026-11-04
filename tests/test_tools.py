"""Tests of the agent's tools without a workspace: specifications, validation, result shaping, Genie polling.

The chunk store and the MCP client are stubs that record what they were asked. The live paths
(hybrid search on Lakebase, the Genie space through the managed MCP server) are exercised by
notebooks/agent_tools_check.py, whose output is kept under docs/evidence/.
"""

import json
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

import pytest

from evidence_curator.mcp_tools import (
    TERMINAL_STATES,
    GenieSpace,
    discover_mcp_tools,
    find_key,
    genie_rows,
    genie_server_url,
    parse_result,
)
from evidence_curator.tools import (
    MAX_RESULTS,
    ToolRegistry,
    resolve_therapy_tool,
    search_papers_tool,
    shape_search_results,
    validate_arguments,
)
from evidence_curator.vector_store import SearchFilters

# ----------------------------------------------------------------------------- stubs


@dataclass
class StubStore:
    """`LakebaseChunkStore` as the tool sees it: one method, scripted rows, recorded calls."""

    rows: list[dict[str, Any]] = field(default_factory=list)
    calls: list[dict[str, Any]] = field(default_factory=list)

    def hybrid_search(
        self, query: str, num_results: int = 5, filters: SearchFilters | None = None
    ) -> list[dict[str, Any]]:
        """Record the call and return the scripted rows."""
        self.calls.append({"query": query, "num_results": num_results, "filters": filters})
        return self.rows[:num_results]


def _tool(name: str, properties: dict[str, Any], description: str = "") -> SimpleNamespace:
    return SimpleNamespace(
        name=name,
        description=description,
        inputSchema={"type": "object", "properties": properties, "required": list(properties)},
    )


def _result(payload: str | dict[str, object] | list[object], is_error: bool = False) -> SimpleNamespace:
    text = payload if isinstance(payload, str) else json.dumps(payload)
    return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)], isError=is_error)


@dataclass
class StubMCPClient:
    """An MCP server with a query and a poll tool; poll answers are scripted in order."""

    tools: list[SimpleNamespace]
    responses: dict[str, list[SimpleNamespace]]
    calls: list[tuple[str, dict[str, Any]]] = field(default_factory=list)

    def list_tools(self) -> list[SimpleNamespace]:
        """Return the scripted tools."""
        return self.tools

    def call_tool(self, tool_name: str, arguments: dict[str, Any] | None = None) -> SimpleNamespace:
        """Record the call; the last scripted response repeats."""
        self.calls.append((tool_name, dict(arguments or {})))
        queue = self.responses[tool_name]
        return queue.pop(0) if len(queue) > 1 else queue[0]


SPACE = "01f1deadbeef00000000000000000001"
WORKSPACE = SimpleNamespace(config=SimpleNamespace(host="https://example.cloud.databricks.com/"))
GENIE_TOOLS = [
    _tool(f"query_space_{SPACE}", {"query": {"type": "string"}, "conversation_id": {"type": "string"}}, "Ask Genie"),
    _tool(f"poll_response_{SPACE}", {"conversation_id": {"type": "string"}, "message_id": {"type": "string"}}, "Poll"),
]


def _genie(
    responses: dict[str, list[SimpleNamespace]], max_wait_s: float = 30.0
) -> tuple[GenieSpace, StubMCPClient, list[float]]:
    client = StubMCPClient(tools=GENIE_TOOLS, responses=responses)
    clock = [0.0]
    sleeps: list[float] = []

    def tick(seconds: float) -> None:
        sleeps.append(seconds)
        clock[0] += seconds

    space = GenieSpace(
        workspace=WORKSPACE,  # type: ignore[arg-type]
        space_id=SPACE,
        client_factory=lambda url, w: client,
        poll_interval_s=2.0,
        max_wait_s=max_wait_s,
        clock=lambda: clock[0],
        sleep=tick,
    )
    return space, client, sleeps


ROW = {
    "id": "PMC9556320:section:12",
    "pmcid": "PMC9556320",
    "chunk_seq": 12,
    "strategy": "section",
    "kind": "text",
    "section": "Results",
    "page": 4,
    "title": "Two-year effects of semaglutide in adults with overweight or obesity: the STEP 5 trial",
    "journal": "Nature Medicine",
    "pub_year": 2022,
    "therapies": "semaglutide",
    "nct_ids": "NCT03693430",
    "text": "Mean change in body weight from baseline to week 104 was " + "x" * 700,
    "score": 0.0163,
    "vector_rank": 1,
    "text_rank": 3,
}


# ----------------------------------------------------------------------------- specifications


def test_specs_are_closed_function_schemas() -> None:
    """Every specification is a function with a closed object of parameters and a description."""
    registry = ToolRegistry().add(search_papers_tool(StubStore()), resolve_therapy_tool())  # type: ignore[arg-type]
    assert registry.names() == ["search_papers", "resolve_therapy"]
    for spec in registry.specs():
        assert spec["type"] == "function"
        params = spec["function"]["parameters"]
        assert params["type"] == "object"
        assert params["additionalProperties"] is False
        assert set(params["required"]) <= set(params["properties"])
        assert spec["function"]["description"]


def test_duplicate_tool_names_are_rejected() -> None:
    """A second tool under a taken name is an error, not an overwrite."""
    registry = ToolRegistry().add(resolve_therapy_tool())
    with pytest.raises(ValueError, match="duplicate"):
        registry.add(resolve_therapy_tool())


# ----------------------------------------------------------------------------- validation


@pytest.mark.parametrize(
    ("arguments", "problem"),
    [
        ({}, "missing required argument 'query'"),
        ({"query": "x", "top_k": 3}, "unknown argument 'top_k'"),
        ({"query": "x", "num_results": "5"}, "'num_results' must be a integer"),
        ({"query": "x", "num_results": 5.5}, "'num_results' must be a integer"),
        ({"query": "x", "num_results": True}, "'num_results' must be a integer"),
        ({"query": "x", "num_results": 0}, "'num_results' must be >= 1"),
        ({"query": "x", "num_results": 99}, "'num_results' must be <= 10"),
        ({"query": 7}, "'query' must be a string"),
    ],
)
def test_validate_arguments_reports_each_problem(arguments: dict[str, Any], problem: str) -> None:
    """Missing, unknown, mistyped and out-of-range arguments are each named."""
    params = search_papers_tool(StubStore()).parameters  # type: ignore[arg-type]
    assert problem in "; ".join(validate_arguments(params, arguments))


def test_validate_arguments_accepts_a_good_call() -> None:
    """A call that matches the schema has no problems."""
    params = search_papers_tool(StubStore()).parameters  # type: ignore[arg-type]
    assert validate_arguments(params, {"query": "x", "num_results": 3, "therapy": "Wegovy", "year_from": 2024}) == []


def test_registry_execute_turns_every_failure_into_a_structured_error() -> None:
    """Unknown tools, bad JSON, non-objects and invalid arguments all come back as error results."""
    registry = ToolRegistry().add(search_papers_tool(StubStore()), resolve_therapy_tool())  # type: ignore[arg-type]
    unknown = json.loads(registry.execute("delete_everything", "{}"))
    assert "unknown tool" in unknown["error"] and "search_papers" in unknown["hint"]
    bad_json = json.loads(registry.execute("search_papers", "{not json"))
    assert "not valid JSON" in bad_json["error"]
    not_object = json.loads(registry.execute("search_papers", "[1, 2]"))
    assert "JSON object" in not_object["error"]
    invalid = json.loads(registry.execute("search_papers", json.dumps({"query": "x", "top_k": 3})))
    assert "unknown argument" in invalid["error"] and invalid["tool"] == "search_papers"


def test_registry_execute_catches_exceptions_from_the_callable() -> None:
    """An exception inside a tool becomes an error result; the loop survives."""

    class Broken:
        def hybrid_search(self, *args: object, **kwargs: object) -> list[dict[str, Any]]:
            """Fail like a store whose endpoint is still starting."""
            raise ConnectionError("Lakebase endpoint is starting")

    registry = ToolRegistry().add(search_papers_tool(Broken()))  # type: ignore[arg-type]
    out = json.loads(registry.execute("search_papers", {"query": "weight loss"}))
    assert out["error"].startswith("search_papers failed: ConnectionError")


# ----------------------------------------------------------------------------- search_papers


def test_search_papers_shapes_rows_and_bounds_the_excerpt() -> None:
    """Rows are reduced to citation fields, lists are split, the excerpt is bounded, ranks are dropped."""
    store = StubStore(rows=[ROW])
    out = json.loads(
        ToolRegistry().add(search_papers_tool(store)).execute("search_papers", {"query": "two-year weight change"})
    )  # type: ignore[arg-type]
    assert out["query"] == "two-year weight change"
    assert out["filters"] == {}
    (hit,) = out["results"]
    assert hit["pmcid"] == "PMC9556320" and hit["chunk_id"] == "PMC9556320:section:12"
    assert hit["nct_ids"] == ["NCT03693430"] and hit["therapies"] == ["semaglutide"]
    assert hit["score"] == 0.0163
    assert len(hit["text"]) <= 600 and hit["text"].endswith("…")
    assert "vector_rank" not in hit
    assert "cite by pmcid" in out["note"]


def test_search_papers_resolves_aliases_clamps_and_filters() -> None:
    """A brand name becomes the canonical therapy, num_results is clamped, filters reach the store."""
    store = StubStore(rows=[ROW])
    tool = search_papers_tool(store)  # type: ignore[arg-type]
    tool.exec_fn(query="OSA", num_results=50, therapy="Zepbound", nct_id="nct05412004", year_from=2024, year_to=2026)
    call = store.calls[-1]
    assert call["num_results"] == MAX_RESULTS
    assert call["filters"] == SearchFilters(
        strategy="section", therapy="tirzepatide", nct_id="NCT05412004", year_from=2024, year_to=2026
    )
    tool.exec_fn(query="OSA", num_results=0)
    assert store.calls[-1]["num_results"] == 1


@pytest.mark.parametrize(
    ("kwargs", "fragment"),
    [
        ({"query": "   "}, "query is empty"),
        ({"query": "x", "therapy": "Placebo"}, "unknown therapy 'Placebo'"),
        ({"query": "x", "nct_id": "NCT123"}, "is not an NCT ID"),
        ({"query": "x", "year_from": 2025, "year_to": 2020}, "year_from is after year_to"),
    ],
)
def test_search_papers_argument_errors_do_not_hit_the_store(kwargs: dict[str, Any], fragment: str) -> None:
    """Argument errors are answered before any database work."""
    store = StubStore(rows=[ROW])
    out = json.loads(search_papers_tool(store).exec_fn(**kwargs))  # type: ignore[arg-type]
    assert fragment in out["error"] and out["hint"]
    assert store.calls == []


def test_search_papers_empty_result_says_so() -> None:
    """An empty result carries a note the model can relay."""
    out = json.loads(search_papers_tool(StubStore()).exec_fn(query="OASIS 1 oral semaglutide"))  # type: ignore[arg-type]
    assert out["results"] == [] and out["note"].startswith("no chunk matched")


def test_shape_search_results_tolerates_missing_columns() -> None:
    """Missing columns shape to empty values rather than raising."""
    (hit,) = shape_search_results([{"id": "x", "text": None}])
    assert hit["text"] == "" and hit["nct_ids"] == [] and hit["pmcid"] is None


# ----------------------------------------------------------------------------- resolve_therapy


@pytest.mark.parametrize(
    ("name", "therapy"),
    [
        ("Wegovy", "semaglutide"),
        ("LY3298176", "tirzepatide"),
        ("Saxenda", "liraglutide"),
        ("Semaglutide 2.4 mg", "semaglutide"),
    ],
)
def test_resolve_therapy_maps_aliases(name: str, therapy: str) -> None:
    """Brands, sponsor codes and dose labels map to the canonical therapy."""
    out = json.loads(resolve_therapy_tool().exec_fn(name=name))
    assert out == {
        "name": name,
        "therapy": therapy,
        "matched": True,
        "known_therapies": ["liraglutide", "semaglutide", "tirzepatide"],
    }


def test_resolve_therapy_reports_a_miss_with_a_hint() -> None:
    """A class name is not a therapy; the miss carries a hint."""
    out = json.loads(resolve_therapy_tool().exec_fn(name="GLP-1 receptor agonist"))
    assert out["matched"] is False and out["therapy"] is None and "hint" in out


# ----------------------------------------------------------------------------- MCP adapter


def test_genie_server_url_strips_the_trailing_slash() -> None:
    """The server URL is built from the host without a doubled slash."""
    assert genie_server_url(WORKSPACE, SPACE) == f"https://example.cloud.databricks.com/api/2.0/mcp/genie/{SPACE}"  # type: ignore[arg-type]


def test_parse_result_handles_json_text_and_errors() -> None:
    """JSON text parses, plain text is kept, lists are wrapped, isError is flagged."""
    assert parse_result(_result({"status": "COMPLETED"})) == {"status": "COMPLETED"}
    assert parse_result(_result("plain words")) == {"text": "plain words"}
    assert parse_result(_result([1, 2])) == {"value": [1, 2]}
    err = parse_result(_result("permission denied", is_error=True))
    assert err["error"] == "permission denied"


def test_find_key_searches_nested_structures_in_order() -> None:
    """Keys are found at any depth, candidates in order, optionally by type."""
    data = {"message": {"status": "EXECUTING", "attachments": [{"query": {"query": "SELECT 1"}}]}, "message_id": "m1"}
    assert find_key(data, ("status",)) == "EXECUTING"
    assert find_key(data, ("message_id",)) == "m1"
    assert find_key(data, ("sql", "query")) == {"query": "SELECT 1"}
    assert find_key(data, ("sql", "query"), of_type=str) == "SELECT 1"
    assert find_key(data, ("nothing",)) is None


def test_discover_mcp_tools_wraps_every_server_tool() -> None:
    """A discovered tool keeps the server's name and schema and calls through the client."""
    client = StubMCPClient(
        tools=[_tool("add_numbers", {"a": {"type": "number"}, "b": {"type": "number"}}, "Add")],
        responses={"add_numbers": [_result({"value": 13})]},
    )
    (tool,) = discover_mcp_tools(
        "https://x/api/2.0/mcp/functions/c/s/add_numbers", WORKSPACE, client_factory=lambda url, w: client
    )  # type: ignore[arg-type]
    assert tool.name == "add_numbers" and tool.spec["function"]["parameters"]["required"] == ["a", "b"]
    assert json.loads(tool.exec_fn(a=10, b=3)) == {"value": 13}
    assert client.calls == [("add_numbers", {"a": 10, "b": 3})]


def test_discover_mcp_tools_rejects_duplicate_names() -> None:
    """Two tools of one name on a server are refused."""
    client = StubMCPClient(tools=[_tool("t", {}), _tool("t", {})], responses={})
    with pytest.raises(ValueError, match="twice"):
        discover_mcp_tools("https://x", WORKSPACE, client_factory=lambda url, w: client)  # type: ignore[arg-type]


# ----------------------------------------------------------------------------- Genie as query_trials


def test_query_trials_polls_until_completed_and_keeps_the_ids() -> None:
    """Polling continues until a terminal state; the ids, answer, SQL, columns and rows are returned."""
    pending = _result({"status": "EXECUTING", "conversationId": "c1", "messageId": "m1"})
    done = _result(
        {
            "status": "COMPLETED",
            "conversationId": "c1",
            "messageId": "m1",
            "content": {
                "textAttachments": ["12 trials are phase 3."],
                "queryAttachments": [
                    {
                        "query": "SELECT therapy, count(*) AS n FROM trials WHERE phase = 'PHASE3' GROUP BY therapy",
                        "description": "Phase 3 trials per therapy",
                        "statement_response": {
                            "manifest": {
                                "schema": {"columns": [{"name": "therapy"}, {"name": "n"}]},
                                "total_row_count": 3,
                            },
                            "result": {
                                "data_array": [
                                    {"values": [{"string_value": "liraglutide"}, {"string_value": "8"}]},
                                    {"values": [{"string_value": "semaglutide"}, {"string_value": "11"}]},
                                    {"values": [{"string_value": "tirzepatide"}, {"string_value": "9"}]},
                                ]
                            },
                        },
                    }
                ],
            },
        }
    )
    space, client, sleeps = _genie(
        {f"query_space_{SPACE}": [pending], f"poll_response_{SPACE}": [pending, pending, done]}
    )
    out = json.loads(space.query_trials_tool().exec_fn(question="How many trials are phase 3?"))
    assert out["status"] == "COMPLETED" and out["conversation_id"] == "c1" and out["message_id"] == "m1"
    assert out["polls"] == 3 and sleeps == [2.0, 2.0, 2.0]
    assert out["answer"] == "12 trials are phase 3."
    assert out["sql"].startswith("SELECT therapy") and out["columns"] == ["therapy", "n"]
    assert out["rows"] == [["liraglutide", "8"], ["semaglutide", "11"], ["tirzepatide", "9"]] and out["total_rows"] == 3
    assert client.calls[0] == (f"query_space_{SPACE}", {"query": "How many trials are phase 3?"})
    assert client.calls[1] == (f"poll_response_{SPACE}", {"conversation_id": "c1", "message_id": "m1"})


def test_genie_rows_flattens_typed_and_plain_rows() -> None:
    """Typed cells, plain lists and scalars all become lists of scalars."""
    assert genie_rows([{"values": [{"string_value": "a"}, {"long_value": 2}]}, ["b", 3], "c"]) == [
        ["a", 2],
        ["b", 3],
        ["c"],
    ]
    assert genie_rows(None) == []


def test_query_trials_returns_pending_with_ids_when_the_budget_is_spent() -> None:
    """When the wait budget runs out the result is PENDING with the ids, and the question is never re-submitted."""
    pending = _result({"status": "SUBMITTED", "conversation_id": "c2", "message_id": "m2"})
    space, client, sleeps = _genie(
        {f"query_space_{SPACE}": [pending], f"poll_response_{SPACE}": [pending]}, max_wait_s=7.0
    )
    out = json.loads(space.query_trials_tool().exec_fn(question="Which trials are recruiting?"))
    assert out["status"] == "PENDING" and out["conversation_id"] == "c2" and out["message_id"] == "m2"
    assert out["polls"] == 4 and "poll again" in out["note"]
    assert len([c for c in client.calls if c[0].startswith("query_space")]) == 1  # never re-submitted


def test_query_trials_follow_up_carries_the_conversation_id() -> None:
    """A follow-up passes the conversation id to the query tool."""
    done = _result(
        {
            "status": "COMPLETED",
            "conversation_id": "c3",
            "message_id": "m3",
            "text": "Novo Nordisk sponsors 19 of them.",
        }
    )
    space, client, _ = _genie({f"query_space_{SPACE}": [done]})
    out = json.loads(space.query_trials_tool().exec_fn(question="And who sponsors them?", conversation_id="c3"))
    assert out["status"] == "COMPLETED" and out["answer"] == "Novo Nordisk sponsors 19 of them."
    assert client.calls == [(f"query_space_{SPACE}", {"query": "And who sponsors them?", "conversation_id": "c3"})]


def test_query_trials_reports_server_errors_and_failed_states() -> None:
    """MCP errors and FAILED messages become error results."""
    denied = _result("PERMISSION_DENIED: no CAN_RUN on space", is_error=True)
    space, _, _ = _genie({f"query_space_{SPACE}": [denied]})
    out = json.loads(space.query_trials_tool().exec_fn(question="x"))
    assert out["error"].startswith("PERMISSION_DENIED") and out["tool"] == "query_trials"

    failed = _result({"status": "FAILED", "conversation_id": "c4", "message_id": "m4", "error": "warehouse stopped"})
    space, _, _ = _genie({f"query_space_{SPACE}": [failed]})
    out = json.loads(space.query_trials_tool().exec_fn(question="x"))
    assert out["error"] == "warehouse stopped" and out["status"] == "FAILED"
    assert "FAILED" in TERMINAL_STATES


def test_query_trials_without_a_poll_tool_treats_the_first_answer_as_final() -> None:
    """A server without a poll tool answers synchronously."""
    client = StubMCPClient(tools=[GENIE_TOOLS[0]], responses={f"query_space_{SPACE}": [_result({"text": "3 trials"})]})
    space = GenieSpace(workspace=WORKSPACE, space_id=SPACE, client_factory=lambda url, w: client)  # type: ignore[arg-type]
    out = json.loads(space.query_trials_tool().exec_fn(question="x"))
    assert out["status"] == "COMPLETED" and out["answer"] == "3 trials"


def test_genie_discover_requires_a_query_tool() -> None:
    """A space whose server lists no query tool cannot be used."""
    client = StubMCPClient(tools=[GENIE_TOOLS[1]], responses={})
    space = GenieSpace(workspace=WORKSPACE, space_id=SPACE, client_factory=lambda url, w: client)  # type: ignore[arg-type]
    with pytest.raises(RuntimeError, match="no query tool"):
        space.discover()
