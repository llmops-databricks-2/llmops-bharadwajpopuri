# Retrieval foundation (lecture 2)

How the Evidence Curator's documents become searchable evidence: the course's arXiv pipeline
(download → `ai_parse_document` → chunks → embeddings → Lakebase synced table → SQL retrieval)
transposed to open-access papers about the three GLP-1 therapies, with the decisions recorded so
they can be defended or reversed. Observations from the runs live in
[`chunking_report.md`](chunking_report.md) and [`retrieval_log.md`](retrieval_log.md); the corpus
itself is listed in [`corpus.md`](corpus.md).

## The pipeline

```text
trial_references (184 registry links, 123 PMIDs)
   │  PMC ID converter → PMCIDs            (pure Python: evidence_curator.papers)
   │  PMC Article Datasets on AWS → open-access status, licence, PDF + MD5
   ▼
papers (24 rows)  +  /Volumes/…/evidence_files/pmc_papers/PMC*.pdf          job task  ingest_papers
   │  ai_parse_document(content) → parsed_papers (JSON string per PDF)
   │  chunking: `element` (course baseline) and `section` (alternative)      evidence_curator.chunking
   │  course_ops.gateway.embed → 1,024-d vectors, token usage recorded      evidence_curator.gateway
   ▼
paper_chunks (Delta, Change Data Feed on, both strategies, `strategy` column) job task  process_papers
   │  synced table, TRIGGERED, primary key `id`, `embedding` → vector(1024)  evidence_curator.vector_store
   ▼
Lakebase  lb-llmops-bharadwajpopuri / databricks_postgres / bharadwajpopuri.paper_chunks_synced
   │  GIN (full text) + HNSW (cosine) indexes                                job task  sync_paper_chunks
   ▼
SQL retrieval: semantic · filtered · keyword · hybrid (reciprocal rank fusion) notebooks/retrieval_experiments.py
```

One job, `job-prepare-papers-bharadwajpopuri-<target>`, runs the three tasks in that order
(`resources/papers.job.yml`); the two notebooks under `notebooks/` are the inspection and the
experiments, run from VS Code against the same tables.

## Configuration approach

