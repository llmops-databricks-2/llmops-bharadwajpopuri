"""MCP tools: discovery through the Databricks managed servers, and the Genie space as `query_trials`.

MCP standardises how the application *discovers* a server's tools (name, description, input schema)
and *invokes* them; it does not choose the orchestration. The adapter here turns every discovered
tool into the same `ToolInfo` the local tools use, so the agent loop never knows which kind it is
calling. Two servers matter for this project:

- the Genie space over the registry tables, `{host}/api/2.0/mcp/genie/{space_id}`, wrapped as one
  tool, `query_trials`, with a stable name and a description written for our data rather than the
  server's generic one;
- a Unity Catalog function server, `{host}/api/2.0/mcp/functions/{catalog}/{schema}/{function}`,
  exposed as-is by `discover_mcp_tools` (the optional MCP-without-Genie example).

Genie answers asynchronously: the query tool returns a conversation and message ID with a pending
status, and a poll tool fetches progress for *that* message. Polling is not a new question; a
follow-up is a new query carrying the conversation ID. The wrapper bounds the wait and returns a
pending result with the IDs rather than re-submitting, so the agent can say the answer is delayed.

Both servers run under the calling identity's own grants on the space, the warehouse and the
tables (they bypass the Unity Gateway), which is why a permission error is diagnosed on the
resource, not on MCP.
"""

import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from databricks.sdk import WorkspaceClient

from evidence_curator.tools import ToolInfo, error_result, function_spec

TERMINAL_STATES = {"COMPLETED", "FAILED", "CANCELLED", "ERROR", "QUERY_RESULT_EXPIRED"}
QUESTION_KEYS = ("query", "question", "content", "message", "prompt")
POLL_INTERVAL_S = 2.0
MAX_WAIT_S = 30.0
RAW_CHARS = 4000
MAX_ROWS = 50  # rows of a Genie result passed to the model; the trial tables are small


class MCPTool(Protocol):
    """What the adapter reads from an `mcp.types.Tool`."""

    name: str
    description: str | None
    inputSchema: dict[str, Any] | None  # noqa: N815 - the MCP field name


class CallResult(Protocol):
    """What the adapter reads from an `mcp.types.CallToolResult`."""

    content: list[object]
    isError: bool  # noqa: N815 - the MCP field name


class MCPClient(Protocol):
    """The two calls of `databricks_mcp.DatabricksMCPClient` the adapter uses (a stub in tests)."""

    def list_tools(self) -> list[MCPTool]:
        """List the server's tools."""
        ...

    def call_tool(self, tool_name: str, arguments: dict[str, Any] | None = None) -> CallResult:
        """Invoke one tool."""
        ...


ClientFactory = Callable[[str, WorkspaceClient], MCPClient]


def databricks_mcp_client(server_url: str, workspace: WorkspaceClient) -> MCPClient:
    """Create the SDK's MCP client for one server URL."""
    from databricks_mcp import DatabricksMCPClient  # imported here so tests need no live client

    return DatabricksMCPClient(server_url=server_url, workspace_client=workspace)


def genie_server_url(workspace: WorkspaceClient, space_id: str) -> str:
    """Return the managed MCP server URL of a Genie space."""
    return f"{workspace.config.host.rstrip('/')}/api/2.0/mcp/genie/{space_id}"


def uc_function_server_url(workspace: WorkspaceClient, catalog: str, schema: str, function: str) -> str:
    """Return the managed MCP server URL of one Unity Catalog function."""
    return f"{workspace.config.host.rstrip('/')}/api/2.0/mcp/functions/{catalog}/{schema}/{function}"


def result_text(response: CallResult) -> str:
    """Join the text blocks of a `CallToolResult`; non-text blocks are noted, not dropped silently."""
    parts: list[str] = []
    for block in getattr(response, "content", None) or []:
        text = getattr(block, "text", None)
        parts.append(text if text is not None else f"[{getattr(block, 'type', 'non-text')} block]")
    return "".join(parts)


