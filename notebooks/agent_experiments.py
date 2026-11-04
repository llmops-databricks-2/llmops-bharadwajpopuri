# Databricks notebook source
# ruff: noqa: ERA001
# Databricks MAGIC comments are executable notebook cells.
"""Agent experiments: the verification set V1–V8 through the agent, the fixed-RAG baseline, and memory isolation; writes docs/agent_log.md."""

# COMMAND ----------

# MAGIC %md
# MAGIC # Agent experiments (lecture 3, steps 4–5)
# MAGIC
# MAGIC The verification set of `docs/agent_orchestration.md` through the real agent, in the dev
# MAGIC workspace, recorded in `docs/agent_log.md`:
# MAGIC
# MAGIC | Part | What it shows | Homework evidence |
# MAGIC |---|---|---|
# MAGIC | A | V1–V6: which tool the model chose, what came back, the answer and its citations | tool selection, a successful result |
# MAGIC | B | V5 on the out-of-corpus question and V8 against a tight budget | a controlled failure, the limit result |
# MAGIC | C | Four questions through the fixed RAG workflow and through the agent | why the orchestration fits |
# MAGIC | D | V7: a follow-up in the same session by a *new* agent and helper instance; a fresh session; another owner | persistent memory, isolation |
# MAGIC
# MAGIC Every call goes through `course_ops.gateway.chat` (GPT-OSS-120B); timings and tokens are
# MAGIC recorded so the cost of the full path (model iterations plus tool calls) is visible.
# MAGIC Runs locally in VS Code with `GENIE_SPACE_ID` set, or as the `agent_experiments` task.

# COMMAND ----------

import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import nest_asyncio
from databricks.sdk import WorkspaceClient

ROOT = Path.cwd().resolve()
if not (ROOT / "project_config.yml").exists():
    ROOT = ROOT.parent
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from arxiv_curator.config import load_config  # noqa: E402
from evidence_curator.agent import AgentResponse, EvidenceCuratorAgent, citations_in, rag_answer  # noqa: E402
from evidence_curator.gateway import gateway_client  # noqa: E402
from evidence_curator.lakebase import LakebaseConnector  # noqa: E402
from evidence_curator.mcp_tools import GenieSpace  # noqa: E402
from evidence_curator.memory import LakebaseMemory  # noqa: E402
from evidence_curator.reporting import preserve_observations  # noqa: E402
from evidence_curator.tools import ToolRegistry, resolve_therapy_tool, search_papers_tool  # noqa: E402
from evidence_curator.vector_store import LakebaseChunkStore  # noqa: E402


def parameter(name: str, default: str = "") -> str:
    """Read a job parameter from a notebook widget, or from the environment when run locally."""
    try:
        from databricks.sdk.runtime import dbutils

        dbutils.widgets.text(name, default)
        return dbutils.widgets.get(name) or default
    except Exception:  # noqa: BLE001 - no notebook context
        return os.environ.get(name.upper(), default)


log: list[str] = []


def md(*lines: str) -> None:
    """Append lines to the Markdown report."""
    log.extend(lines)


def cell(value: object, width: int = 160) -> str:
    """One table cell: single line, pipes escaped, bounded."""
    text = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value
    text = " ".join(text.split()).replace("|", "/")
    return text if len(text) <= width else text[: width - 1] + "…"


def calls_cell(response: AgentResponse) -> str:
    """Render the tool calls of a turn as `name(args)` with their status."""
    if not response.tool_calls:
        return "none"
    parts = []
    for call in response.tool_calls:
        args = ", ".join(f"{k}={cell(v, 40)}" for k, v in call.arguments.items())
        parts.append(f"{call.name}({args}){'' if call.ok else ' → error'}")
    return "; ".join(parts)


def record(label: str, response: AgentResponse) -> None:
    """Print a turn and add it to the log table."""
    print(
        f"\n=== {label}\n{response.answer}\n-- {response.finish_reason}, {response.iterations} model calls, tools: {calls_cell(response)}, "
        f"{response.latency_s}s, {response.prompt_tokens}+{response.completion_tokens} tokens, citations {response.citations}"
    )
    md(
        f"| {label} | {cell(calls_cell(response), 220)} | {response.finish_reason} | {response.iterations} | "
        f"{response.latency_s} | {response.prompt_tokens}+{response.completion_tokens} | {', '.join(response.citations) or '—'} | "
        f"{cell(response.answer, 400)} |"
    )


