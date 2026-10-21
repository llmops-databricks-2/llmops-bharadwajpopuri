# Evidence of runs

Collected on 2026-10-17 by re-running the data-preparation job in the development workspace, with the
Databricks CLI output of each step captured (`2>&1 | tee`: the CLI prints its progress to stderr).
No tokens, no secrets: the bundle, the CLI and the SDK authenticate through the OAuth profile, and
nothing in the notebooks prints a credential.

| File | Shows |
|---|---|
| `2026-10-17_bundle_validate.txt` | `databricks bundle validate -t dev` → `Validation OK!` |
| `2026-10-17_bundle_deploy.txt` | `databricks bundle deploy -t dev` → wheel built, job `[dev bharadwajpopuri] job-prepare-trials-bharadwajpopuri-dev` deployed |
| `2026-10-17_bundle_run.txt` | `databricks bundle run prepare_trials -t dev` → run 250976392519306, SUCCESS |
| `2026-10-17_job_run.json` | the Jobs API record of that run: `result_state` SUCCESS, 78 s execution, notebook under `.bundle/dev` |
| `2026-10-17_tables.txt` | Unity Catalog metadata of `trials`, `trial_references`, `drug_aliases`: columns, types, last update |
| `2026-10-17_row_counts.txt` | `COUNT(*)` on the SQL warehouse: `trials` 30, `trial_references` 184, `drug_aliases` 19 |
| `../gateway_experiment_log.md` | responses, token usage and latency of the gateway experiment |