def parse_result(response: CallResult) -> dict[str, Any]:
    """Turn a tool result into a dict: parsed JSON when the server sent JSON, else `{"text": ...}`; errors flagged."""
    text = result_text(response)
    try:
        data = json.loads(text) if text else {}
    except json.JSONDecodeError:
        data = {"text": text}
    if not isinstance(data, dict):
        data = {"value": data}
    if getattr(response, "isError", False):
        data["error"] = data.get("error") or text or "MCP server reported an error"
    return data


def find_key(
    data: object, candidates: tuple[str, ...], depth: int = 4, of_type: type | tuple[type, ...] | None = None
) -> object:
    """Return the first value found for any candidate key, searching nested dicts and lists breadth-first.

    `of_type` skips values of another type: the SQL text, not the attachment object that holds it.
    """
    queue: list[tuple[Any, int]] = [(data, 0)]
    while queue:
        node, level = queue.pop(0)
        if isinstance(node, dict):
            for key in candidates:
                value = node.get(key)
                if value in (None, "") or (of_type is not None and not isinstance(value, of_type)):
                    continue
                return value
            if level < depth:
                queue.extend((v, level + 1) for v in node.values())
        elif isinstance(node, list) and level < depth:
            queue.extend((v, level + 1) for v in node)
    return None


def genie_rows(data_array: object) -> list[list[object]]:
    """Flatten a statement result's `data_array` to plain rows.

    The Genie server returns typed cells, `{"values": [{"string_value": "12"}, ...]}` per row; the SDK
    and some servers return plain lists. Both become a list of scalar lists.
    """
    rows: list[list[object]] = []
    if not isinstance(data_array, list):
        return rows
    for row in data_array:
        if isinstance(row, dict) and isinstance(row.get("values"), list):
            rows.append([next(iter(v.values()), None) if isinstance(v, dict) else v for v in row["values"]])
        elif isinstance(row, list):
            rows.append(list(row))
        else:
            rows.append([row])
    return rows


def discover_mcp_tools(
    server_url: str, workspace: WorkspaceClient, client_factory: ClientFactory = databricks_mcp_client
) -> list[ToolInfo]:
    """Every tool of one MCP server as a `ToolInfo`, with the server's own name, description and schema."""
    client = client_factory(server_url, workspace)
    tools: list[ToolInfo] = []
    seen: set[str] = set()
    for mcp_tool in client.list_tools():
        name = mcp_tool.name
        if name in seen:
            raise ValueError(f"{server_url} lists the tool '{name}' twice")
        seen.add(name)
        schema = dict(mcp_tool.inputSchema or {"type": "object", "properties": {}})
        spec = {
            "type": "function",
            "function": {"name": name, "description": mcp_tool.description or f"Tool {name}", "parameters": schema},
        }

        def exec_fn(_name: str = name, **kwargs: object) -> str:
            try:
                data = parse_result(client.call_tool(_name, kwargs))
            except Exception as exc:  # noqa: BLE001
                return error_result(f"{_name} failed: {type(exc).__name__}: {exc}", tool=_name)
            return json.dumps(data, ensure_ascii=False)

        tools.append(ToolInfo(name=name, spec=spec, exec_fn=exec_fn))
    return tools


