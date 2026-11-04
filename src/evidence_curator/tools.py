"""Tools of the Evidence Curator agent: contracts the model sees, callables the application keeps.

A tool is two things (lecture 3): a model-facing specification (name, description, JSON-schema
parameters, in the nested function envelope the course's Chat Completions calls use) and an
executable function. The model only ever receives the specification; it returns a *request* to call
a tool by name with JSON arguments, and the application resolves the name in `ToolRegistry`,
validates the arguments against the schema and runs the callable. Nothing the model writes is
executed without passing through that gate.

Local tools live here: `search_papers` over the Lakebase copy of the chunk table, and
`resolve_therapy` over the alias table. The Genie tool, discovered from the managed MCP server, is
in `mcp_tools.py`; both kinds become the same `ToolInfo` so one agent loop serves them.

Results and errors are JSON strings: compact, structured, and explicit about what they are. A tool
that fails returns `{"error": ..., "hint": ...}` rather than raising, so the model can correct a bad
argument or tell the user, and the loop never dies on a tool.
"""

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from evidence_curator.aliases import DRUG_ALIASES, canonical_therapy
from evidence_curator.chunking import SECTIONS
from evidence_curator.vector_store import LakebaseChunkStore, SearchFilters

THERAPIES: tuple[str, ...] = tuple(sorted({a.therapy for a in DRUG_ALIASES}))
MAX_RESULTS = 10
DEFAULT_RESULTS = 5
EXCERPT_CHARS = 600  # enough for a reported result with its numbers; not a whole section
_NCT = re.compile(r"^NCT\d{8}$")
_JSON_TYPES: dict[str, type | tuple[type, ...]] = {
    "string": str,
    "integer": int,
    "number": (int, float),
    "boolean": bool,
    "object": dict,
    "array": list,
}


@dataclass(frozen=True)
class ToolInfo:
    """One tool: the specification the model sees and the function the application runs."""

    name: str
    spec: dict[str, Any]
    exec_fn: Callable[..., str]

    @property
    def parameters(self) -> dict[str, Any]:
        """Return the JSON-schema parameter object of the specification."""
        return self.spec["function"]["parameters"]


def function_spec(name: str, description: str, properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    """Build the Chat Completions function envelope with a closed parameter object."""
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
                "additionalProperties": False,
            },
        },
    }


def error_result(error: str, hint: str | None = None, **extra: str | int | float | bool | None) -> str:
    """Build a tool result that tells the model what went wrong and what would work."""
    payload: dict[str, Any] = {"error": error}
    if hint:
        payload["hint"] = hint
    payload.update(extra)
    return json.dumps(payload, ensure_ascii=False)


def validate_arguments(parameters: dict[str, Any], arguments: dict[str, Any]) -> list[str]:
    """Check arguments against a tool's parameter schema; returns the problems found (empty = valid).

    Covers what the course's teaching loop skips: required keys, unknown keys when the object is
    closed, JSON types (an integer schema rejects "5" and 5.5; a number accepts both int and float),
    enumerations, and numeric bounds when the schema states them. Range *clamping* is the callable's
    job, so a model asking for 50 results gets 10, not an error.
    """
    problems: list[str] = []
    properties: dict[str, Any] = parameters.get("properties", {})
    for key in parameters.get("required", []):
        if key not in arguments:
            problems.append(f"missing required argument '{key}'")
    if parameters.get("additionalProperties") is False:
        for key in arguments:
            if key not in properties:
                problems.append(f"unknown argument '{key}'")
    for key, value in arguments.items():
        schema = properties.get(key)
        if schema is None or value is None:
            continue
        expected = schema.get("type")
        if expected in _JSON_TYPES:
            py_type = _JSON_TYPES[expected]
            # bool is an int in Python; a boolean is not an acceptable integer or number here.
            if isinstance(value, bool) and expected in ("integer", "number"):
                problems.append(f"'{key}' must be a {expected}, got a boolean")
            elif not isinstance(value, py_type):
                problems.append(f"'{key}' must be a {expected}, got {type(value).__name__}")
                continue
        if "enum" in schema and value not in schema["enum"]:
            problems.append(f"'{key}' must be one of {schema['enum']}, got {value!r}")
        if isinstance(value, int | float) and not isinstance(value, bool):
            if "minimum" in schema and value < schema["minimum"]:
                problems.append(f"'{key}' must be >= {schema['minimum']}, got {value}")
            if "maximum" in schema and value > schema["maximum"]:
                problems.append(f"'{key}' must be <= {schema['maximum']}, got {value}")
    return problems


