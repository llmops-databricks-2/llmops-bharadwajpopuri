# Databricks notebook source
# ruff: noqa: ERA001
# Databricks MAGIC comments are executable notebook cells.
"""Retrieval experiments: the same questions through semantic, filtered, keyword and hybrid search; writes docs/retrieval_log.md."""

# COMMAND ----------

# MAGIC %md
# MAGIC # Retrieval experiments
# MAGIC
# MAGIC Homework item 4: run semantic, filtered and hybrid search on the Lakebase copy of `paper_chunks`
# MAGIC and capture what changes in the returned evidence. The question set is fixed and small, as the
# MAGIC lecture recommends: exact trial names and acronyms, a paraphrased concept, a brand name the papers
# MAGIC never use, a date constraint, a cross-therapy question, and one the corpus cannot answer. Each
# MAGIC question names the trial(s) whose paper should surface, so a hit can be counted mechanically from
# MAGIC the chunk's `nct_ids`.
# MAGIC
# MAGIC Modes, all through `evidence_curator.vector_store.LakebaseChunkStore` on the same connection:
# MAGIC
# MAGIC | Mode | What ranks | Notes |
# MAGIC |---|---|---|
# MAGIC | `semantic` | cosine similarity of GTE Large vectors | the query is embedded by the service that embedded the chunks |
# MAGIC | `semantic+filter` | the same, after SQL predicates on therapy / trial / year | the lecture's "put the constraint in the filter, not in the query" |
# MAGIC | `keyword` | PostgreSQL full text: any stemmed term matches, chunks matching every term first, then `ts_rank_cd` | the keyword-only view that AI Search calls FULL_TEXT |
# MAGIC | `keyword all-terms` | the same with every term required (`plainto_tsquery`, the first run's `websearch_to_tsquery` behaviour) | kept for comparison: it returned nothing for half of the questions |
# MAGIC | `hybrid` | reciprocal rank fusion of the semantic and keyword rankings | the fusion AI Search describes for its HYBRID mode |
# MAGIC
# MAGIC Every mode runs on the `section` chunks (the alternative strategy); `semantic` also runs on the
# MAGIC course-baseline `element` chunks so the two chunkings are compared on identical questions.
# MAGIC Runs in VS Code (OAuth profile) or the workspace; writes `docs/retrieval_log.md` when run locally.

# COMMAND ----------

import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from databricks.sdk import WorkspaceClient

ROOT = Path.cwd().resolve()
if not (ROOT / "project_config.yml").exists():
    ROOT = ROOT.parent
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from arxiv_curator.config import load_config  # noqa: E402
from evidence_curator.chunking import BASELINE, SECTIONS  # noqa: E402
from evidence_curator.reporting import preserve_observations  # noqa: E402
from evidence_curator.vector_store import LakebaseChunkStore, SearchFilters  # noqa: E402

cfg = load_config("project_config.yml", env="dev")
w = WorkspaceClient()
store = LakebaseChunkStore(cfg, workspace=w)
print(f"{store.synced_table_id} via {store.project_name} as {w.current_user.me().user_name}")
print(store.inspect())

# COMMAND ----------

# MAGIC %md
# MAGIC ## The question set

# COMMAND ----------

