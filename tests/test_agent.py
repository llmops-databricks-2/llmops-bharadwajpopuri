"""Tests of the agent loop against a scripted model: routing, the message protocol, budgets, memory, errors.

The OpenAI client is a stub that returns prepared responses in order and records every request,
so each test states what the model "decided" and checks what the code did with it. No gateway,
no Lakebase: the live behaviour is recorded by notebooks/agent_experiments.py in docs/agent_log.md.
"""

import json
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

from evidence_curator.agent import FALLBACK_ANSWER, LIMIT_NOTICE, EvidenceCuratorAgent, rag_answer
from evidence_curator.tools import ToolInfo, ToolRegistry, function_spec, resolve_therapy_tool

# ----------------------------------------------------------------------------- stubs


def _answer(text: str | list[dict[str, Any]], prompt_tokens: int = 100, completion_tokens: int = 20) -> SimpleNamespace:
    message = SimpleNamespace(content=text, tool_calls=None)
    return SimpleNamespace(
        choices=[SimpleNamespace(message=message, finish_reason="stop")],
        usage=SimpleNamespace(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens),
    )


def _tool_call(name: str, arguments: dict[str, Any] | str, call_id: str) -> SimpleNamespace:
    raw = arguments if isinstance(arguments, str) else json.dumps(arguments)
    return SimpleNamespace(id=call_id, function=SimpleNamespace(name=name, arguments=raw))


def _calls(*calls: SimpleNamespace, text: str = "") -> SimpleNamespace:
    message = SimpleNamespace(content=text, tool_calls=list(calls))
    return SimpleNamespace(
        choices=[SimpleNamespace(message=message, finish_reason="tool_calls")],
        usage=SimpleNamespace(prompt_tokens=120, completion_tokens=30),
    )