@dataclass
class ToolRegistry:
    """Name → tool, and the one place a model's tool request is turned into an execution."""

    tools: dict[str, ToolInfo] = field(default_factory=dict)

    def add(self, *tools: ToolInfo) -> "ToolRegistry":
        """Register tools; a second tool with a name already taken is an error, never a silent overwrite."""
        for tool in tools:
            if tool.name in self.tools:
                raise ValueError(f"duplicate tool name: {tool.name}")
            self.tools[tool.name] = tool
        return self

    def specs(self) -> list[dict[str, Any]]:
        """Return the specifications in registration order, for the model call."""
        return [tool.spec for tool in self.tools.values()]

    def names(self) -> list[str]:
        """Return the registered tool names."""
        return list(self.tools)

    def execute(self, name: str, arguments: str | dict[str, Any] | None) -> str:
        """Run one tool call as the model requested it; every failure comes back as a structured error.

        `arguments` is the JSON string from the assistant message (or an already-parsed dict).
        """
        tool = self.tools.get(name)
        if tool is None:
            return error_result(f"unknown tool '{name}'", hint=f"available tools: {', '.join(self.names())}")
        if arguments is None or arguments == "":
            parsed: dict[str, Any] = {}
        elif isinstance(arguments, str):
            try:
                parsed = json.loads(arguments)
            except json.JSONDecodeError as exc:
                return error_result(f"arguments are not valid JSON: {exc.msg}", hint="send a JSON object")
        else:
            parsed = dict(arguments)
        if not isinstance(parsed, dict):
            return error_result("arguments must be a JSON object", hint="send a JSON object of named arguments")
        problems = validate_arguments(tool.parameters, parsed)
        if problems:
            return error_result("; ".join(problems), hint="fix the arguments and call the tool again", tool=name)
        try:
            return tool.exec_fn(**parsed)
        except Exception as exc:  # noqa: BLE001 - the loop must survive any tool failure
            return error_result(f"{name} failed: {type(exc).__name__}: {exc}", tool=name)


# ---------------------------------------------------------------------- search_papers


def _excerpt(text: str | None, limit: int = EXCERPT_CHARS) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _listed(value: str | None) -> list[str]:
    return [v for v in (value or "").split(",") if v]