K = 5
QUESTIONS: list[dict[str, Any]] = [
    {
        "id": "Q1",
        "question": "What did SURMOUNT-J report for body weight change with tirzepatide in Japanese participants?",
        "probes": "exact trial name; filter by therapy",
        "expected": {"NCT04844918"},
        "filters": SearchFilters(therapy="tirzepatide"),
    },
    {
        "id": "Q2",
        "question": "Do cardiometabolic risk improvements persist over two years of treatment, and what happens after stopping?",
        "probes": "paraphrased concept, no trial named",
        "expected": {"NCT03693430", "NCT03548987", "NCT03548935"},
        "filters": None,
    },
    {
        "id": "Q3",
        "question": "Wegovy pen ease of use and injection acceptability",
        "probes": "brand name the papers never use (alias resolution belongs to the agent)",
        "expected": {"NCT04074161"},
        "filters": None,
    },
    {
        "id": "Q4",
        "question": "obstructive sleep apnea outcomes",
        "probes": "same question, two therapy filters",
        "expected": {"NCT01557166", "NCT05412004"},
        "filters": SearchFilters(therapy="liraglutide"),
        "filters_alt": SearchFilters(therapy="tirzepatide"),
    },
    {
        "id": "Q5",
        "question": "apnea-hypopnea index AHI reduction with tirzepatide",
        "probes": "technical term plus acronym: keyword strength",
        "expected": {"NCT05412004"},
        "filters": None,
    },
    {
        "id": "Q6",
        "question": "neuropsychiatric adverse events, depression and suicidal ideation during treatment",
        "probes": "cross-therapy safety question",
        "expected": {"NCT01272219", "NCT04184622"},
        "filters": None,
    },
    {
        "id": "Q7",
        "question": "health-related quality of life and physical functioning improvements",
        "probes": "date constraint as a filter rather than words in the query",
        "expected": {"NCT01272219", "NCT04184622", "NCT04657016"},
        "filters": SearchFilters(year_from=2024),
    },
    {
        "id": "Q8",
        "question": "oral semaglutide 50 mg OASIS 1 trial weight loss results",
        "probes": "not in the corpus: what comes back with no threshold",
        "expected": set(),
        "filters": None,
    },
]

# COMMAND ----------

# MAGIC %md
# MAGIC ## Run every mode on every question

# COMMAND ----------


def timed(fn: Any, *args: Any, **kwargs: Any) -> tuple[list[dict[str, Any]], float]:  # noqa: ANN401 - a search method and its arguments
    """Call a search method and return its rows with the wall-clock latency in seconds."""
    started = time.perf_counter()
    rows = fn(*args, **kwargs)
    return rows, round(time.perf_counter() - started, 2)


def hit_rank(rows: list[dict[str, Any]], expected: set[str]) -> int | None:
    """Rank (1-based) of the first row whose paper is linked to an expected trial; None when absent."""
    for rank, row in enumerate(rows, start=1):
        if expected & set((row.get("nct_ids") or "").split(",")):
            return rank
    return None


results: list[dict[str, Any]] = []
for q in QUESTIONS:
    vector = store.embed_query(q["question"])
    runs: list[tuple[str, SearchFilters, Any, dict[str, Any]]] = [
        ("semantic (section)", SearchFilters(strategy=SECTIONS), store.search, {"query_vector": vector}),
        ("semantic (element)", SearchFilters(strategy=BASELINE), store.search, {"query_vector": vector}),
        ("keyword (section)", SearchFilters(strategy=SECTIONS), store.keyword_search, {}),
        (
            "keyword all-terms (section)",
            SearchFilters(strategy=SECTIONS),
            store.keyword_search,
            {"require_all_terms": True},
        ),
        ("hybrid (section)", SearchFilters(strategy=SECTIONS), store.hybrid_search, {"query_vector": vector}),
    ]
    for key in ("filters", "filters_alt"):
        if q.get(key):
            f = q[key]
            label = f"semantic+filter ({', '.join(p for p in [f.therapy, f.nct_id, f'year>={f.year_from}' if f.year_from else None] if p)})"
            runs.append(
                (
                    label,
                    SearchFilters(
                        strategy=SECTIONS, therapy=f.therapy, nct_id=f.nct_id, year_from=f.year_from, year_to=f.year_to
                    ),
                    store.search,
                    {"query_vector": vector},
                )
            )
    for label, filters, method, kwargs in runs:
        rows, latency = timed(method, q["question"], K, filters, **kwargs)
        results.append(
            {
                "qid": q["id"],
                "mode": label,
                "rows": rows,
                "latency_s": latency,
                "hit_rank": hit_rank(rows, q["expected"]),
            }
        )
        top = rows[0] if rows else None
        print(
            f"{q['id']} {label:<42} {latency:>5.2f}s  hit@{K}: {str(results[-1]['hit_rank'] or '-'):<4} "
            f"top: {top['score']:.3f} {top['pmcid']} [{(top['section'] or '')[:24]}]"
            if top
            else f"{q['id']} {label:<42} {latency:>5.2f}s  no rows"
        )

# COMMAND ----------

# MAGIC %md
# MAGIC ## What changed between modes

# COMMAND ----------

by_mode: dict[str, list[dict[str, Any]]] = {}
for r in results:
    by_mode.setdefault(r["mode"], []).append(r)