nest_asyncio.apply()
env = parameter("env", "dev")
cfg = load_config("project_config.yml", env=env)
w = WorkspaceClient()
genie_space_id = parameter("genie_space_id", cfg.genie_space_id or "")
me = w.current_user.me().user_name
if not genie_space_id:
    raise ValueError(
        "genie_space_id is required: deploy the bundle and pass the space ID (job parameter or GENIE_SPACE_ID)"
    )

client = gateway_client(w)
store = LakebaseChunkStore(cfg, workspace=w)
genie = GenieSpace(workspace=w, space_id=genie_space_id)
registry = ToolRegistry().add(search_papers_tool(store), genie.query_trials_tool(), resolve_therapy_tool())
connector = LakebaseConnector(cfg.lakebase_instance or "", workspace=w)
memory_schema = f"{cfg.catalog}_memory"
memory = LakebaseMemory(connector, schema=memory_schema)
memory.ensure_schema()  # the one-time, privileged step; the agent only reads and inserts afterwards


def new_agent(**kwargs: int) -> EvidenceCuratorAgent:
    """Build a fresh agent instance: nothing carried over in the process."""
    return EvidenceCuratorAgent(client, cfg.llm_endpoint, registry, memory=memory, **kwargs)


started_at = datetime.now(UTC)
print(
    f"env={env} as {me}; model={cfg.llm_endpoint}; tools={registry.names()}; memory={memory_schema}.session_messages (owner {memory.owner})"
)
md(
    "# Agent log",
    "",
    f"Run of {started_at:%Y-%m-%d %H:%M} UTC by `notebooks/agent_experiments.py`, env `{env}`, as `{me}` on "
    f"`{w.config.host}`. Model `{cfg.llm_endpoint}`; tools `{', '.join(registry.names())}`; session memory in "
    f"`{memory_schema}.session_messages` (owner `{memory.owner}`). Budgets: 6 model calls and 8 tool calls per turn "
    "unless stated. Tokens are prompt+completion summed over the turn's model calls; seconds are wall-clock from the laptop.",
    "",
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## A. Tool selection on V1–V6

# COMMAND ----------

TABLE_HEADER = (
    "| Question | Tool calls (in order) | Finish | Model calls | Seconds | Tokens | Citations | Answer |",
    "| --- | --- | --- | --- | --- | --- | --- | --- |",
)
md("## A. Tool selection (V1–V6)", "", *TABLE_HEADER)
verification = [
    ("V1 greeting", "What can you help me with?"),
    ("V2 paper result", "What did SURMOUNT-J report for body weight change with tirzepatide in Japanese participants?"),
    (
        "V3 registry count",
        "How many of our trials are phase 3, and how many of those have posted results, per therapy?",
    ),
    (
        "V4 compare",
        "Compare STEP 1, SURMOUNT-1 and SCALE Obesity and Prediabetes: design from the registry, weight-loss result from the papers.",
    ),
    ("V6 linked publications", "Which publications are linked to NCT03548935?"),
]
responses: dict[str, AgentResponse] = {}
for label, question in verification:
    responses[label] = new_agent().chat(question)
    record(label, responses[label])
md("")

# COMMAND ----------

# MAGIC %md
# MAGIC ## B. Controlled failures: the out-of-corpus question and the budget

# COMMAND ----------

md("## B. Controlled failures", "", *TABLE_HEADER)
v5 = new_agent().chat("oral semaglutide 50 mg OASIS 1 trial weight loss results")
record("V5 out of corpus (OASIS 1)", v5)
v8 = new_agent(max_iterations=2).chat("Search every adverse event in every trial, one trial at a time.")
record("V8 budget: max_iterations=2", v8)
md(
    "",
    f"V5: the answer mentions OASIS: {'OASIS' in v5.answer}; tools called: {calls_cell(v5)}. The search returns "
    "semaglutide passages with high scores for a trial the corpus does not hold, which is why the instruction checks "
    "the named trial against the passages rather than trusting the score.",
    f"V8: finish_reason `{v8.finish_reason}` after {v8.iterations} model calls and {len(v8.tool_calls)} tool calls; "
    "the last call was made without tools after the limit notice, so the answer states what remains unverified.",
    "",
)
assert v8.finish_reason in ("limit", "fallback"), v8.finish_reason

# COMMAND ----------

# MAGIC %md
# MAGIC ## C. The fixed workflow against the agent
# MAGIC
# MAGIC The same four questions through simple RAG (always one hybrid search with the user's words, then
# MAGIC one model call) and through the agent. The workflow retrieves for a greeting and answers a
# MAGIC counting question from fragments; the agent routes.

# COMMAND ----------

md(
    "## C. Fixed RAG workflow versus the agent",
    "",
    "| Question | Workflow: searches | Workflow: citations | Workflow answer | Agent: tool calls | Agent: citations | Agent answer |",
    "| --- | --- | --- | --- | --- | --- | --- |",
)
comparison = [
    ("V1 greeting", "What can you help me with?"),
    ("V2 paper result", "What did SURMOUNT-J report for body weight change with tirzepatide in Japanese participants?"),
    (
        "V3 registry count",
        "How many of our trials are phase 3, and how many of those have posted results, per therapy?",
    ),
    ("V6 linked publications", "Which publications are linked to NCT03548935?"),
]
for label, question in comparison:
    rag_text, _evidence = rag_answer(client, cfg.llm_endpoint, registry, question)
    rag_citations = citations_in(rag_text)
    agent_response = responses[label]
    print(f"\n=== workflow: {label}\n{rag_text}")
    md(
        f"| {label} | 1 (always) | {', '.join(rag_citations) or '—'} | {cell(rag_text, 300)} | "
        f"{cell(calls_cell(agent_response), 160)} | {', '.join(agent_response.citations) or '—'} | {cell(agent_response.answer, 300)} |"
    )
md("")

# COMMAND ----------

# MAGIC %md
# MAGIC ## D. Session memory: continuity, a fresh session, another owner
# MAGIC
# MAGIC Turn 2 is answered by a new agent instance and a new memory helper, so the context can only have
# MAGIC come from Lakebase. The fresh session gets the same follow-up without history; the other owner
# MAGIC reads the first session's ID and gets nothing.

# COMMAND ----------

session_id = f"lecture3-{uuid4().hex[:8]}"
md("## D. Session memory", "", f"Session `{session_id}`, owner `{memory.owner}`.", "", *TABLE_HEADER)
turn1 = new_agent().chat(
    "What did SURMOUNT-OSA report for the apnea-hypopnea index with tirzepatide?", session_id=session_id
)
record("V7 turn 1 (session)", turn1)

memory_again = LakebaseMemory(LakebaseConnector(cfg.lakebase_instance or "", workspace=w), schema=memory_schema)
agent_again = EvidenceCuratorAgent(client, cfg.llm_endpoint, registry, memory=memory_again)
turn2 = agent_again.chat(
    "And what was the corresponding result in the liraglutide sleep-apnoea trial?", session_id=session_id
)
record("V7 turn 2 (new instances, same session)", turn2)

fresh = new_agent().chat(
    "And what was the corresponding result in the liraglutide sleep-apnoea trial?",
    session_id=f"fresh-{uuid4().hex[:8]}",
)
record("V7 follow-up in a fresh session", fresh)

stored = memory_again.load_messages(session_id)
other_owner = LakebaseMemory(
    LakebaseConnector(cfg.lakebase_instance or "", workspace=w), schema=memory_schema, owner="someone.else@example.com"
)
seen_by_other = other_owner.load_messages(session_id)
resaved = memory_again.save_turn(session_id, turn1.turn_id, turn1.messages)
print(
    f"\nstored for {session_id}: {len(stored)} messages {[m['role'] for m in stored]}; other owner sees {len(seen_by_other)}; re-saving turn 1 wrote {resaved} rows"
)
md(
    "",
    f"- Turn 1 saved {turn1.history_saved} rows; turn 2 loaded {turn2.history_loaded} messages through a new helper and saved {turn2.history_saved}.",
    f"- Stored for the session: {len(stored)} messages, roles {[m['role'] for m in stored]} — questions and answers only; "
    f"the answer rows carry the tools used as metadata ({cell([m.get('tools') for m in stored if m['role'] == 'assistant'], 200)}).",
    f"- The fresh session loaded {fresh.history_loaded} messages: the follow-up had no 'corresponding result' to resolve.",
    f"- Owner `someone.else@example.com` loading session `{session_id}`: {len(seen_by_other)} messages.",
    f"- Re-saving turn 1 (same turn_id) wrote {resaved} rows: a retried request cannot duplicate history.",
    "",
)
assert len(stored) == 4, stored
assert seen_by_other == [] and resaved == 0
assert turn2.history_loaded == 2 and fresh.history_loaded == 0

# COMMAND ----------

LOG = ROOT / "docs" / "agent_log.md"
observations = preserve_observations(
    LOG,
    "_Filled in after the run: where the model chose well or badly, what the controlled failures looked like, what the follow-up resolved from history, and the cost of the full path._",
)
md("## Observations", "", observations, "")
LOG.write_text("\n".join(log) + "\n")
print(f"\nwrote {LOG}")