def shape_search_results(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Reduce store rows to what the model needs: identifiers for citation, a score, a bounded excerpt."""
    shaped = []
    for row in rows:
        shaped.append(
            {
                "chunk_id": row.get("id"),
                "pmcid": row.get("pmcid"),
                "title": row.get("title"),
                "journal": row.get("journal"),
                "pub_year": row.get("pub_year"),
                "section": row.get("section"),
                "kind": row.get("kind"),
                "nct_ids": _listed(row.get("nct_ids")),
                "therapies": _listed(row.get("therapies")),
                "score": row.get("score"),
                "text": _excerpt(row.get("text")),
            }
        )
    return shaped


def search_papers_tool(store: LakebaseChunkStore, strategy: str = SECTIONS) -> ToolInfo:
    """Build the retrieval tool: hybrid search over the chunk table, with the lecture-2 metadata filters."""

    def search_papers(
        query: str,
        num_results: int = DEFAULT_RESULTS,
        therapy: str | None = None,
        nct_id: str | None = None,
        year_from: int | None = None,
        year_to: int | None = None,
    ) -> str:
        query = query.strip()
        if not query:
            return error_result("query is empty", hint="describe the evidence you need, in a few words")
        num_results = max(1, min(int(num_results), MAX_RESULTS))
        canonical = None
        if therapy:
            canonical = canonical_therapy(therapy)
            if canonical is None:
                return error_result(
                    f"unknown therapy '{therapy}'",
                    hint=f"use one of {list(THERAPIES)}, or call resolve_therapy on a brand or code name",
                )
        if nct_id:
            nct_id = nct_id.strip().upper()
            if not _NCT.match(nct_id):
                return error_result(
                    f"'{nct_id}' is not an NCT ID", hint="NCT followed by eight digits, e.g. NCT04184622"
                )
        if year_from is not None and year_to is not None and year_from > year_to:
            return error_result("year_from is after year_to", hint="swap the two years")
        filters = SearchFilters(
            strategy=strategy, therapy=canonical, nct_id=nct_id or None, year_from=year_from, year_to=year_to
        )
        rows = store.hybrid_search(query, num_results=num_results, filters=filters)
        applied = {
            k: v
            for k, v in (("therapy", canonical), ("nct_id", nct_id), ("year_from", year_from), ("year_to", year_to))
            if v
        }
        result: dict[str, Any] = {"query": query, "filters": applied, "results": shape_search_results(rows)}
        if not rows:
            result["note"] = (
                "no chunk matched; the corpus holds 24 open-access papers on semaglutide, tirzepatide and liraglutide obesity trials"
            )
        else:
            result["note"] = (
                "results are passages, several may come from one paper; cite by pmcid and check nct_ids match the trial asked about"
            )
        return json.dumps(result, ensure_ascii=False)

    spec = function_spec(
        "search_papers",
        "Find passages inside the open-access trial papers of the corpus (semaglutide, tirzepatide, liraglutide for "
        "obesity): reported results, endpoints, adverse events, methods, populations. Use it when the answer must come "
        "from what a paper says. Returns ranked passages with pmcid, title, year, section, the trials (nct_ids) and "
        "therapies the paper covers, a score and an excerpt. Not for counts, statuses, dates or sponsors of trials: "
        "use query_trials for those.",
        {
            "query": {"type": "string", "description": "What to look for, as a short search phrase or question."},
            "num_results": {
                "type": "integer",
                "description": f"Passages to return, 1-{MAX_RESULTS} (default {DEFAULT_RESULTS}).",
                "minimum": 1,
                "maximum": MAX_RESULTS,
            },
            "therapy": {
                "type": "string",
                "description": "Restrict to papers about one therapy: semaglutide, tirzepatide or liraglutide (a brand "
                "or code name is resolved).",
            },
            "nct_id": {"type": "string", "description": "Restrict to papers linked to one trial, e.g. NCT04184622."},
            "year_from": {"type": "integer", "description": "Earliest publication year to include."},
            "year_to": {"type": "integer", "description": "Latest publication year to include."},
        },
        ["query"],
    )
    return ToolInfo(name="search_papers", spec=spec, exec_fn=search_papers)


# ---------------------------------------------------------------------- resolve_therapy


def resolve_therapy(name: str) -> str:
    """Map a brand, sponsor code or dose label to the canonical therapy the other tools filter on."""
    therapy = canonical_therapy(name)
    payload: dict[str, Any] = {
        "name": name,
        "therapy": therapy,
        "matched": therapy is not None,
        "known_therapies": list(THERAPIES),
    }
    if therapy is None:
        payload["hint"] = "not a known alias; search without a therapy filter or ask the user which therapy is meant"
    return json.dumps(payload, ensure_ascii=False)


def resolve_therapy_tool() -> ToolInfo:
    """Build the alias-resolution tool."""
    spec = function_spec(
        "resolve_therapy",
        "Map a drug name as the user wrote it (brand such as Wegovy or Zepbound, sponsor code such as NN9535 or "
        "LY3298176, dose label such as 'semaglutide 2.4 mg') to the canonical therapy name used by search_papers "
        "and the trial tables. Returns the therapy or matched=false.",
        {"name": {"type": "string", "description": "The drug name to resolve."}},
        ["name"],
    )
    return ToolInfo(name="resolve_therapy", spec=spec, exec_fn=resolve_therapy)