@dataclass
class GenieSpace:
    """The Genie space's MCP server as one agent tool, `query_trials`, with bounded polling."""

    workspace: WorkspaceClient
    space_id: str
    client_factory: ClientFactory = databricks_mcp_client
    poll_interval_s: float = POLL_INTERVAL_S
    max_wait_s: float = MAX_WAIT_S
    clock: Callable[[], float] = time.monotonic
    sleep: Callable[[float], None] = time.sleep
    query_tool: MCPTool | None = field(default=None, init=False)
    poll_tool: MCPTool | None = field(default=None, init=False)
    _client: MCPClient | None = field(default=None, init=False, repr=False)

    @property
    def server_url(self) -> str:
        """Return the space's managed MCP server URL."""
        return genie_server_url(self.workspace, self.space_id)

    @property
    def client(self) -> MCPClient:
        """Return the MCP client, created on first use."""
        if self._client is None:
            self._client = self.client_factory(self.server_url, self.workspace)
        return self._client

    def discover(self) -> list[MCPTool]:
        """List the server's tools and pick the query and poll operations by name prefix."""
        tools = list(self.client.list_tools())
        self.query_tool = next((t for t in tools if t.name.startswith("query_space")), None)
        self.poll_tool = next((t for t in tools if t.name.startswith("poll_response")), None)
        if self.query_tool is None:
            raise RuntimeError(f"no query tool on {self.server_url}: {[t.name for t in tools]}")
        return tools

    @staticmethod
    def _properties(tool: MCPTool | None) -> dict[str, Any]:
        schema = getattr(tool, "inputSchema", None) or {}
        return dict(schema.get("properties", {}))

    def query_arguments(self, question: str, conversation_id: str | None) -> dict[str, Any]:
        """Name the arguments the way the discovered schema does, rather than assuming them."""
        props = self._properties(self.query_tool)
        key = next((k for k in QUESTION_KEYS if k in props), "query")
        args: dict[str, Any] = {key: question}
        if conversation_id and "conversation_id" in props:
            args["conversation_id"] = conversation_id
        return args

    def poll_arguments(self, conversation_id: str, message_id: str) -> dict[str, Any]:
        """Name the poll arguments the way the discovered schema does."""
        props = self._properties(self.poll_tool)
        args = {"conversation_id": conversation_id, "message_id": message_id}
        return {k: v for k, v in args.items() if not props or k in props}

    @staticmethod
    def summarize(data: dict[str, Any]) -> dict[str, Any]:
        """Pick the fields the agent needs out of the server's response, plus a bounded raw copy for the log.

        The managed Genie server answers with `status`, `conversationId`, `messageId` and a `content`
        object holding `textAttachments` (the answer sentences) and `queryAttachments` (the SQL with its
        `statement_response`: manifest columns and typed `data_array` rows). The lookups below take that
        shape first and fall back to a key search, so a change in the server's envelope degrades to a
        raw copy rather than an exception.
        """
        status = find_key(data, ("status",), of_type=str)
        content = data.get("content") if isinstance(data.get("content"), dict) else {}
        texts = content.get("textAttachments") if isinstance(content, dict) else None
        answer: str | None = None
        if isinstance(texts, list) and texts:
            answer = "\n".join(t if isinstance(t, str) else json.dumps(t) for t in texts)
        else:
            found = find_key(data, ("text", "answer", "result_text", "description"), of_type=str)
            answer = found if isinstance(found, str) else None
        sql: str | None = None
        columns: list[str] = []
        rows: list[list[object]] = []
        total_rows: int | None = None
        attachments = content.get("queryAttachments") if isinstance(content, dict) else None
        if isinstance(attachments, list) and attachments:
            attachment = attachments[0] if isinstance(attachments[0], dict) else {}
            sql = attachment.get("query") if isinstance(attachment.get("query"), str) else None
            statement = attachment.get("statement_response") or {}
            manifest = statement.get("manifest") or {}
            columns = [
                c.get("name") for c in (manifest.get("schema") or {}).get("columns") or [] if isinstance(c, dict)
            ]
            total_rows = manifest.get("total_row_count")
            rows = genie_rows((statement.get("result") or {}).get("data_array"))
        if sql is None:
            found = find_key(data, ("sql", "statement", "query"), of_type=str)
            sql = found if isinstance(found, str) else None
        if not rows:
            found_rows = find_key(data, ("data_array", "rows", "data"), of_type=list)
            rows = genie_rows(found_rows) if isinstance(found_rows, list) else []
        summary: dict[str, Any] = {
            "status": status.upper() if isinstance(status, str) else None,
            "conversation_id": find_key(data, ("conversation_id", "conversationId"), of_type=str),
            "message_id": find_key(data, ("message_id", "messageId"), of_type=str),
            "answer": answer,
            "sql": sql,
            "columns": columns,
            "rows": rows[:MAX_ROWS],
            "total_rows": total_rows if total_rows is not None else (len(rows) or None),
            "error": data.get("error") or find_key(data, ("error",), of_type=str),
        }
        summary["raw"] = json.dumps(data, ensure_ascii=False)[:RAW_CHARS]
        return summary

    def ask(self, question: str, conversation_id: str | None = None) -> dict[str, Any]:
        """Submit a question, poll its message until it completes or the wait budget is spent."""
        query_tool = self.query_tool
        if query_tool is None:
            self.discover()
            query_tool = self.query_tool
        if query_tool is None:
            raise RuntimeError(f"no query tool on {self.server_url}")
        first = self.summarize(
            parse_result(self.client.call_tool(query_tool.name, self.query_arguments(question, conversation_id)))
        )
        first["question"] = question
        if first["error"]:
            return first
        if (
            first["status"] in TERMINAL_STATES
            or self.poll_tool is None
            or not (first["conversation_id"] and first["message_id"])
        ):
            first["status"] = first["status"] or "COMPLETED"
            return first
        deadline = self.clock() + self.max_wait_s
        polls = 0
        latest = first
        while self.clock() < deadline:
            self.sleep(self.poll_interval_s)
            polls += 1
            polled = self.summarize(
                parse_result(
                    self.client.call_tool(
                        self.poll_tool.name, self.poll_arguments(first["conversation_id"], first["message_id"])
                    )
                )
            )
            latest = {**first, **{k: v for k, v in polled.items() if v is not None}}
            latest["polls"] = polls
            if latest["error"] or (latest["status"] in TERMINAL_STATES):
                return latest
        latest["status"] = "PENDING"
        latest["polls"] = polls
        latest["note"] = (
            f"no final answer within {self.max_wait_s:.0f} s; poll again with conversation_id and message_id rather than re-asking"
        )
        return latest

    def query_trials_tool(self) -> ToolInfo:
        """Build the `query_trials` tool over this space."""

        def query_trials(question: str, conversation_id: str | None = None) -> str:
            question = question.strip()
            if not question:
                return error_result("question is empty", hint="ask a question about the trial tables in plain words")
            try:
                result = self.ask(question, conversation_id)
            except Exception as exc:  # noqa: BLE001
                return error_result(f"query_trials failed: {type(exc).__name__}: {exc}", tool="query_trials")
            if result.get("error"):
                return error_result(
                    str(result["error"]), tool="query_trials", status=result.get("status"), raw=result.get("raw")
                )
            return json.dumps(result, ensure_ascii=False)

        spec = function_spec(
            "query_trials",
            "Ask a question about the clinical-trial registry tables of the corpus in plain language; Genie writes "
            "and runs the SQL. Use it for facts about trials: how many, which phase, status, sponsor, enrollment, "
            "start and completion dates, whether results are posted, which publications (PMIDs) are linked to a "
            "trial, and which drug aliases map to a therapy. The tables cover 30 trials of semaglutide, "
            "tirzepatide and liraglutide for obesity. Not for what a paper reports: use search_papers for that. "
            "Returns status, the answer, the SQL run and rows; pass conversation_id back for a follow-up.",
            {
                "question": {
                    "type": "string",
                    "description": "The question, in plain language, naming trials by NCT ID or acronym when known.",
                },
                "conversation_id": {
                    "type": "string",
                    "description": "From a previous query_trials result, to ask a follow-up in the same Genie conversation.",
                },
            },
            ["question"],
        )
        return ToolInfo(name="query_trials", spec=spec, exec_fn=query_trials)
