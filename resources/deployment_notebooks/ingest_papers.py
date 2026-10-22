# Databricks notebook source
# ruff: noqa: ERA001
# Databricks MAGIC comments are executable notebook cells.
"""Paper ingestion for the Evidence Curator: registry-linked PMC open-access papers to a volume and a table."""

# COMMAND ----------

# MAGIC %md
# MAGIC # Ingest papers
# MAGIC
# MAGIC The literature half of the data, the counterpart of the arXiv curator's "search arXiv → download
# MAGIC PDFs → `arxiv_papers`" step. The corpus is not a free-text search: it is derived from the
# MAGIC publication links ClinicalTrials.gov itself records for the 30 pinned trials (`trial_references`),
# MAGIC resolved against PubMed Central:
# MAGIC
# MAGIC 1. PMIDs → PMCIDs with the PMC ID converter (papers PubMed Central does not hold drop out here:
# MAGIC    most pivotal trial papers are paywalled).
# MAGIC 2. PMCIDs → the PMC Article Datasets on AWS, NCBI's documented route for automated retrieval since
# MAGIC    the OA web service was discontinued: per article version, a JSON object with open-access status,
# MAGIC    licence, retraction flag and the PDF's location and checksum.
# MAGIC 3. Keep open-access versions under a Creative Commons licence with a PDF; rank by the directness
# MAGIC    of the registry link (RESULT, then DERIVED, then BACKGROUND) and recency; fill the cap round-robin
# MAGIC    across the three therapies.
# MAGIC 4. Download the PDFs into the volume (checksum-verified, skipped when already there) and overwrite
# MAGIC    the `papers` table: one row per paper with its licence, journal, year, linked trials and therapies.
# MAGIC
# MAGIC Every paper therefore arrives tied to at least one trial by the registry, which is the paper-to-trial
# MAGIC mapping the project proposal asked for. `max_papers` caps parsing and embedding cost; the resolution
# MAGIC funnel is printed so the choice is visible.

# COMMAND ----------

import json
from datetime import UTC, datetime
from pathlib import Path

from databricks.sdk.runtime import dbutils, display
from pyspark.sql import SparkSession

from arxiv_curator.config import load_config
from evidence_curator.papers import (
    PAPERS_SCHEMA,
    download_pdf,
    paper_rows,
    pmcids_for,
    pubmed_summaries,
    resolve_articles,
)
from evidence_curator.seed import SEED_TRIALS
from evidence_curator.trials import rows_in_schema_order

dbutils.widgets.text("env", "dev")
dbutils.widgets.text("max_papers", "24")
env = dbutils.widgets.get("env")
max_papers = int(dbutils.widgets.get("max_papers"))

cfg = load_config("../../project_config.yml", env=env)
schema_name = cfg.full_schema_name
pdf_dir = f"/Volumes/{cfg.catalog}/{cfg.schema}/{cfg.volume}/pmc_papers"
print(f"Configuration loaded for {schema_name}; PDFs go to {pdf_dir}; cap {max_papers} papers")