Everything environment-specific comes from `project_config.yml` through the course's
`ProjectConfig`: catalog, schema, volume, the embedding names, the warehouse, and (added this
week, read from the file the onboarding filled in) the Lakebase project `lakebase_instance` and the
`usage_policy_id`. Since the workspace move of November 2026 the configuration carries two embedding
names for the same GTE Large model (README, "Models"): `embedding_service` is the gateway model
service and is what every OpenAI-client call in this project passes (`embed_texts`, `embed_query`,
the token counts); `embedding_endpoint` is the serving endpoint for `ai_query`, AI Search and an
agent's `DatabricksServingEndpoint` resource, which the gateway client refuses. No notebook names a resource of its own; the same code deploys to `dev`, `acc`
and `prd` by target, as the lecture asks ("use the configured environment rather than copying a
developer's resource names into a notebook").

Cost attribution follows the same rule: the job carries the usage policy, the synced table's pipeline
is created with it (`NewPipelineSpec.budget_policy_id`), the local Databricks Connect session passes
it to serverless, and the Lakebase project already carries it. The project's compute suspends after
five idle minutes; the sync pipeline is triggered, so nothing runs between sessions.

Delta is the source of truth. `paper_chunks` is overwritten by the processing task (the corpus is a
snapshot and the chunking is deterministic); the Postgres copy is never written directly, and a
re-sync is one task run.

## Decisions

| Decision | Choice | Why, and what it costs |
|---|---|---|
| Serving store | Lakebase pgvector synced table, not an AI Search index | No Vector Search endpoint is provisioned for students; an endpoint is always-on compute (the lecture put it at ~$250–300 a month) while Lakebase scales to zero; SQL gives metadata predicates, hybrid scoring and reranking under the application's control. Cost: the application embeds its own queries and owns index creation. |
| Embedding path | `embedding_service` (`course_ops.gateway.embed`, GTE Large) through Unity Gateway, from Python in batches | The repository README says to generate vectors through the gateway's embeddings API before storing them in pgvector; usage lands in `system.ai_gateway.usage` against the student budget; the gateway reports the model's own token count per call. The course switched its arXiv pipeline to `databricks-gte-large-en` via `ai_query` because AI Search cannot call the gateway, a constraint the Lakebase route does not have. Risk: if the gateway service were replaced, every vector must be regenerated with whatever replaces it (true of any model change). |
| Rate limits | Wait-and-retry on the gateway's per-user tokens-per-minute limit (15 s doubling to 60 s, batch halved after three consecutive 429s), hits and waiting time recorded in the task summary | The first dev run of `process_papers` failed with `REQUEST_LIMIT_EXCEEDED` on `course_ops.gateway.embed` after a burst of 32-text batches; the OpenAI client's own two quick retries cannot out-wait a per-minute limiter. Batch ingestion through a shared, budgeted service is throughput-bound, which is the operational point the lecture made about embedding choice; the recorded waits quantify it. |
| Corpus | Papers the registry itself links to the pinned trials, resolved to the PMC Open Access Subset | Every paper is tied to a trial by ClinicalTrials.gov, which is the paper-to-trial mapping the proposal needed; no free-text search, so the set is reproducible. The PMC OA web service was discontinued in 2026; membership, licence and PDFs now come from NCBI's PMC Article Datasets on AWS (world-readable, plain HTTPS, MD5 per file), the route NCBI documents for automated retrieval. |
| Licence policy | Any Creative Commons licence (CC BY, CC BY-NC, CC BY-NC-ND, …), recorded per paper; `TDM`-only author manuscripts and unlicensed items excluded | On 2026-10-22: 123 PMIDs → 73 in PMC → 54 open access with a CC licence and a PDF (21 CC BY, 15 CC BY-NC, 22 CC BY-NC-ND; the other 19: 8 absent from the datasets, 4 without a PDF, 3 without a licence code, 4 text-mining-only manuscripts). Restricting to CC BY would leave liraglutide with two papers (its SCALE result papers are CC BY-NC-ND). The project is non-commercial coursework and briefs cite rather than reproduce; `use_case.md` was updated accordingly. |
| Corpus size | 24 papers, 8 per therapy, trial-result papers first, then breadth across trials, then recency | Enough variety to make the retrieval questions meaningful while keeping parsing (billed per page) and embedding small; `max_papers` is a job parameter. |
| Chunking | Two strategies in one table: `element` (one chunk per parsed text element, the course baseline) and `section` (section-aware packing to 1,500 characters with a sentence-aligned 200-character overlap, long paragraphs split at sentence ends, page headers/footers dropped, reference lists and acknowledgements skipped, tables kept as chunks with their caption and header row) | The baseline inherits the parser's paragraph sizes, from a one-line fragment to a page-long paragraph, indexes reference entries and running headers, and loses tables, which carry the strongest evidence in clinical papers. The alternative controls size and drops noise at the price of more code and a few heuristics (caption detection, section skip list). Comparison numbers in `chunking_report.md`. |
| Token budget | 1,500 characters ≈ 375 tokens by the four-characters rule; GTE Large's window is 8,192 tokens | The window is not the binding constraint; retrieval precision is. The model's own counts for a sample, and a probe of the window, are in `chunking_report.md`. |
| Synced table | TRIGGERED, primary key `id`, `type_overrides` embedding → `PG_SPECIFIC_TYPE_VECTOR` size 1024, `create_database_objects_if_missing`, pipeline storage in the student schema | Without the override the array arrives as JSONB and vector operators do not apply; triggered because the corpus changes when the job runs, not continuously. |
| Indexes | GIN on `to_tsvector('english', title ‖ text)`; HNSW `vector_cosine_ops` on `embedding` | The course leaves HNSW out because its optional Lakebase Search example puts a `lakebase_ann` index on the same column; that Beta route (`ai_search()` over Lakebase) is not used here, so the pgvector index is created. On a few thousand rows an exact scan is fast anyway. |
| Keyword matching | Any stemmed term of the question matches; chunks matching every term rank first, then `ts_rank_cd` cover density (`require_all_terms=True` keeps the first run's behaviour) | The first run used `websearch_to_tsquery`, which ANDs every term: four of the eight questions returned no rows and hybrid degenerated to semantic on them. Postgres ranking has no IDF (a trial name weighs no more than "participants"), hence the all-terms-first ordering; BM25 would need an extension or AI Search. |
| Hybrid scoring | Reciprocal rank fusion of the semantic and full-text rankings (k = 60, top-50 candidates each) | The fusion AI Search describes for HYBRID; it combines ranks, so cosine similarity (0–1) and `ts_rank_cd` (unbounded, usually small) never share a scale. The course's hybrid SQL uses a weighted sum of the raw scores, which is harder to tune; the two agree on the top results more often than not. |
| `ai_search()` over Lakebase | Not used | Beta; the lecture reported workspace errors on this path and does not rely on it for the agent. Direct Postgres is the recommended route. |

## How to run

```bash
databricks bundle validate -t dev
databricks bundle deploy -t dev
databricks bundle run prepare_papers -t dev        # ingest → process → sync, ~10–20 min end to end
uv run python notebooks/chunk_inspection.py        # writes docs/corpus.md and docs/chunking_report.md
uv run python notebooks/retrieval_experiments.py   # writes docs/retrieval_log.md
```

The two notebooks need the OAuth profile (`DATABRICKS_CONFIG_PROFILE=course`) and open a serverless
Databricks Connect session for the tables and a Postgres connection to the Lakebase project with a
short-lived token minted by the SDK; nothing is copied into code or output.

## What was verified

- **Source and destination of the sync.** Unique non-null `id`, populated 1,024-d vectors and Change
  Data Feed on `paper_chunks` before creation; after it, `pg_typeof(embedding) = vector`,
  `vector_dims = 1024`, destination row count equal to the source, no null vectors, both indexes in
  `pg_indexes`, synced-table state `SYNCED_TABLE_ONLINE_NO_PENDING_UPDATE` and the pipeline id
  (the `sync_paper_chunks` task output).
- **Embedding window.** `usage.prompt_tokens` per batch from the gateway; a sample of chunks counted
  individually; an inside-window and a beyond-window probe (`chunking_report.md`).
- **Retrieval.** The same eight questions through every mode, hit@5 against the trial each
  question is about, latency per call, and the overlap between modes (`retrieval_log.md`).
- **Where the record is.** The dev run of 2026-10-31 is job run 427363127837771 in the course's
  first workspace; the CLI output of each step and the tasks' exit summaries were captured but are
  kept out of git (`docs/evidence/` is ignored, at the reviewers' request), so the numbers in this
  document and the two reports are the record. On 2026-11-03 the course moved to a new workspace:
  the teachers copied the tables and the volume files under the same names, the synced table was
  re-created there by running the sync task alone (`databricks bundle run prepare_papers -t dev
  --only sync_paper_chunks`, no re-parsing and no re-embedding), and `retrieval_log.md` was
  regenerated against it.

## Known limitations

- Tables become `cell | cell` rows with the caption attached; merged cells and footnotes lose their
  structure, and figures contribute only their captions. `ai_prep_search` or a layout-aware chunker
  would be the next step if table questions matter.
- The section heuristics (caption detection, the skip list) are tuned on this corpus and inspected
  by hand, not evaluated against labels; the inspection notebook is where they get checked after
  a corpus change.
- Cosine similarity does not separate "answered" from "not in the corpus" (the out-of-corpus question scored 0.823, above several correct answers); the agent needs an entity check (trial name, NCT ID) and the keyword channel's emptiness as signals of absence, not a score threshold.
- The hit@5 labels are the trial each question targets, not a reviewed golden set; the golden set of
  ~20 questions with expected passages is the evaluation lecture's work.
- Pivotal results of the three programmes are largely paywalled (NEJM, Lancet); the corpus leans
  towards secondary analyses and pooled safety papers, so briefs about primary endpoints will cite
  the registry's posted results, as the use case anticipated. Ten of the thirty pinned trials have
  no open-access paper in the corpus.
- The PMC datasets refresh daily and an article version can be withdrawn; `papers.pmc_version` and
  the MD5 check record what was used, but nothing re-checks the bucket after ingestion.
- The gateway's tokens-per-minute limit bounds how fast the corpus can be (re)embedded; a larger corpus would need either a longer job window, a pacing parameter tuned to the published limit, or a batch embedding path outside the per-user budget.
- The query path embeds through the gateway on every call (one round trip before the SQL); a cache
  for repeated questions and a score threshold calibrated on the question set are deliberate
  omissions this week.
- Serverless environment version: the job uses 5 (matching this project's pins), while the lecture
  demonstrated 6; still an open question to the teachers from the first pull request.

## Observations

The two reports hold the detail; the summary, from the run of 2026-10-31:

- **Parsing and chunking.** `ai_parse_document` returns mostly page furniture; text elements are about a third of the elements. The course baseline (one chunk per text element) inherits the parser's paragraph sizes, 1–7,261 characters: a quarter of its 1,044 chunks are fragments under 50 tokens, 37 are duplicates, reference lists and running headers are indexed, tables are not, and the longest element counted 2,255 tokens by the model. The section strategy holds 11–1,509 characters (p95 368 tokens), drops references and furniture, keeps 132 tables with their captions, and labels every chunk with its section; it still has defects the side-by-side exposed (front-matter boxes parsed as tables, affiliation footnotes treated as body text, Nature-style captions not recognised, hyphenation without a line break left unrepaired, occasional wrong section labels from the parser's reading order). It is the strategy retrieval uses; the baseline stays in the table for comparison.
- **Embedding window.** GTE Large through the gateway accepts 8,192 tokens and silently truncates beyond it (an 81k-character probe returned a vector with `prompt_tokens = 8192`, no error); the model counts a median 3.6 characters per token here, so the four-characters rule under-estimates by ~10%. The length check lives in the pipeline.
- **Gateway rate limit.** The first `process_papers` run failed with `REQUEST_LIMIT_EXCEEDED` (tokens per minute, per user); with wait-and-retry the 491,842 tokens took 67 calls and 115 s, 60 s of it waiting. Re-embedding is a paced batch job.
- **Lakebase.** The synced table came online with 2,141 rows, `embedding` as `vector(1024)`, no nulls, HNSW and GIN indexes beside the primary key, pgvector 0.8.0; one job run creates or updates it and verifies the destination.
- **Retrieval.** Semantic search on section chunks hit 7/7 answerable questions (baseline chunks 6/7, with reference entries and author lines in its top results); filters narrowed the evidence exactly as intended; the keyword channel with every term required returned nothing for half of the questions, so it was changed to any-term matching with all-terms first, after which it hit 7/7 and the hybrid's mean first-hit rank was 1.00, the best of the modes (rerun of 2026-11-03); hybrid (RRF) promoted evidence neither channel ranked first where both matched, at twice the latency; the out-of-corpus question scored 0.823, higher than several correct answers, so a score threshold cannot detect absence and the agent will check for the named trial instead.