summary_lines = ["| Mode | questions | hit@5 | mean first-hit rank | mean latency (s) |", "|---|---:|---:|---:|---:|"]
for mode, runs_of_mode in by_mode.items():
    scored = [r for r in runs_of_mode if QUESTIONS[[q["id"] for q in QUESTIONS].index(r["qid"])]["expected"]]
    hits = [r["hit_rank"] for r in scored if r["hit_rank"]]
    summary_lines.append(
        f"| {mode} | {len(runs_of_mode)} | {len(hits)}/{len(scored)} | {sum(hits) / len(hits):.2f} | {sum(r['latency_s'] for r in runs_of_mode) / len(runs_of_mode):.2f} |"
        if hits
        else f"| {mode} | {len(runs_of_mode)} | 0/{len(scored)} | – | {sum(r['latency_s'] for r in runs_of_mode) / len(runs_of_mode):.2f} |"
    )


def top_ids(qid: str, mode: str) -> set[str]:
    """Collect the ids of one run's results."""
    return {row["id"] for r in results if r["qid"] == qid and r["mode"] == mode for row in r["rows"]}


overlaps = []
for q in QUESTIONS:
    a, b = top_ids(q["id"], "semantic (section)"), top_ids(q["id"], "hybrid (section)")
    overlaps.append(len(a & b) / len(a | b) if a | b else 0.0)
summary_lines.append(
    f"\nMean Jaccard overlap of the top-{K} sets, semantic vs hybrid on section chunks: {sum(overlaps) / len(overlaps):.2f}."
)
print("\n".join(summary_lines))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Write the log

# COMMAND ----------

lines = [
    "# Retrieval log",
    "",
    f"Run at {datetime.now(UTC).isoformat(timespec='seconds')} against `{store.synced_table_id}` "
    f"(Lakebase project `{cfg.lakebase_instance}`), queries embedded with `{cfg.embedding_service}`. "
    f"Top-{K} per mode; a *hit* is a result whose paper is linked by the registry to one of the question's expected trials.",
    "",
    "## Questions",
    "",
    "| Id | Question | Probes | Expected trials | Filter |",
    "|---|---|---|---|---|",
]
for q in QUESTIONS:
    f = q.get("filters")
    filter_text = (
        ", ".join(p for p in [f.therapy, f.nct_id, f"year ≥ {f.year_from}" if f and f.year_from else None] if p)
        if f
        else "–"
    )
    if q.get("filters_alt"):
        filter_text += f" / {q['filters_alt'].therapy}"
    lines.append(
        f"| {q['id']} | {q['question']} | {q['probes']} | {', '.join(sorted(q['expected'])) or '–'} | {filter_text} |"
    )
lines += ["", "## Summary", ""] + summary_lines + ["", "## Results by question", ""]
for q in QUESTIONS:
    lines.append(f"### {q['id']}: {q['question']}\n")
    for r in [r for r in results if r["qid"] == q["id"]]:
        lines.append(f"**{r['mode']}** — {r['latency_s']} s, first hit at rank {r['hit_rank'] or '–'}\n")
        if not r["rows"]:
            lines.append("_no rows_\n")
            continue
        lines.append("| # | score | paper | year | section | text |")
        lines.append("|---:|---:|---|---:|---|---|")
        for rank, row in enumerate(r["rows"][:3], start=1):
            extra = f" (v{row['vector_rank'] or '–'}/t{row['text_rank'] or '–'})" if "vector_rank" in row else ""
            lines.append(
                f"| {rank} | {row['score']:.3f}{extra} | {row['pmcid']} | {row['pub_year']} | {(row['section'] or '')[:40]} | "
                f"{row['text'][:140].replace('|', '/').replace(chr(10), ' ')}… |"
            )
        lines.append("")
LOG = ROOT / "docs" / "retrieval_log.md"
observations = preserve_observations(
    LOG,
    "_Filled in after the run: where hybrid beat semantic (and vice versa), what the filters changed, how the two chunkings differed, and what the out-of-corpus question returned._",
)
lines += ["## Observations", "", observations, ""]
LOG.write_text("\n".join(lines) + "\n")
print(f"wrote {ROOT / 'docs' / 'retrieval_log.md'}")