spark = SparkSession.builder.getOrCreate()
spark.sql(f"CREATE VOLUME IF NOT EXISTS {cfg.full_volume_path}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Resolve the registry's publication links against PubMed Central

# COMMAND ----------

references = [row.asDict() for row in spark.table(f"{schema_name}.trial_references").collect()]
pmids = sorted({str(r["pmid"]) for r in references})
therapy_of = {trial.nct_id: trial.therapy for trial in SEED_TRIALS}
print(f"{len(references)} registry links to {len(pmids)} distinct PMIDs")

pmcid_of = pmcids_for(pmids)
articles = resolve_articles(sorted(set(pmcid_of.values())))
usable = {pmcid: a for pmcid, a in articles.items() if a.usable}
summaries = pubmed_summaries([pmid for pmid, pmcid in pmcid_of.items() if pmcid in usable])
retrieved_at = datetime.now(UTC)

licences: dict[str, int] = {}
for article in articles.values():
    key = article.license_code or ("TDM" if article.is_manuscript else "none")
    licences[key] = licences.get(key, 0) + 1
print(f"in PMC: {len(pmcid_of)}; in the datasets: {len(articles)}; usable (open access, CC, PDF): {len(usable)}")
print(f"licence codes among those in the datasets: {json.dumps(licences, sort_keys=True)}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Select the corpus and fetch the PDFs

# COMMAND ----------

rows = paper_rows(
    references, therapy_of, pmcid_of, articles, summaries, max_papers=max_papers, retrieved_at=retrieved_at
)
print(f"selected {len(rows)} papers")

Path(pdf_dir).mkdir(parents=True, exist_ok=True)
for row in rows:
    article = articles[row["pmcid"]]
    destination = f"{pdf_dir}/{row['pmcid']}.pdf"
    size = download_pdf(article, destination)
    row["volume_path"] = destination
    print(
        f"  {row['pmcid']:<12} {size / 1024:7.0f} KB  {row['therapies']:<24} {row['license']:<12} {(row['title'] or '')[:70]}"
    )

# COMMAND ----------

# MAGIC %md
# MAGIC ## Write the `papers` table

# COMMAND ----------

papers_table = f"{schema_name}.papers"
df = spark.createDataFrame(rows_in_schema_order(rows, PAPERS_SCHEMA), schema=PAPERS_SCHEMA)
df.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(papers_table)
print(f"Wrote {df.count()} rows to {papers_table}")

papers = spark.table(papers_table)
papers.printSchema()
display(
    papers.select(
        "pmcid", "therapies", "pub_year", "journal", "license", "reference_types", "n_trials", "nct_ids", "title"
    ).orderBy("therapies", "pub_year")
)
display(
    spark.sql(
        f"""
        SELECT therapies, license, COUNT(*) AS n_papers, MIN(pub_year) AS from_year, MAX(pub_year) AS to_year
        FROM {papers_table}
        GROUP BY ALL
        ORDER BY ALL
        """
    )
)

# COMMAND ----------

# Sanity checks: the corpus covers every therapy, keys are unique, every PDF is a real file in the volume.
n_papers = papers.count()
assert n_papers > 0, "no usable open-access papers were found"
assert papers.select("pmcid").distinct().count() == n_papers, "pmcid is not unique"
therapies_covered = {t for row in papers.select("therapies").collect() for t in row["therapies"].split(",")}
assert therapies_covered == {trial.therapy for trial in SEED_TRIALS}, f"therapies covered: {therapies_covered}"
assert papers.filter("license IS NULL OR volume_path IS NULL").count() == 0, "licence or volume path missing"
too_small = [row["pmcid"] for row in papers.collect() if Path(row["volume_path"]).stat().st_size < 10_000]
assert not too_small, f"suspiciously small PDFs: {too_small}"
print(f"OK: {n_papers} papers across {sorted(therapies_covered)} in {papers_table}, PDFs under {pdf_dir}")

# COMMAND ----------

# The task's exit value: the resolution funnel and the corpus shape, read back by the evidence script
# (`databricks jobs get-run-output`) so the numbers in the PR come from the run, not from memory.
summary = {
    "registry_links": len(references),
    "distinct_pmids": len(pmids),
    "in_pmc": len(pmcid_of),
    "in_datasets": len(articles),
    "usable_open_access": len(usable),
    "selected": n_papers,
    "max_papers": max_papers,
    "licences_in_datasets": licences,
    "selected_by_therapy": {
        row["therapies"]: row["n"]
        for row in papers.groupBy("therapies").count().withColumnRenamed("count", "n").collect()
    },
    "trials_covered": len({n for row in papers.select("nct_ids").collect() for n in row["nct_ids"].split(",")}),
    "pdf_dir": pdf_dir,
    "papers_table": papers_table,
}
dbutils.notebook.exit(json.dumps(summary))
