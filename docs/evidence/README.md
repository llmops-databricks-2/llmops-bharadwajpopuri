# Evidence of runs

Screenshots and command output from the development workspace, named by date and step. No tokens,
no secrets: the bundle, the CLI and the SDK authenticate through the OAuth profile, and nothing in the
notebooks prints a credential.

| File | Shows |
|---|---|
| `2026-10-14_bundle_validate.txt` | `databricks bundle validate -t dev` → `Validation OK!` |
| `2026-10-14_bundle_deploy.txt` | `databricks bundle deploy -t dev` → wheel built, job `[dev bharadwajpopuri] job-prepare-trials-bharadwajpopuri-dev` deployed |
| `2026-10-14_job_run.png` | the job run page: task `prepare_trials` succeeded on serverless |
| `2026-10-14_trials_schema.png` | the notebook output: `printSchema()` and the sample records |
| `2026-10-14_trials_catalog.png` | Catalog Explorer: `llmops_dev.bharadwajpopuri.trials` with 30 rows |
| `../gateway_experiment_log.md` | responses, token usage and latency of the gateway experiment |
