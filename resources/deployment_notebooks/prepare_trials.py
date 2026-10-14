# Databricks notebook source
# ruff: noqa: ERA001
# Databricks MAGIC comments are executable notebook cells.
"""Data preparation for the Evidence Curator: pinned ClinicalTrials.gov records to Delta tables."""

# COMMAND ----------

# MAGIC %md
# MAGIC # Prepare trials
# MAGIC
# MAGIC The structured half of the Evidence Curator's data, the registry side of the arXiv curator's
# MAGIC "get metadata → store to Delta table" step. It fetches the pinned trial snapshot
# MAGIC (`evidence_curator.seed`) from the ClinicalTrials.gov API v2, flattens the records
# MAGIC (`evidence_curator.trials`), and writes three tables to this environment's schema:
# MAGIC
# MAGIC | Table | Rows | What it is |
# MAGIC |---|---|---|
# MAGIC | `trials` | one per pinned trial | registry metadata: design, status, enrollment, planned primary outcomes, dates |
# MAGIC | `trial_references` | one per (trial, PMID) | the registry's own publication links: the seed of the paper-to-trial mapping |
# MAGIC | `drug_aliases` | one per alias | INN / brand / sponsor code / dose label to canonical therapy |
# MAGIC
# MAGIC Every row carries `retrieved_at` and the source, so a brief can say how current its registry
# MAGIC facts are. The tables are overwritten on each run: the snapshot is defined by the seed list,
# MAGIC and Delta's history keeps earlier versions.

# COMMAND ----------

from datetime import UTC, datetime

from databricks.sdk.runtime import dbutils, display
from pyspark.sql import SparkSession

from arxiv_curator.config import load_config
from evidence_curator.seed import SEED_TRIALS
from evidence_curator.trials import (
    ALIASES_SCHEMA,
    REFERENCES_SCHEMA,
    TRIALS_SCHEMA,
    alias_rows,
    build_snapshot,
    fetch_studies,
    rows_in_schema_order,
)

# The environment comes from the job's base parameters; "dev" when run by hand.
dbutils.widgets.text("env", "dev")
env = dbutils.widgets.get("env")

cfg = load_config("../../project_config.yml", env=env)
schema_name = cfg.full_schema_name
print(f"Configuration loaded for {schema_name}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Fetch the snapshot
# MAGIC
# MAGIC Two requests to the API (25 IDs each). A pinned ID that the API does not return is an error,
# MAGIC not a silent gap: the snapshot is defined as exactly these trials.

# COMMAND ----------

retrieved_at = datetime.now(UTC)
nct_ids = [trial.nct_id for trial in SEED_TRIALS]
studies = fetch_studies(nct_ids)
trial_rows, reference_rows, missing = build_snapshot(studies, retrieved_at=retrieved_at)
print(
    f"Fetched {len(trial_rows)} of {len(nct_ids)} pinned trials with {len(reference_rows)} publication links "
    f"at {retrieved_at.isoformat(timespec='seconds')}"
)
if missing:
    raise RuntimeError(f"Pinned trials not returned by ClinicalTrials.gov: {missing}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Write the Delta tables
# MAGIC
# MAGIC Rows are passed positionally in DDL column order with an explicit schema, so types are what the
# MAGIC schema says (no inference from a sample of rows that might all be null in a column).

# COMMAND ----------

spark = SparkSession.builder.getOrCreate()

tables = {
    "trials": (TRIALS_SCHEMA, trial_rows),
    "trial_references": (REFERENCES_SCHEMA, reference_rows),
    "drug_aliases": (ALIASES_SCHEMA, alias_rows()),
}
for name, (ddl, rows) in tables.items():
    df = spark.createDataFrame(rows_in_schema_order(rows, ddl), schema=ddl)
    table = f"{schema_name}.{name}"
    df.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(table)
    print(f"Wrote {df.count()} rows to {table}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Check the schema and sample records

# COMMAND ----------

trials = spark.table(f"{schema_name}.trials")
trials.printSchema()

overview_columns = [
    "nct_id",
    "therapy",
    "program",
    "acronym",
    "phase",
    "overall_status",
    "lead_sponsor",
    "enrollment_count",
    "start_date",
    "has_results",
    "n_references",
]
display(trials.select(*overview_columns).orderBy("therapy", "start_date"))

# COMMAND ----------

display(
    spark.sql(
        f"""
        SELECT therapy, phase, overall_status, COUNT(*) AS n_trials, SUM(enrollment_count) AS participants
        FROM {schema_name}.trials
        GROUP BY ALL
        ORDER BY ALL
        """
    )
)

# COMMAND ----------

display(
    spark.sql(
        f"""
        SELECT t.nct_id, t.acronym, t.therapy, r.reference_type, COUNT(*) AS n_pmids
        FROM {schema_name}.trial_references r
        JOIN {schema_name}.trials t USING (nct_id)
        GROUP BY ALL
        ORDER BY t.therapy, t.nct_id, r.reference_type
        """
    )
)

# COMMAND ----------

# Sanity checks: the snapshot is complete, keys are unique, provenance is present on every row.
n_trials = trials.count()
assert n_trials == len(SEED_TRIALS), f"expected {len(SEED_TRIALS)} trials, found {n_trials}"
assert trials.select("nct_id").distinct().count() == n_trials, "nct_id is not unique"
assert trials.filter("retrieved_at IS NULL OR source_url IS NULL").count() == 0, "provenance missing"
assert trials.filter("intervention_therapies IS NULL").count() == 0, "a trial has no recognised therapy"
print(f"OK: {n_trials} trials, {len(reference_rows)} publication links, {len(alias_rows())} aliases in {schema_name}")
