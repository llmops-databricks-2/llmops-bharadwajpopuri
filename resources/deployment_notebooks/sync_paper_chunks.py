# Databricks notebook source
# ruff: noqa: ERA001
# Databricks MAGIC comments are executable notebook cells.
"""Lakebase synchronisation for the Evidence Curator: mirror `paper_chunks` into pgvector and verify it."""

# COMMAND ----------

# MAGIC %md
# MAGIC # Sync paper chunks to Lakebase
# MAGIC
# MAGIC The course's notebook 2.5 for this project: `paper_chunks` (Delta, Change Data Feed on) becomes a
# MAGIC *synced table* in the student's Lakebase project through a managed, triggered pipeline, keyed on
# MAGIC `id`, with `embedding` declared `vector(1024)` so pgvector's operators apply. Delta stays the source
# MAGIC of truth; the Postgres copy is never written directly.
# MAGIC
# MAGIC Creation sequence, as the lecture notes give it:
# MAGIC
# MAGIC 1. validate the source: stable non-null unique `id`, populated vectors, Change Data Feed enabled;
# MAGIC 2. install the `vector` extension in the target database;
# MAGIC 3. create the synced table (or trigger one update of the existing one) and wait for *that* update;
# MAGIC 4. create the indexes the queries rely on (GIN for full text, HNSW for cosine);
# MAGIC 5. inspect the destination itself: `pg_typeof(embedding)`, row count, null vectors, `pg_indexes`.
# MAGIC
# MAGIC Cost note: the project's compute scales to zero after five idle minutes; the sync pipeline is
# MAGIC triggered, so it only runs when this notebook (or the job) asks for an update.

# COMMAND ----------

import json

from databricks.sdk import WorkspaceClient
from databricks.sdk.runtime import dbutils
from pyspark.sql import SparkSession

from arxiv_curator.config import load_config
from evidence_curator.vector_store import LakebaseChunkStore, SearchFilters

dbutils.widgets.text("env", "dev")
env = dbutils.widgets.get("env")

cfg = load_config("../../project_config.yml", env=env)
spark = SparkSession.builder.getOrCreate()
w = WorkspaceClient()
store = LakebaseChunkStore(cfg, workspace=w)
print(f"Source {store.source_table_full_name} → synced table {store.synced_table_id} in {store.project_name}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Validate the source table

# COMMAND ----------

source = spark.table(store.source_table_full_name)
n_source = source.count()
assert n_source > 0, "the source table is empty: run process_papers first"
assert source.filter("id IS NULL").count() == 0, "null ids"
assert source.select("id").distinct().count() == n_source, "ids are not unique: the primary key would be ambiguous"
assert source.filter("embedding IS NULL OR size(embedding) <> 1024").count() == 0, "rows without a 1,024-d vector"
properties = {r["key"]: r["value"] for r in spark.sql(f"SHOW TBLPROPERTIES {store.source_table_full_name}").collect()}
assert properties.get("delta.enableChangeDataFeed") == "true", "Change Data Feed is off: the triggered sync needs it"
print(f"source OK: {n_source} rows, unique ids, vectors present, Change Data Feed on")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2–3. Extension, then create or update the synced table

# COMMAND ----------

endpoint_name, host = store.resolve_endpoint()
print(f"branch {store.branch_name}; endpoint {endpoint_name}; database {store.database}")
store.ensure_extension()
print("pgvector extension present")

existing = store.get_synced_table()
print("synced table exists" if existing else "synced table missing: creating it")
table = store.create_or_update(timeout_s=1800)
status = table.status
print(
    json.dumps(
        {
            "name": table.name,
            "state": status.detailed_state.value if status and status.detailed_state else None,
            "pipeline_id": status.pipeline_id if status else None,
            "last_sync_time": str(status.last_sync_time) if status and status.last_sync_time else None,
            "last_processed_commit_version": status.last_processed_commit_version if status else None,
            "message": status.message if status else None,
        },
        indent=2,
    )
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4–5. Indexes, then inspect the database itself

# COMMAND ----------

index_names = store.ensure_indexes(hnsw=True)
report = store.inspect()
print(json.dumps(report, indent=2))

assert report["row_count"] == n_source, f"destination has {report['row_count']} rows, source {n_source}"
assert report["null_vectors"] == 0, "null vectors in the destination"
assert report["embedding_type"] == "vector", (
    f"embedding arrived as {report['embedding_type']}, not vector: type override missing"
)
assert report["embedding_dims"] == 1024, f"vector dimension {report['embedding_dims']}"
present = {index["name"] for index in report["indexes"]}
assert set(index_names) <= present, f"indexes missing: {set(index_names) - present}"
print(f"OK: {report['table']} holds {report['row_count']} rows as vector(1024) with indexes {sorted(present)}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Smoke test: one semantic query through the same embedding service

# COMMAND ----------

for row in store.search(
    "weight regain after stopping treatment", num_results=3, filters=SearchFilters(strategy="section")
):
    print(f"{row['score']:.3f}  {row['id']:<32} {row['section'] or '':<30} {row['text'][:90]}")

# COMMAND ----------

summary = {
    "synced_table": table.name,
    "state": status.detailed_state.value if status and status.detailed_state else None,
    "pipeline_id": status.pipeline_id if status else None,
    "last_sync_time": str(status.last_sync_time) if status and status.last_sync_time else None,
    "source_rows": n_source,
    "destination": report,
}
dbutils.notebook.exit(json.dumps(summary, default=str))
