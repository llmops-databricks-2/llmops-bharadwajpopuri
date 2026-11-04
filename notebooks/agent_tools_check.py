# Databricks notebook source
# ruff: noqa: ERA001
# Databricks MAGIC comments are executable notebook cells.
"""Tool check for the agent: every callable tested directly, then the registry gate, then Genie through MCP; writes docs/agent_tools_log.md."""

# COMMAND ----------

# MAGIC %md
# MAGIC # Agent tools check (lecture 3, step 3)
# MAGIC
# MAGIC The lecture's rule: test the callable independently before testing model selection. This
# MAGIC notebook runs each tool of `docs/agent_orchestration.md` directly, with the inputs of the small
# MAGIC verification set (normal values, a malformed input, a question outside the corpus), and records
# MAGIC what came back in `docs/agent_tools_log.md`. No model is involved: a failure here is a
# MAGIC configuration, permission or tool problem, not model behaviour — the "diagnose one layer at a
# MAGIC time" table of the lecture notes.
# MAGIC
# MAGIC | Section | Layer | What a failure means |
# MAGIC |---|---|---|
# MAGIC | 1 | `resolve_therapy` | pure function: a bug in the alias table |
# MAGIC | 2 | `search_papers` | Lakebase credential, endpoint, synced table, embedding service |
# MAGIC | 3 | `ToolRegistry.execute` | the argument gate the model's requests pass through |
# MAGIC | 4 | Genie through MCP | space permission, warehouse, table grants, the managed MCP server |
# MAGIC | 5 | Genie through the SDK | the space itself: when section 4 fails and this works, MCP is the problem |
# MAGIC
# MAGIC Runs as a job (`agent_tools_check`, space ID passed from the bundle) or locally in VS Code with
# MAGIC `GENIE_SPACE_ID` set from `databricks bundle summary`; the Markdown log is written when run locally.

# COMMAND ----------

import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import nest_asyncio
from databricks.sdk import WorkspaceClient

ROOT = Path.cwd().resolve()
if not (ROOT / "project_config.yml").exists():
    ROOT = ROOT.parent
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from arxiv_curator.config import load_config  # noqa: E402
from evidence_curator.mcp_tools import GenieSpace, genie_server_url  # noqa: E402
from evidence_curator.reporting import preserve_observations  # noqa: E402
from evidence_curator.tools import ToolRegistry, resolve_therapy_tool, search_papers_tool  # noqa: E402
from evidence_curator.vector_store import LakebaseChunkStore  # noqa: E402


def parameter(name: str, default: str = "") -> str:
    """Read a job parameter from a notebook widget, or from the environment when run locally."""
    try:
        from databricks.sdk.runtime import dbutils

        dbutils.widgets.text(name, default)
        return dbutils.widgets.get(name) or default
    except Exception:  # noqa: BLE001 - no notebook context: VS Code or plain Python
        return os.environ.get(name.upper(), default)


log: list[str] = []  # the Markdown report, section by section


def md(*lines: str) -> None:
    """Append lines to the Markdown report."""
    log.extend(lines)


def cell(value: object, width: int = 120) -> str:
    """One table cell: single line, pipes escaped, bounded."""
    text = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value
    text = " ".join(text.split()).replace("|", "/")
    return text if len(text) <= width else text[: width - 1] + "…"


def show(label: str, payload: str, keep: int = 1200) -> dict[str, Any]:
    """Print a tool result compactly and return it parsed."""
    data = json.loads(payload)
    text = json.dumps(data, ensure_ascii=False)
    print(f"\n--- {label}\n{text if len(text) <= keep else text[:keep] + ' …'}")
    return data