@dataclass
class StubClient:
    """`client.chat.completions.create` returning scripted responses and recording requests."""

    responses: list[SimpleNamespace]
    requests: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Expose create() where the OpenAI client has it."""
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **params: Any) -> SimpleNamespace:  # noqa: ANN401 - mirrors the OpenAI client
        self.requests.append(
            {**params, "messages": [dict(m) for m in params["messages"]]}
        )  # a snapshot: the agent mutates its list
        if not self.responses:
            raise AssertionError("the model was called more times than scripted")
        return self.responses.pop(0)


@dataclass
class StubMemory:
    """Records what the agent loads and saves."""

    history: list[dict[str, Any]] = field(default_factory=list)
    loads: list[tuple[str, int]] = field(default_factory=list)
    saves: list[tuple[str, str, list[dict[str, Any]]]] = field(default_factory=list)

    def load_messages(self, session_id: str, max_messages: int) -> list[dict[str, Any]]:
        """Return the scripted history."""
        self.loads.append((session_id, max_messages))
        return list(self.history)

    def save_turn(self, session_id: str, turn_id: str, messages: list[dict[str, Any]]) -> int:
        """Record the turn; pretend two rows were written."""
        self.saves.append((session_id, turn_id, messages))
        return 2


def _search_tool(results: list[dict[str, Any]] | None = None, calls: list[dict[str, Any]] | None = None) -> ToolInfo:
    """Build a search_papers stand-in that records its arguments and returns scripted passages."""
    recorded = calls if calls is not None else []

    def search_papers(query: str, num_results: int = 5, therapy: str | None = None) -> str:
        recorded.append({"query": query, "num_results": num_results, "therapy": therapy})
        return json.dumps({"query": query, "filters": {}, "results": results or [], "note": "x"})

    spec = function_spec(
        "search_papers",
        "Find passages.",
        {
            "query": {"type": "string"},
            "num_results": {"type": "integer", "minimum": 1, "maximum": 10},
            "therapy": {"type": "string"},
        },
        ["query"],
    )
    return ToolInfo(name="search_papers", spec=spec, exec_fn=search_papers)


PASSAGE = {"pmcid": "PMC11111111", "nct_ids": ["NCT05412004"], "text": "AHI decreased by 25.3 events per hour"}


def _agent(
    responses: list[SimpleNamespace], registry: ToolRegistry | None = None, **kwargs: object
) -> tuple[EvidenceCuratorAgent, StubClient]:
    client = StubClient(responses)
    registry = registry or ToolRegistry().add(_search_tool([PASSAGE]), resolve_therapy_tool())
    return EvidenceCuratorAgent(client, "course_ops.gateway.chat", registry, **kwargs), client  # type: ignore[arg-type]


# ----------------------------------------------------------------------------- routing and protocol


def test_direct_answer_makes_one_model_call_and_no_tool_calls() -> None:
    """A greeting is answered from the first response; tools were offered but not used."""
    agent, client = _agent([_answer("I search 24 papers and 30 trial records.")])
    out = agent.chat("What can you help me with?")
    assert out.answer == "I search 24 papers and 30 trial records." and out.finish_reason == "answer"
    assert out.iterations == 1 and out.tool_calls == [] and out.citations == []
    assert [t["function"]["name"] for t in client.requests[0]["tools"]] == ["search_papers", "resolve_therapy"]
    assert (
        client.requests[0]["messages"][0]["role"] == "system"
        and client.requests[0]["messages"][-1]["content"] == "What can you help me with?"
    )
    assert client.requests[0]["reasoning_effort"] == "low"
    assert out.prompt_tokens == 100 and out.completion_tokens == 20


def test_tool_call_round_trip_keeps_the_protocol() -> None:
    """Assistant tool-call message, one tool message per call under its id, then the model is called again."""
    calls: list[dict[str, Any]] = []
    registry = ToolRegistry().add(_search_tool([PASSAGE], calls))
    agent, client = _agent(
        [
            _calls(_tool_call("search_papers", {"query": "SURMOUNT-OSA AHI", "therapy": "tirzepatide"}, "call_1")),
            _answer("AHI fell by 25.3 events/h (PMC11111111, NCT05412004)."),
        ],
        registry,
    )
    out = agent.chat("What did SURMOUNT-OSA report for AHI?")
    assert out.finish_reason == "answer" and out.iterations == 2
    assert calls == [{"query": "SURMOUNT-OSA AHI", "num_results": 5, "therapy": "tirzepatide"}]
    assert out.tools_used == ["search_papers"] and out.tool_calls[0].ok and out.tool_calls[0].result_chars > 0
    assert out.citations == ["PMC11111111", "NCT05412004"]
    second = client.requests[1]["messages"]
    assert second[-2]["role"] == "assistant" and second[-2]["tool_calls"][0]["id"] == "call_1"
    assert second[-2]["tool_calls"][0]["function"]["name"] == "search_papers"
    assert second[-1] == {"role": "tool", "tool_call_id": "call_1", "content": second[-1]["content"]}
    assert json.loads(second[-1]["content"])["results"] == [PASSAGE]


def test_several_tool_calls_in_one_response_all_run_before_the_next_call() -> None:
    """Two calls in one assistant message become two tool messages, each under its own id, in order."""
    calls: list[dict[str, Any]] = []
    registry = ToolRegistry().add(_search_tool([PASSAGE], calls), resolve_therapy_tool())
    agent, client = _agent(
        [
            _calls(
                _tool_call("resolve_therapy", {"name": "Zepbound"}, "a"),
                _tool_call("search_papers", {"query": "x"}, "b"),
            ),
            _answer("done"),
        ],
        registry,
    )
    out = agent.chat("compare")
    assert out.tools_used == ["resolve_therapy", "search_papers"]
    tool_messages = [m for m in client.requests[1]["messages"] if m["role"] == "tool"]
    assert [m["tool_call_id"] for m in tool_messages] == ["a", "b"]
    assert json.loads(tool_messages[0]["content"])["therapy"] == "tirzepatide"


def test_gpt_oss_content_parts_are_split_into_text() -> None:
    """A list of reasoning and text parts yields the text; reasoning is not the answer."""
    content = [
        {"type": "reasoning", "summary": [{"type": "summary_text", "text": "thinking"}]},
        {"type": "text", "text": "The answer."},
    ]
    agent, _ = _agent([_answer(content)])
    assert agent.chat("q").answer == "The answer."


# ----------------------------------------------------------------------------- failure paths


def test_invalid_tool_request_returns_a_structured_error_and_the_model_recovers() -> None:
    """An unknown tool and bad arguments are not executed; the error goes back as the tool result."""
    calls: list[dict[str, Any]] = []
    registry = ToolRegistry().add(_search_tool([PASSAGE], calls))
    agent, client = _agent(
        [
            _calls(_tool_call("delete_everything", {}, "c1")),
            _calls(_tool_call("search_papers", {"query": "x", "top_k": 50}, "c2")),
            _calls(_tool_call("search_papers", "{not json", "c3")),
            _calls(_tool_call("search_papers", {"query": "x"}, "c4")),
            _answer("recovered"),
        ],
        registry,
    )
    out = agent.chat("q")
    assert out.answer == "recovered" and out.finish_reason == "answer"
    assert [c.ok for c in out.tool_calls] == [False, False, False, True]
    assert calls == [{"query": "x", "num_results": 5, "therapy": None}]
    errors = [
        json.loads([m for m in r["messages"] if m["role"] == "tool"][-1]["content"]) for r in client.requests[1:4]
    ]
    assert "unknown tool" in errors[0]["error"]
    assert "unknown argument 'top_k'" in errors[1]["error"]
    assert "not valid JSON" in errors[2]["error"]


def test_iteration_budget_ends_with_a_limit_answer() -> None:
    """On the last iteration tools are withheld, the limit notice is sent, and the answer is marked limit."""
    agent, client = _agent(
        [
            _calls(_tool_call("search_papers", {"query": "adverse events STEP 1"}, "1")),
            _calls(_tool_call("search_papers", {"query": "adverse events STEP 2"}, "2")),
            _answer("Found STEP 1 and STEP 2 adverse events; the other trials remain unverified."),
        ],
        max_iterations=3,
    )
    out = agent.chat("Search every adverse event in every trial, one trial at a time.")
    assert out.finish_reason == "limit" and out.iterations == 3 and len(out.tool_calls) == 2
    assert "unverified" in out.answer
    last = client.requests[2]
    assert "tools" not in last
    assert last["messages"][-1] == {"role": "system", "content": LIMIT_NOTICE}


def test_tool_call_budget_stops_execution_before_the_iteration_budget() -> None:
    """Past max_tool_calls, further requested calls are answered with an error and not executed."""
    calls: list[dict[str, Any]] = []
    registry = ToolRegistry().add(_search_tool([PASSAGE], calls))
    agent, _ = _agent(
        [
            _calls(
                _tool_call("search_papers", {"query": "a"}, "1"),
                _tool_call("search_papers", {"query": "b"}, "2"),
                _tool_call("search_papers", {"query": "c"}, "3"),
            ),
            _answer("partial"),
        ],
        registry,
        max_tool_calls=2,
    )
    out = agent.chat("q")
    assert len(calls) == 2 and [c.ok for c in out.tool_calls] == [True, True, False]
    assert out.finish_reason == "limit"


def test_empty_answers_are_retried_once_then_fall_back() -> None:
    """Two empty model answers end the turn with the fallback text, never an exception."""
    agent, _ = _agent([_answer(""), _answer("")])
    out = agent.chat("q")
    assert out.answer == FALLBACK_ANSWER and out.finish_reason == "fallback" and out.iterations == 2


def test_tool_exception_becomes_an_error_result_not_a_crash() -> None:
    """A tool that raises is reported to the model as an error result."""

    def broken(query: str, num_results: int = 5, therapy: str | None = None) -> str:
        raise ConnectionError("Lakebase endpoint is starting")

    tool = ToolInfo(name="search_papers", spec=_search_tool().spec, exec_fn=broken)
    agent, client = _agent(
        [_calls(_tool_call("search_papers", {"query": "x"}, "1")), _answer("sorry")], ToolRegistry().add(tool)
    )
    out = agent.chat("q")
    assert out.tool_calls[0].ok is False
    tool_message = [m for m in client.requests[1]["messages"] if m["role"] == "tool"][0]
    assert "ConnectionError" in json.loads(tool_message["content"])["error"]


# ----------------------------------------------------------------------------- memory


def test_history_is_loaded_before_the_first_call_and_the_turn_saved_after_the_last() -> None:
    """With a session, history precedes the question in the prompt and the turn's messages are saved once."""
    memory = StubMemory(
        history=[{"role": "user", "content": "earlier q"}, {"role": "assistant", "content": "earlier a"}]
    )
    agent, client = _agent(
        [_calls(_tool_call("search_papers", {"query": "x"}, "1")), _answer("now a")],
        memory=memory,  # type: ignore[arg-type]
        history_messages=12,
    )
    out = agent.chat("now q", session_id="s1", turn_id="turn-7")
    assert memory.loads == [("s1", 12)] and out.history_loaded == 2 and out.history_saved == 2
    first = client.requests[0]["messages"]
    assert [m["content"] for m in first[1:]] == ["earlier q", "earlier a", "now q"]
    (saved,) = memory.saves
    assert saved[0] == "s1" and saved[1] == "turn-7"
    assert [m["role"] for m in saved[2]] == ["user", "assistant", "tool", "assistant"]
    assert saved[2][-1]["content"] == "now a" and saved[2][-1]["tools"] == [
        {"name": "search_papers", "arguments": {"query": "x"}}
    ]


def test_without_a_session_memory_is_untouched() -> None:
    """No session id: nothing loaded, nothing saved, history_saved is None."""
    memory = StubMemory()
    agent, _ = _agent([_answer("a")], memory=memory)  # type: ignore[arg-type]
    out = agent.chat("q")
    assert memory.loads == [] and memory.saves == [] and out.history_saved is None and out.history_loaded == 0


# ----------------------------------------------------------------------------- the fixed baseline


def test_rag_answer_always_searches_with_the_users_words_then_answers_once() -> None:
    """The baseline retrieves for any question, even a greeting, and makes exactly one model call."""
    calls: list[dict[str, Any]] = []
    registry = ToolRegistry().add(_search_tool([PASSAGE], calls))
    client = StubClient([_answer("Hello! Here are five unrelated passages.")])
    answer, evidence = rag_answer(client, "course_ops.gateway.chat", registry, "Hi there")  # type: ignore[arg-type]
    assert calls == [{"query": "Hi there", "num_results": 5, "therapy": None}]
    assert answer.startswith("Hello") and json.loads(evidence)["results"] == [PASSAGE]
    assert len(client.requests) == 1 and "tools" not in client.requests[0]
