# Evidence of runs

Collected on 2026-10-31 by running the lecture-2 pipeline in the development workspace, with the Databricks CLI output
of each step captured (`2>&1 | tee`) and each task's exit summary fetched from the Jobs API. No tokens, no secrets:
the bundle, the CLI, the SDK and the Postgres connection authenticate through the OAuth profile and short-lived
credentials, and nothing in the notebooks prints one. Lecture-1 evidence (2026-10-17) remains in this folder.

| File | Shows |
|---|---|
| `2026-10-31_bundle_validate.txt` | `databricks bundle validate -t dev` → `Validation OK!` |
| `2026-10-31_bundle_deploy.txt` | `databricks bundle deploy -t dev` → wheel built, jobs deployed (`[dev bharadwajpopuri] job-prepare-papers-bharadwajpopuri-dev` among them) |
| `2026-10-31_bundle_run_papers.txt` | `databricks bundle run prepare_papers -t dev` → run 427363127837771, SUCCESS in 445 s |
| `2026-10-31_job_run_papers.json` | the Jobs API record of that run: three tasks, their states and durations |
| `2026-10-31_task_ingest_papers.json` | the ingest task's summary: 123 PMIDs → 73 in PMC → 54 usable → 24 selected, 20 trials covered |
| `2026-10-31_task_process_papers.json` | the processing task's summary: 24 papers chunked; `element` 1044 chunks, 1–7261 chars (p50 559, p95 3164); `section` 1097 chunks, 11–1509 chars (p50 884, p95 1472); 2141 texts embedded in 67 calls, 491842 prompt tokens; 4 rate-limit hits, 60.0 s waited, 0 batch splits, 115 s wall |
| `2026-10-31_bundle_run_papers_failed_attempt_1.txt` | an earlier run of the job today that failed in `process_papers` with `REQUEST_LIMIT_EXCEEDED` (the gateway's tokens-per-minute limit) before the wait-and-retry was added |

| `2026-10-31_task_sync_paper_chunks.json` | the sync task's summary: state SYNCED_TABLE_ONLINE_NO_PENDING_UPDATE, destination 2141 rows as `vector` of 1024 dims, indexes paper_chunks_synced_embedding_hnsw, paper_chunks_synced_fts_gin, paper_chunks_synced_pkey |
| `2026-10-31_synced_table.json` | the synced table as the Postgres API reports it: spec (primary key, TRIGGERED, vector override) and status |
| `2026-10-31_tables.txt` | Unity Catalog metadata of `papers`, `parsed_papers`, `paper_chunks`: columns, types, Change Data Feed property |
| `2026-10-31_row_counts.txt` | `COUNT(*)` on the SQL warehouse: `paper_chunks` 2141, `paper_chunks/element` 1044, `paper_chunks/section` 1097, `papers` 24, `parsed_papers` 24 |
| `2026-10-31_chunk_inspection.txt` | console output of `notebooks/chunk_inspection.py` (report in `../chunking_report.md`, corpus in `../corpus.md`) |
| `2026-10-31_retrieval_experiments.txt` | console output of `notebooks/retrieval_experiments.py` (log in `../retrieval_log.md`) |