nest_asyncio.apply()  # DatabricksMCPClient uses asyncio.run, which needs this inside a notebook's loop
env = parameter("env", "dev")
cfg = load_config("project_config.yml", env=env)
w = WorkspaceClient()
genie_space_id = parameter("genie_space_id", cfg.genie_space_id or "")
me = w.current_user.me().user_name
started_at = datetime.now(UTC)
print(
    f"env={env} as {me}; chat={cfg.llm_endpoint}; lakebase={cfg.lakebase_instance}; genie_space_id={genie_space_id or '(none)'}"
)
md(
    "# Agent tools check",
    "",
    f"Run of {started_at:%Y-%m-%d %H:%M} UTC by `notebooks/agent_tools_check.py`, env `{env}`, as `{me}` "
    f"(workspace `{w.config.host}`). Every tool of [the orchestration design](agent_orchestration.md) called "
    "directly, no model involved: the layer-by-layer check the lecture asks for before a model is allowed to "
    "choose a tool. Timings are wall-clock seconds from the laptop, including the Lakebase and gateway round trips.",
    "",
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. resolve_therapy — a pure function

# COMMAND ----------

resolve = resolve_therapy_tool()
md("## 1. `resolve_therapy`", "", "| Input | Therapy | Matched |", "| --- | --- | --- |")
for name in ("Wegovy", "LY3298176", "Semaglutide 2.4 mg", "Saxenda", "Placebo", "GLP-1 receptor agonist"):
    out = show(f"resolve_therapy({name!r})", resolve.exec_fn(name=name))
    md(f"| {name} | {out['therapy']} | {out['matched']} |")
md("")
assert json.loads(resolve.exec_fn(name="Wegovy"))["therapy"] == "semaglutide"
assert json.loads(resolve.exec_fn(name="Placebo"))["matched"] is False

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. search_papers — hybrid search on the Lakebase chunk table
# MAGIC
# MAGIC V2 of the verification set with a therapy filter, a year-filtered question, a malformed trial ID,
# MAGIC an unknown therapy, and V5, the question the corpus cannot answer (OASIS 1 is not among the 24 papers).

# COMMAND ----------

store = LakebaseChunkStore(cfg, workspace=w)
search = search_papers_tool(store)
print(f"store: {store.synced_table_id} via {store.project_name}")
md(
    "## 2. `search_papers`",
    "",
    f"Hybrid search on `{store.synced_table_id}` in `{store.project_name}`, `section` chunks, query embedded by "
    f"`{cfg.embedding_service}`.",
    "",
    "| Check | Arguments | Seconds | Outcome |",
    "| --- | --- | --- | --- |",
)

checks = [
    (
        "V2 SURMOUNT-J, therapy filter from a brand name",
        {
            "query": "SURMOUNT-J body weight change tirzepatide Japanese participants",
            "therapy": "Zepbound",
            "num_results": 3,
        },
    ),
    (
        "quality of life, year_from=2024",
        {
            "query": "health-related quality of life and physical functioning improvements",
            "year_from": 2024,
            "num_results": 3,
        },
    ),
    ("malformed nct_id", {"query": "weight loss", "nct_id": "NCT123"}),
    ("unknown therapy", {"query": "weight loss", "therapy": "orforglipron"}),
    (
        "V5 out of corpus: OASIS 1",
        {"query": "oral semaglutide 50 mg OASIS 1 trial weight loss results", "num_results": 3},
    ),
]
hits_log: list[str] = []
for label, kwargs in checks:
    started = time.perf_counter()
    out = show(label, search.exec_fn(**kwargs))
    elapsed = round(time.perf_counter() - started, 2)
    if "error" in out:
        md(f"| {label} | `{cell(kwargs)}` | {elapsed} | error: {cell(out['error'])} — hint: {cell(out['hint'])} |")
        continue
    md(
        f"| {label} | `{cell(kwargs)}` | {elapsed} | {len(out['results'])} passages; filters applied {cell(out['filters'])} |"
    )
    hits_log += [
        f"**{label}**",
        "",
        "| Score | PMCID | Year | Trials | Section | Excerpt |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for hit in out["results"]:
        print(
            f"    {hit['score']:.4f}  {hit['pmcid']}  {hit['pub_year']}  {hit['nct_ids']}  {hit['section']!s:.30}  {hit['text'][:90]}…"
        )
        hits_log.append(
            f"| {hit['score']:.4f} | {hit['pmcid']} | {hit['pub_year']} | {', '.join(hit['nct_ids'])} | "
            f"{cell(hit['section'] or '', 40)} | {cell(hit['text'], 140)} |"
        )
    hits_log.append("")
md("", *hits_log)

v2 = json.loads(
    search.exec_fn(
        query="SURMOUNT-J body weight change tirzepatide Japanese participants", therapy="tirzepatide", num_results=3
    )
)
assert v2["results"], "V2 returned nothing: the synced table is empty or the embedding service failed"
assert all("tirzepatide" in hit["therapies"] for hit in v2["results"]), "therapy filter did not apply"
assert any("NCT04844918" in hit["nct_ids"] for hit in v2["results"]), "SURMOUNT-J (NCT04844918) not in the top 3"
v5 = json.loads(search.exec_fn(query="oral semaglutide 50 mg OASIS 1 trial weight loss results", num_results=3))
oasis_mentioned = any("OASIS" in hit["text"] for hit in v5["results"])
print("\nV5 entity check: does any returned passage mention OASIS?", oasis_mentioned)
md(
    f"V5 entity check: a returned passage mentions OASIS — **{oasis_mentioned}**. The search returns the nearest "
    f"semaglutide passages (top score {v5['results'][0]['score'] if v5['results'] else 'n/a'}) for a trial the corpus "
    "does not hold; the agent's instruction to check the named trial against `nct_ids` and the text is what turns "
    "this into an honest 'not in the corpus' answer.",
    "",
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. The registry gate — what a model's request goes through

# COMMAND ----------

registry = ToolRegistry().add(search, resolve)
print("tools:", registry.names())
print(json.dumps(registry.specs(), indent=1)[:1500], "…")
md("## 3. The registry gate", "", "| Request | Result |", "| --- | --- |")
for label, name, arguments in [
    ("unknown tool", "delete_everything", "{}"),
    ("bad JSON", "search_papers", "{not json"),
    ("unknown argument", "search_papers", json.dumps({"query": "x", "top_k": 3})),
    ("wrong type", "search_papers", json.dumps({"query": "x", "num_results": "three"})),
    ("valid call", "resolve_therapy", json.dumps({"name": "Mounjaro"})),
]:
    out = show(label, registry.execute(name, arguments))
    md(f"| {label}: `{name}` `{cell(arguments, 60)}` | {cell(out, 200)} |")
md("")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. query_trials — the Genie space through its managed MCP server
# MAGIC
# MAGIC Discovery first: the tool names and input schemas the server really publishes (the wrapper names
# MAGIC its arguments from this schema). Then V3, a follow-up in the same conversation, and V6.

# COMMAND ----------


def genie_row(label: str, result: dict[str, Any], seconds: float) -> None:
    """One line of the Genie table in the log."""
    if "error" in result:
        md(f"| {label} | {seconds:.1f} | error | {cell(result['error'], 160)} | | |")
        return
    md(
        f"| {label} | {seconds:.1f} | {result.get('status')} ({result.get('polls', 0)} polls) | "
        f"{cell(result.get('answer') or '', 160)} | `{cell(result.get('sql') or '', 160)}` | "
        f"{cell(result.get('rows') or [], 160)} |"
    )


if not genie_space_id:
    print(
        "no genie_space_id: deploy the bundle and pass the space ID (job parameter or GENIE_SPACE_ID); skipping 4 and 5"
    )
    md("## 4. `query_trials` (Genie through MCP)", "", "_Skipped: no Genie space ID was passed._", "")
else:
    genie = GenieSpace(workspace=w, space_id=genie_space_id)
    print("server:", genie_server_url(w, genie_space_id))
    md(
        "## 4. `query_trials` (Genie through MCP)",
        "",
        f"Space `{genie_space_id}`, server `{genie_server_url(w, genie_space_id)}`. Tools the server publishes:",
        "",
    )
    for tool in genie.discover():
        print(f"\n{tool.name}: {tool.description}\n  inputSchema: {json.dumps(tool.inputSchema)}")
        md(f"- `{tool.name}` — {cell(tool.description or '', 200)}; input schema `{cell(tool.inputSchema, 300)}`")
    md("", "| Question | Seconds | Status | Answer | SQL | Rows |", "| --- | --- | --- | --- | --- | --- |")
    query_trials = genie.query_trials_tool()
    registry.add(query_trials)

    started = time.perf_counter()
    v3 = show(
        "V3 phase 3 counts",
        query_trials.exec_fn(
            question="How many trials are phase 3 per therapy, and how many of those have posted results?"
        ),
        keep=3000,
    )
    genie_row("V3 phase 3 per therapy, with posted results", v3, time.perf_counter() - started)
    print(f"  status={v3.get('status')}, polls={v3.get('polls')}, sql={v3.get('sql')}, rows={v3.get('rows')}")

    if v3.get("conversation_id"):
        started = time.perf_counter()
        followup = show(
            "follow-up in the same conversation",
            query_trials.exec_fn(
                question="Of those, which ones started after 2022?", conversation_id=v3["conversation_id"]
            ),
            keep=2000,
        )
        genie_row("follow-up, same conversation: which started after 2022", followup, time.perf_counter() - started)

    started = time.perf_counter()
    v6 = show(
        "V6 publications of NCT03548935",
        query_trials.exec_fn(
            question="Which publications are linked to NCT03548935? Show PMID, reference type and citation."
        ),
        keep=2500,
    )
    genie_row("V6 publications linked to NCT03548935", v6, time.perf_counter() - started)

    gate = show("through the gate: empty question", registry.execute("query_trials", json.dumps({"question": "  "})))
    md("", f"Through the gate with an empty question: {cell(gate, 160)}", "")
    assert v3.get("status") in ("COMPLETED", "PENDING") or v3.get("error"), v3

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5. Cross-check: the same space through the SDK
# MAGIC
# MAGIC Notebook 3.2b's path. If section 4 failed and this works, the problem is the MCP server or its
# MAGIC permission path; if both fail the same way, it is the space, the warehouse or the table grants.

# COMMAND ----------

if genie_space_id:
    space = w.genie.get_space(space_id=genie_space_id)
    print(f"space {space.space_id}: title={space.title!r} warehouse={space.warehouse_id}")
    started = time.perf_counter()
    conversation = w.genie.start_conversation_and_wait(
        space_id=genie_space_id, content="Which trials compare two therapies head to head?"
    )
    seconds = time.perf_counter() - started
    message = conversation.as_dict()
    print(f"  {seconds:.1f} s, status={message.get('status')}")
    sdk_sql, sdk_text = "", ""
    for attachment in message.get("attachments", []):
        if "query" in attachment:
            sdk_sql = attachment["query"].get("query", "")
            print("  sql:", sdk_sql)
        if "text" in attachment:
            sdk_text = attachment["text"].get("content", "")
            print("  text:", sdk_text)
    md(
        "## 5. The same space through the SDK",
        "",
        f"`w.genie.start_conversation_and_wait` on space `{space.title}` (warehouse `{space.warehouse_id}`): "
        f'"Which trials compare two therapies head to head?" → status `{message.get("status")}` in {seconds:.1f} s; '
        f"SQL `{cell(sdk_sql, 200)}`; text: {cell(sdk_text, 200)}",
        "",
    )

# COMMAND ----------

LOG = ROOT / "docs" / "agent_tools_log.md"
observations = preserve_observations(
    LOG,
    "_Filled in after the run: what the discovered Genie schema looked like, where a tool misbehaved, what the search returned for the out-of-corpus question._",
)
md("## Observations", "", observations, "")
LOG.write_text("\n".join(log) + "\n")
print(f"\nwrote {LOG}\nDone: tools checked directly, before any model chooses them.")
