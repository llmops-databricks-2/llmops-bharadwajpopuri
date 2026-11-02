# Databricks notebook source
# ruff: noqa: ERA001
# Databricks MAGIC comments are executable notebook cells.
"""Inspection: parsed documents, chunk quality and sizes for both strategies; writes docs/chunking_report.md."""

# COMMAND ----------

# MAGIC %md
# MAGIC # Chunk inspection
# MAGIC
# MAGIC The course's notebook 2.3 for this project, run after the `prepare_papers` job. It answers the
# MAGIC first two homework items with numbers and samples:
# MAGIC
# MAGIC 1. **Inspect the processed documents and chunk tables.** What the parser produced per paper, a
# MAGIC    side-by-side of a few chunks with their page in the PDF, and the structure the baseline loses
# MAGIC    (reference entries as chunks, running headers, fragments, tables dropped).
# MAGIC 2. **Review chunk sizes and the alternative strategy.** Length distributions in characters and
# MAGIC    tokens per strategy; the embedding model's own token counts on a sample (from the gateway's usage
# MAGIC    report, not the four-characters rule); and a probe of GTE Large's input limit.
# MAGIC
# MAGIC Runs in VS Code (Databricks Connect for the tables, the OAuth profile for the gateway) or in the
# MAGIC workspace. Writes `docs/corpus.md` and `docs/chunking_report.md` when run locally.

# COMMAND ----------

import json
import os
import random
import re
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
from databricks.sdk import WorkspaceClient
from pyspark.sql import SparkSession

ROOT = Path.cwd().resolve()
if not (ROOT / "project_config.yml").exists():
    ROOT = ROOT.parent
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from arxiv_curator.config import load_config  # noqa: E402
from evidence_curator.chunking import (  # noqa: E402
    BASELINE,
    SECTIONS,
    element_type_counts,
    estimate_tokens,
    length_stats,
    parse_elements,
)
from evidence_curator.gateway import count_tokens, gateway_client  # noqa: E402
from evidence_curator.reporting import preserve_observations  # noqa: E402

cfg = load_config("project_config.yml", env="dev")
schema_name = cfg.full_schema_name
if "DATABRICKS_RUNTIME_VERSION" in os.environ:  # a workspace notebook: the session is given
    spark = SparkSession.builder.getOrCreate()
else:  # VS Code: Databricks Connect on serverless, authenticated by the OAuth profile
    from databricks.connect import DatabricksSession

    spark = DatabricksSession.builder.serverless(True, usage_policy_id=cfg.usage_policy_id).getOrCreate()
w = WorkspaceClient()
client = gateway_client(w)
print(f"{schema_name} as {w.current_user.me().user_name}; embedding service {cfg.embedding_service}")

GTE_WINDOW = 8192  # tokens, databricks-gte-large-en (lecture table); verified below
report: list[str] = [
    f"# Chunking report\n\nGenerated {datetime.now(UTC).isoformat(timespec='seconds')} from `{schema_name}`.\n"
]

# COMMAND ----------

# MAGIC %md
# MAGIC ## The corpus

# COMMAND ----------

papers = (
    spark.table(f"{schema_name}.papers")
    .select("pmcid", "therapies", "pub_year", "journal", "license", "reference_types", "nct_ids", "title")
    .orderBy("therapies", "pub_year", "pmcid")
    .toPandas()
)
print(papers.to_string(max_colwidth=60))
corpus_lines = [
    "# The paper corpus\n",
    f"{len(papers)} open-access papers from PubMed Central, selected by `evidence_curator.papers` from the publication "
    "links ClinicalTrials.gov records for the pinned trials (see the `ingest_papers` task for the resolution funnel). "
    "Licence as PubMed Central's dataset reports it; `reference_types` is how the registry labels the paper's link to "
    "each trial (RESULT: reports the trial's results; DERIVED: found by PubMed linkage; BACKGROUND: cited by the sponsor).\n",
    "| PMCID | Therapies | Year | Journal | Licence | Link | Trials | Title |",
    "|---|---|---:|---|---|---|---|---|",
]
for row in papers.itertuples():
    corpus_lines.append(
        f"| {row.pmcid} | {row.therapies} | {row.pub_year} | {row.journal} | {row.license} | {row.reference_types} | "
        f"{row.nct_ids.replace(',', ', ')} | {row.title} |"
    )
