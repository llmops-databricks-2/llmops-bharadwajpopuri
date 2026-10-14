# Databricks notebook source
# ruff: noqa: ERA001
# Databricks MAGIC comments are executable notebook cells.
"""Experiment: the course model services through Unity Gateway, on Evidence Curator prompts."""

# COMMAND ----------

# MAGIC %md
# MAGIC # Gateway experiment
# MAGIC
# MAGIC Four prompts against `course_ops.gateway.chat` (GPT-OSS-120B) and one against
# MAGIC `course_ops.gateway.embed` (GTE Large), through the workspace's Unity Gateway at
# MAGIC `<host>/ai-gateway/mlflow/v1`, with `WorkspaceClient` doing the authentication.
# MAGIC
# MAGIC The prompts are the agent's future jobs done by hand: summarise a registry record, compare
# MAGIC two records, answer a results question **without** context (to see what the model does when it
# MAGIC has no evidence), and resolve drug aliases. Each call records the response, token usage and
# MAGIC latency; the table at the end goes into `docs/gateway_experiment_log.md` when run locally.
# MAGIC
# MAGIC Runs locally in VS Code (the Databricks extension's `.venv` and OAuth profile) or in the
# MAGIC workspace. Nothing here prints a token: the bearer header is added per request by the SDK.

# COMMAND ----------

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from databricks.sdk import WorkspaceClient

# When the project wheel is not installed (interactive runs), import from the synced source tree.
ROOT = Path.cwd().resolve()
if not (ROOT / "project_config.yml").exists():
    ROOT = ROOT.parent  # the notebook runs from notebooks/, one level below the repo root
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from arxiv_curator.config import load_config  # noqa: E402
from evidence_curator.gateway import ChatResult, chat, gateway_client  # noqa: E402
from evidence_curator.seed import seed_by_id  # noqa: E402
from evidence_curator.trials import fetch_studies, flatten_study  # noqa: E402

cfg = load_config("project_config.yml", env="dev")
w = WorkspaceClient()
print(f"Workspace {w.config.host} as {w.current_user.me().user_name}; auth type: {w.config.auth_type}")
client = gateway_client(w)
print(f"Gateway base URL: {client.base_url}")
print(f"Chat service: {cfg.llm_endpoint}; embedding service: {cfg.embedding_endpoint}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Context for the prompts: two registry records, fetched live
# MAGIC
# MAGIC The same flattening the data-preparation job uses, so the model sees exactly what the
# MAGIC `query_trials` tool will return later. Only design fields are passed: no reported results.

# COMMAND ----------

CONTEXT_FIELDS = [
    "nct_id",
    "acronym",
    "official_title",
    "phase",
    "overall_status",
    "lead_sponsor",
    "interventions",
    "enrollment_count",
    "allocation",
    "masking",
    "primary_outcomes",
    "start_date",
    "primary_completion_date",
    "minimum_age",
    "maximum_age",
    "has_results",
]

seeds = seed_by_id()
studies = fetch_studies(["NCT03548935", "NCT04184622"])
records = {}
for study in studies:
    row = flatten_study(study, seeds[study["protocolSection"]["identificationModule"]["nctId"]], datetime.now(UTC))
    records[row["nct_id"]] = {k: row[k] for k in CONTEXT_FIELDS}
context = json.dumps(records, indent=1)
print(f"{len(records)} records, {len(context)} characters of context")

# COMMAND ----------

SYSTEM = (
    "You are an evidence curator for pharma R&D. Answer only from the registry records provided. "
    "Cite every fact as (NCT ID, field). If the records do not contain the answer, say "
    "'not found in the dataset'. Never rank therapies across separate trials."
)

PROMPTS = {
    "summarise_record": (
        "Summarise the design of trial NCT03548935 in five lines: population, intervention and comparator, "
        "primary endpoint and its time frame, enrollment, and status. Cite each fact.\n\nRecords:\n" + context
    ),
    "compare_two_trials": (
        "Compare NCT03548935 and NCT04184622 side by side in a markdown table: population age limits, "
        "intervention, comparator, primary endpoint, treatment duration, enrollment. Add one sentence "
        "stating whether these results can be compared head to head.\n\nRecords:\n" + context
    ),
    "results_without_context": (
        "What mean percentage weight loss did STEP 1 and SURMOUNT-1 report at their primary endpoints, "
        "and in which journals were the results published? Cite your sources."
    ),
    "alias_resolution": (
        "Group these names by the drug they refer to and give the INN for each group: Wegovy, NN9535, "
        "Zepbound, LY3298176, Saxenda, semaglutide 2.4 mg, Mounjaro, Victoza, liraglutide 3.0 mg."
    ),
}

results: list[ChatResult] = []
for label, prompt in PROMPTS.items():
    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}]
    if label == "results_without_context":
        # No system prompt either: the point is to see the model's default behaviour without evidence.
        messages = [{"role": "user", "content": prompt}]
    result = chat(client, cfg.llm_endpoint, messages, prompt_label=label, max_tokens=1024, reasoning_effort="low")
    results.append(result)
    print(f"=== {label} | {result.latency_s}s | tokens in/out/total: ", end="")
    print(f"{result.prompt_tokens}/{result.completion_tokens}/{result.total_tokens} | finish: {result.finish_reason}")
    if result.reasoning:
        print(f"[reasoning summary] {result.reasoning}")
    print(result.content)
    print()

