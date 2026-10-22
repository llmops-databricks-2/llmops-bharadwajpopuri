# Databricks notebook source
# ruff: noqa: ERA001
# Databricks MAGIC comments are executable notebook cells.
"""Document preparation for the Evidence Curator: parse the PDFs, chunk them two ways, embed, write `paper_chunks`."""

# COMMAND ----------

# MAGIC %md
# MAGIC # Process papers
# MAGIC
# MAGIC The course's "parse → chunk → embed → Delta with Change Data Feed" step, on the PMC corpus.
# MAGIC
# MAGIC | Step | Here | Course reference |
# MAGIC |---|---|---|
# MAGIC | Parse | `ai_parse_document` on the volume's PDFs, result stored as a JSON string in `parsed_papers`; only files not parsed before (parsing is billed per page) | `DataProcessor.parse_pdfs_with_ai` |
# MAGIC | Chunk | two strategies side by side, `element` (the course's one chunk per text element) and `section` (section-aware packing with sentence overlap, tables kept, reference lists dropped) | `DataProcessor._extract_chunks` / `_clean_chunk` |
# MAGIC | Embed | `course_ops.gateway.embed` (GTE Large, 1,024 dimensions) through Unity Gateway, in batches, with the gateway's token usage recorded | `ai_query(embedding_endpoint, text)` |
# MAGIC | Store | `paper_chunks`, one row per chunk with its provenance (paper, section, page, element ids) and the paper's metadata for filtering, Change Data Feed on | `arxiv_chunks_table` |
# MAGIC
# MAGIC Both strategies land in the one table with a `strategy` column, so the Lakebase copy can serve
# MAGIC either and the retrieval experiments compare them with a filter rather than a second index.
# MAGIC The table is overwritten on each run: the corpus is a snapshot and the chunking is deterministic.

# COMMAND ----------

import json
import time
from datetime import UTC, datetime

from databricks.sdk import WorkspaceClient
from databricks.sdk.runtime import dbutils, display
from pyspark.sql import SparkSession

from arxiv_curator.config import load_config
from evidence_curator.chunking import STRATEGIES, chunk_elements, element_type_counts, length_stats, parse_elements
from evidence_curator.gateway import embed_texts, gateway_client
from evidence_curator.trials import rows_in_schema_order

dbutils.widgets.text("env", "dev")
dbutils.widgets.text("strategies", ",".join(STRATEGIES))
env = dbutils.widgets.get("env")
strategies = [s.strip() for s in dbutils.widgets.get("strategies").split(",") if s.strip()]

cfg = load_config("../../project_config.yml", env=env)
schema_name = cfg.full_schema_name
pdf_dir = f"/Volumes/{cfg.catalog}/{cfg.schema}/{cfg.volume}/pmc_papers"
papers_table = f"{schema_name}.papers"
parsed_table = f"{schema_name}.parsed_papers"
chunks_table = f"{schema_name}.paper_chunks"
processed = int(time.strftime("%Y%m%d%H%M", time.gmtime()))
print(f"Configuration loaded for {schema_name}; strategies {strategies}; embedding service {cfg.embedding_endpoint}")

spark = SparkSession.builder.getOrCreate()

# COMMAND ----------

# MAGIC %md
# MAGIC ## Parse the PDFs that have not been parsed yet
# MAGIC
# MAGIC Same table shape as the course (`path`, `parsed_content` as a JSON string, `processed`). The
# MAGIC function's native return type is VARIANT in the current reference, STRING in older runtimes;
# MAGIC `CAST(... AS STRING)` yields the JSON text in both cases, which the Python extractor reads with
# MAGIC `json.loads`. Only paths absent from the table are parsed, so re-running costs nothing.

# COMMAND ----------