covered = sorted({n for ncts in papers.nct_ids for n in ncts.split(",")})
corpus_lines.append(f"\nTrials with at least one paper in the corpus: {len(covered)} of 30.\n")
(ROOT / "docs" / "corpus.md").write_text("\n".join(corpus_lines) + "\n")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1a. What the parser produced
# MAGIC
# MAGIC Element types per paper. Scientific PDFs carry a lot of furniture (page headers and footers,
# MAGIC figure placeholders); the `text` count is what the baseline strategy turns into chunks.

# COMMAND ----------

parsed = {
    row["path"].rsplit("/", 1)[-1].removesuffix(".pdf"): json.loads(row["parsed_content"])
    for row in spark.table(f"{schema_name}.parsed_papers").collect()
}
elements_by_paper = {pmcid: parse_elements(payload) for pmcid, payload in parsed.items() if pmcid in set(papers.pmcid)}
type_rows = []
for pmcid, elements in sorted(elements_by_paper.items()):
    counts = element_type_counts(elements)
    pages = (parsed[pmcid].get("document") or {}).get("pages") or parsed[pmcid].get("pages") or []
    type_rows.append({"pmcid": pmcid, "pages": len(pages), **counts})
all_types = sorted({k for r in type_rows for k in r if k not in {"pmcid", "pages"}})
report.append("## Parsed documents: element types per paper\n")
report.append("| PMCID | pages | " + " | ".join(all_types) + " |")
report.append("|---|---:|" + "---:|" * len(all_types))
for r in type_rows:
    report.append(f"| {r['pmcid']} | {r['pages']} | " + " | ".join(str(r.get(t, 0)) for t in all_types) + " |")
    print(r)
totals = Counter()
for r in type_rows:
    totals.update({t: r.get(t, 0) for t in all_types})
report.append(f"\nTotals over {len(type_rows)} papers: {dict(totals)}\n")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1b. Chunks beside their source
# MAGIC
# MAGIC One paper per therapy: the first elements as the parser read them, then the first chunks of each
# MAGIC strategy with their page. Open the PDF from the volume at that page and compare: reading order,
# MAGIC broken words, split sentences, missing captions, table cells. This is the manual look the lecture
# MAGIC asks for before trusting any automated check.

# COMMAND ----------

chunks = (
    spark.table(f"{schema_name}.paper_chunks")
    .select(
        "id",
        "pmcid",
        "chunk_seq",
        "strategy",
        "kind",
        "section",
        "page",
        "n_chars",
        "n_tokens_est",
        "text",
        "therapies",
    )
    .toPandas()
)
print(f"{len(chunks)} chunks: {chunks.groupby('strategy').size().to_dict()}")

samples = papers.groupby("therapies").head(1).pmcid.tolist()[:3]
for pmcid in samples:
    print(f"\n==================== {pmcid}  /Volumes/{cfg.catalog}/{cfg.schema}/{cfg.volume}/pmc_papers/{pmcid}.pdf")
    print("--- parser elements 0-14 (type, page, content[:110])")
    for e in elements_by_paper[pmcid][:15]:
        print(f"  {e.id:>3} {e.type:<15} p{e.page}  {e.content[:110]!r}")
    for strategy in (BASELINE, SECTIONS):
        subset = chunks[(chunks.pmcid == pmcid) & (chunks.strategy == strategy)].sort_values("chunk_seq").head(6)
        print(f"--- {strategy} chunks 0-5")
        for c in subset.itertuples():
            print(
                f"  seq {c.chunk_seq:>3} p{c.page} {c.kind:<5} [{(c.section or '')[:28]:<28}] {c.n_chars:>5} chars  {c.text[:100]!r}"
            )

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1c. Structure the baseline loses (and whether the alternative recovers it)
# MAGIC
# MAGIC Automated checks over all chunks: reference-list entries that became chunks, running headers
# MAGIC repeated across pages, fragments under 50 tokens, hyphenation left unrepaired, exact duplicates,
# MAGIC chunks still exceeding the embedding window, and how many tables reached the index.