# COMMAND ----------

# MAGIC %md
# MAGIC ## Embedding service
# MAGIC
# MAGIC A question and two passages: the vector dimension tells us what to provision in pgvector,
# MAGIC and the cosine similarities show the question lands nearer the relevant passage.

# COMMAND ----------

texts = [
    "Which trials compare semaglutide with liraglutide for obesity?",
    "STEP 8 was a phase 3 trial of once-weekly semaglutide 2.4 mg versus once-daily liraglutide 3.0 mg in adults with overweight or obesity.",
    "SURMOUNT-OSA evaluated tirzepatide in adults with obesity and moderate-to-severe obstructive sleep apnoea.",
]
embedding_response = client.embeddings.create(model=cfg.embedding_endpoint, input=texts)
vectors = [d.embedding for d in embedding_response.data]


def cosine(a: list[float], b: list[float]) -> float:
    """Cosine similarity of two vectors (the Python-only version; pgvector will do this in SQL)."""
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm = (sum(x * x for x in a) ** 0.5) * (sum(y * y for y in b) ** 0.5)
    return dot / norm


embedding_usage = embedding_response.usage.model_dump() if embedding_response.usage else {}
print(f"{len(vectors)} vectors of dimension {len(vectors[0])}; usage: {embedding_usage}")
print(f"question vs STEP 8 passage:      {cosine(vectors[0], vectors[1]):.3f}")
print(f"question vs SURMOUNT-OSA passage: {cosine(vectors[0], vectors[2]):.3f}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Record

# COMMAND ----------

lines = [
    "# Gateway experiment log",
    "",
    f"Run at {datetime.now(UTC).isoformat(timespec='seconds')} against `{cfg.llm_endpoint}` (chat) and "
    f"`{cfg.embedding_endpoint}` (embeddings) via `{client.base_url}`.",
    "",
    "| Prompt | Latency (s) | Prompt tokens | Completion tokens | Total | Finish |",
    "|---|---:|---:|---:|---:|---|",
]
lines += [
    f"| {r.prompt_label} | {r.latency_s} | {r.prompt_tokens} | {r.completion_tokens} | {r.total_tokens} | {r.finish_reason} |"
    for r in results
]
lines += [
    "",
    f"Embeddings: {len(vectors)} inputs, dimension {len(vectors[0])}, usage {embedding_usage}.",
    "",
    "## Responses",
    "",
]
for r in results:
    lines += [f"### {r.prompt_label}", ""]
    if r.reasoning:
        lines += [f"_Reasoning summary returned by the model: {r.reasoning}_", ""]
    lines += [r.content, "", f"Usage detail: `{r.raw_usage}`", ""]
lines += ["## Limitations observed", "", "_Fill in after the run: see the PR description._", ""]

log = "\n".join(lines)
print(log)
docs_dir = ROOT / "docs"
if docs_dir.is_dir():
    (docs_dir / "gateway_experiment_log.md").write_text(log)
    print(f"Saved to {docs_dir / 'gateway_experiment_log.md'}")