spark.sql(
    f"""
    CREATE TABLE IF NOT EXISTS {parsed_table} (
        path STRING,
        parsed_content STRING,
        processed LONG
    )
    """
)
before = spark.table(parsed_table).count()
spark.sql(
    f"""
    INSERT INTO {parsed_table}
    SELECT path, CAST(ai_parse_document(content) AS STRING) AS parsed_content, {processed} AS processed
    FROM READ_FILES('{pdf_dir}', format => 'binaryFile')
    WHERE path NOT IN (SELECT path FROM {parsed_table})
    """
)
parsed = spark.table(parsed_table)
print(f"{parsed.count() - before} PDFs parsed in this run; {parsed.count()} parsed documents in {parsed_table}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Inspect the parser's output before chunking
# MAGIC
# MAGIC What element types the parser found per paper. A paper with almost no `text` elements, or with
# MAGIC an error status in its JSON, is a parsing problem to look at before it becomes a chunking problem.

# COMMAND ----------

papers = {row["pmcid"]: row.asDict() for row in spark.table(papers_table).collect()}
documents = []
for row in parsed.collect():
    pmcid = row["path"].rsplit("/", 1)[-1].removesuffix(".pdf")
    if pmcid not in papers:
        print(f"  skipping {row['path']}: not in {papers_table}")
        continue
    payload = json.loads(row["parsed_content"])
    elements = parse_elements(payload)
    counts = element_type_counts(elements)
    pages = (payload.get("document") or {}).get("pages") or payload.get("pages") or []
    error = payload.get("error_status") or (payload.get("metadata") or {}).get("error_status")
    documents.append({"pmcid": pmcid, "elements": elements, "counts": counts, "pages": len(pages), "error": error})
    print(f"  {pmcid:<12} pages {len(pages):>3}  {json.dumps(counts)}{'  ERROR: ' + str(error) if error else ''}")
assert documents, "no parsed documents matched the papers table"

# COMMAND ----------

# MAGIC %md
# MAGIC ## Chunk with both strategies

# COMMAND ----------

chunk_rows = []
for doc in documents:
    meta = papers[doc["pmcid"]]
    for strategy in strategies:
        for chunk in chunk_elements(doc["elements"], strategy):
            chunk_rows.append(
                {
                    "id": f"{doc['pmcid']}:{strategy}:{chunk.seq:04d}",
                    "pmcid": doc["pmcid"],
                    "chunk_seq": chunk.seq,
                    "strategy": strategy,
                    "kind": chunk.kind,
                    "section": chunk.section,
                    "page": chunk.page,
                    "element_ids": ",".join(str(i) for i in chunk.element_ids),
                    "n_chars": chunk.n_chars,
                    "n_tokens_est": chunk.n_tokens_est,
                    "text": chunk.text,
                    "title": meta["title"],
                    "journal": meta["journal"],
                    "pub_year": meta["pub_year"],
                    "therapies": meta["therapies"],
                    "nct_ids": meta["nct_ids"],
                    "license": meta["license"],
                }
            )
for strategy in strategies:
    lengths = [r["n_chars"] for r in chunk_rows if r["strategy"] == strategy]
    print(
        f"{strategy:<8} chunks: {json.dumps(length_stats(lengths, limit=8192 * 4))} (limit = 8,192 tokens at 4 chars/token)"
    )

# COMMAND ----------

# MAGIC %md
# MAGIC ## Embed through the gateway
# MAGIC
# MAGIC `course_ops.gateway.embed` embeds the chunk text in batches; `usage.prompt_tokens` is the model's
# MAGIC own count of what it was sent, the number that matters against its 8,192-token window. The
# MAGIC same service embeds queries at search time, so documents and questions share one vector space.

# COMMAND ----------

client = gateway_client(WorkspaceClient())
started = time.perf_counter()
vectors, usage = embed_texts(client, cfg.embedding_endpoint, [r["text"] for r in chunk_rows], batch_size=32)
print(
    f"embedded {usage.n_texts} chunks in {usage.n_calls} calls, {usage.prompt_tokens} prompt tokens, "
    f"{usage.latency_s} s in calls ({time.perf_counter() - started:.0f} s wall), dimension {usage.dimension}"
)
assert usage.dimension == 1024, f"expected 1,024-dimensional vectors, got {usage.dimension}"
now = datetime.now(UTC)
for row, vector in zip(chunk_rows, vectors, strict=True):
    row["embedding"] = vector
    row["embedding_model"] = cfg.embedding_endpoint
    row["processed"] = now

# COMMAND ----------

# MAGIC %md
# MAGIC ## Write `paper_chunks` with Change Data Feed

# COMMAND ----------

CHUNKS_SCHEMA = (
    "id STRING, pmcid STRING, chunk_seq INT, strategy STRING, kind STRING, section STRING, page INT, "
    "element_ids STRING, n_chars INT, n_tokens_est INT, text STRING, title STRING, journal STRING, "
    "pub_year INT, therapies STRING, nct_ids STRING, license STRING, embedding ARRAY<FLOAT>, "
    "embedding_model STRING, processed TIMESTAMP"
)
df = spark.createDataFrame(rows_in_schema_order(chunk_rows, CHUNKS_SCHEMA), schema=CHUNKS_SCHEMA)
df.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(chunks_table)
spark.sql(f"ALTER TABLE {chunks_table} SET TBLPROPERTIES (delta.enableChangeDataFeed = true)")
print(f"Wrote {df.count()} rows to {chunks_table}; Change Data Feed enabled")

display(
    spark.sql(
        f"""
        SELECT strategy, kind, COUNT(*) AS n_chunks, COUNT(DISTINCT pmcid) AS n_papers,
               MIN(n_chars) AS min_chars, PERCENTILE(n_chars, 0.5) AS p50_chars,
               PERCENTILE(n_chars, 0.95) AS p95_chars, MAX(n_chars) AS max_chars
        FROM {chunks_table}
        GROUP BY ALL
        ORDER BY ALL
        """
    )
)

# COMMAND ----------

# Sanity checks: keys unique, every row embedded with the configured service, provenance present.
chunks = spark.table(chunks_table)
n_chunks = chunks.count()
assert chunks.select("id").distinct().count() == n_chunks, "chunk id is not unique"
assert chunks.filter("embedding IS NULL OR size(embedding) <> 1024").count() == 0, "a chunk has no 1,024-d embedding"
assert chunks.filter(f"embedding_model <> '{cfg.embedding_endpoint}'").count() == 0, "mixed embedding models"
assert chunks.filter("pmcid IS NULL OR text IS NULL OR text = ''").count() == 0, "provenance or text missing"
assert {r["strategy"] for r in chunks.select("strategy").distinct().collect()} == set(strategies)
print(f"OK: {n_chunks} chunks from {len(documents)} papers, {len(strategies)} strategies, in {chunks_table}")

# COMMAND ----------

summary = {
    "papers_parsed_total": parsed.count(),
    "papers_parsed_this_run": parsed.count() - before,
    "papers_chunked": len(documents),
    "chunks_by_strategy": {
        strategy: length_stats([r["n_chars"] for r in chunk_rows if r["strategy"] == strategy])
        for strategy in strategies
    },
    "tables_as_chunks": sum(1 for r in chunk_rows if r["kind"] == "table"),
    "embedding": {
        "model": usage.model,
        "texts": usage.n_texts,
        "calls": usage.n_calls,
        "prompt_tokens": usage.prompt_tokens,
        "latency_s": usage.latency_s,
        "dimension": usage.dimension,
    },
    "chunks_table": chunks_table,
}
dbutils.notebook.exit(json.dumps(summary))