# COMMAND ----------

REFERENCE_ENTRY = re.compile(r"^\s*(\[?\d{1,3}[\].)]\s+)?[A-Z][A-Za-z'\-]+\s+[A-Z]{1,3}[,.].{0,80}\b(19|20)\d{2}\b")
HYPHEN_GAP = re.compile(r"\w- \w")


def quality_checks(frame: pd.DataFrame) -> dict[str, int | float]:
    """Count the usual chunk defects in one strategy's rows."""
    texts = frame.text.tolist()
    short = frame[frame.n_tokens_est < 50]
    repeated_short = {t for t, n in Counter(s for s in texts if len(s) < 80).items() if n >= 3}
    return {
        "chunks": len(frame),
        "papers": frame.pmcid.nunique(),
        "reference_entries": int(sum(bool(REFERENCE_ENTRY.match(t)) for t in texts)),
        "fragments_under_50_tokens": len(short),
        "running_headers_repeated_3x": len(repeated_short),
        "hyphen_artifacts": int(sum(bool(HYPHEN_GAP.search(t)) for t in texts)),
        "exact_duplicates": int(len(texts) - len(set(texts))),
        "over_window_estimate": int((frame.n_tokens_est > GTE_WINDOW).sum()),
        "tables": int((frame.kind == "table").sum()),
        "sections_named": int(frame.section.notna().sum()),
    }


quality = {strategy: quality_checks(chunks[chunks.strategy == strategy]) for strategy in (BASELINE, SECTIONS)}
report.append("## Chunk quality checks\n")
report.append("| Check | element (course baseline) | section (alternative) |")
report.append("|---|---:|---:|")
for key in quality[BASELINE]:
    report.append(f"| {key} | {quality[BASELINE][key]} | {quality[SECTIONS][key]} |")
report.append("")
print(json.dumps(quality, indent=2))
print("\nExamples of reference entries indexed as chunks (baseline):")
for t in [t for t in chunks[chunks.strategy == BASELINE].text if REFERENCE_ENTRY.match(t)][:5]:
    print("  ", t[:120])

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2a. Length distributions
# MAGIC
# MAGIC Characters and estimated tokens per strategy. `over_limit` counts chunks whose estimate exceeds
# MAGIC the model's window; `under_50` counts fragments too short to carry a claim.

# COMMAND ----------

BUCKETS = [(0, 50), (50, 128), (128, 256), (256, 384), (384, 512), (512, 1024), (1024, GTE_WINDOW), (GTE_WINDOW, 10**9)]
report.append("## Length distributions\n")
report.append("| Strategy | chunks | min | p50 | p95 | max | mean | under 50 tokens | over window |")
report.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
for strategy in (BASELINE, SECTIONS):
    frame = chunks[chunks.strategy == strategy]
    chars = length_stats(frame.n_chars.tolist())
    tokens = length_stats(frame.n_tokens_est.tolist(), limit=GTE_WINDOW)
    report.append(
        f"| {strategy} (chars) | {chars['count']} | {chars['min']} | {chars['p50']} | {chars['p95']} | {chars['max']} | {chars['mean']} | | |"
    )
    report.append(
        f"| {strategy} (tokens, est.) | {tokens['count']} | {tokens['min']} | {tokens['p50']} | {tokens['p95']} | {tokens['max']} | "
        f"{tokens['mean']} | {(frame.n_tokens_est < 50).sum()} | {tokens['over_limit']} |"
    )
    histogram = {
        f"{lo}-{hi if hi < 10**9 else ''}": int(((frame.n_tokens_est >= lo) & (frame.n_tokens_est < hi)).sum())
        for lo, hi in BUCKETS
    }
    print(
        f"{strategy}: chars {chars}\n{' ' * len(strategy)}  tokens {tokens}\n{' ' * len(strategy)}  histogram {histogram}"
    )
    report.append(f"\n`{strategy}` estimated-token histogram: {histogram}\n")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2b. The model's own token counts, and its input limit
