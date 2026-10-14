# Development environment

Three pieces, verified in this order: the code and its Python toolbox on the laptop, VS Code's
connection to the workspace, and the bundle that ties them together.

## Python 3.12 and the project toolbox

`pyproject.toml` pins `requires-python = "==3.12.*"`; `uv sync --extra dev` builds `.venv` with the
course's pinned packages and `uvx pre-commit install` adds the hooks that format and lint on commit.

```text
$ uv sync --extra dev
$ uvx pre-commit install
$ .venv/bin/python --version
Python 3.12.x
```

## Serverless environment

Jobs run on serverless compute with an environment spec in the job definition
(`resources/*.job.yml` → `environments[].spec`). This project's job uses **environment version 5**:
Python 3.12.3, with base packages that match the project's pins (pandas 2.2.3, numpy 2.1.3,
pyarrow 21.0.0, openai 2.14.0), so installing the project wheel adds packages without downgrading
any. The course template's `hello` job and `[tool.databricks.environment]` in `pyproject.toml` say
version 6 (also Python 3.12.3, but Databricks Connect 19.1 against the 18.0.x pinned here); the
difference is raised as a question in the pull request rather than changed in the template.

## VS Code connected to Databricks

The Databricks extension (2.21.0) with target `dev`, an OAuth user-to-machine profile (`course`),
serverless compute, and the `.venv` from above as the active environment. The sign-in happens once in
the browser; the extension and the CLI reuse the profile, so no token is stored in the project.

Verification, run from the VS Code terminal with the `.venv` active:

```text
$ databricks bundle validate -t dev
Name: llmops-bharadwajpopuri
Target: dev
Workspace:
  Host: https://dbc-88df4c2c-4033.cloud.databricks.com
  User: bharadwajpopuri@live.com
  Path: /Workspace/Users/bharadwajpopuri@live.com/.bundle/dev/llmops-bharadwajpopuri

Validation OK!
```

That one command proves the map (`databricks.yml`), the badge (the OAuth profile) and the CLI at
once: the bundle resolved the target, the workspace host and the deploying identity, under the user's
own `.bundle/dev/...` path. Running code in the workspace is proven by `notebooks/gateway_experiment.py`
(a `WorkspaceClient` call that prints the authenticated user) and by the `prepare_trials` job run.