# MAGIC
# MAGIC The four-characters rule is a planning estimate. The gateway returns `usage.prompt_tokens` for
# MAGIC every embedding call, which is the model's tokenizer counting. A stratified sample (the shortest,
# MAGIC the longest and random chunks of each strategy) is embedded one at a time to compare the two, and
# MAGIC two synthetic inputs probe the window: one comfortably inside 8,192 tokens, one far beyond it, to
# MAGIC see whether the service rejects or silently truncates.

# COMMAND ----------

random.seed(7)
sample_rows = []
for strategy in (BASELINE, SECTIONS):
    frame = chunks[chunks.strategy == strategy].sort_values("n_chars")
    picks = (
        frame.head(8).index.tolist()
        + frame.tail(8).index.tolist()
        + random.sample(frame.index.tolist(), min(24, len(frame)))
    )
    for idx in dict.fromkeys(picks):
        row = chunks.loc[idx]
        actual = count_tokens(client, cfg.embedding_service, row.text)
        sample_rows.append(
            {
                "strategy": strategy,
                "id": row.id,
                "n_chars": int(row.n_chars),
                "estimate": int(row.n_tokens_est),
                "actual": actual,
            }
        )
ratios = [r["n_chars"] / r["actual"] for r in sample_rows if r["actual"]]
worst = max(sample_rows, key=lambda r: r["actual"] or 0)
report.append("## Token counts from the embedding model\n")
report.append(
    f"{len(sample_rows)} chunks embedded one at a time through `{cfg.embedding_service}`: characters per model token "
    f"min {min(ratios):.2f}, median {sorted(ratios)[len(ratios) // 2]:.2f}, max {max(ratios):.2f} (the planning rule assumes 4). "
    f"Largest sampled chunk: {worst['actual']} tokens ({worst['n_chars']} chars, `{worst['id']}`).\n"
)
report.append("| Strategy | id | chars | estimate | model tokens |")
report.append("|---|---|---:|---:|---:|")
for r in sorted(sample_rows, key=lambda r: -(r["actual"] or 0))[:12]:
    report.append(f"| {r['strategy']} | {r['id']} | {r['n_chars']} | {r['estimate']} | {r['actual']} |")
print(
    f"chars/token over {len(ratios)} samples: min {min(ratios):.2f} median {sorted(ratios)[len(ratios) // 2]:.2f} max {max(ratios):.2f}"
)

paragraph = chunks[chunks.strategy == SECTIONS].sort_values("n_chars").iloc[-1].text
probes = {
    "inside_window": paragraph * max(1, (GTE_WINDOW * 3) // len(paragraph)),
    "beyond_window": paragraph * max(2, (GTE_WINDOW * 10) // len(paragraph)),
}
probe_results = {}
for label, text in probes.items():
    try:
        probe_results[label] = {
            "chars": len(text),
            "estimate": estimate_tokens(text),
            "model_tokens": count_tokens(client, cfg.embedding_service, text),
            "error": None,
        }
    except Exception as error:  # the service's answer is the finding, whichever it is
        probe_results[label] = {
            "chars": len(text),
            "estimate": estimate_tokens(text),
            "model_tokens": None,
            "error": str(error)[:300],
        }
    print(label, probe_results[label])
report.append("\n### Input-window probe\n")
for label, result in probe_results.items():
    report.append(
        f"- `{label}`: {result['chars']} chars (~{result['estimate']} tokens) → model tokens {result['model_tokens']}; error: {result['error']}"
    )
report.append(
    "\nReading: a `beyond_window` call that returns a token count capped near 8,192 means silent truncation (the lecture's warning); "
    "an error means the service enforces the limit. Either way the section strategy's p95 sits far below it, and the baseline's "
    "longest paragraphs are the ones to watch.\n"
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Write the report

# COMMAND ----------

REPORT = ROOT / "docs" / "chunking_report.md"
report.append("## Observations\n")
report.append(
    preserve_observations(
        REPORT,
        "_Filled in after the run: what the side-by-side showed, which defects the alternative removed, which it introduced, and the strategy chosen for retrieval._",
    )
    + "\n"
)
REPORT.write_text("\n".join(report) + "\n")
print(f"wrote {ROOT / 'docs' / 'chunking_report.md'} and {ROOT / 'docs' / 'corpus.md'}")
