"""Short-lived Lakebase connections, shared by the chunk store (lecture 2) and session memory (lecture 3).

One Lakebase project holds both the pgvector copy of the chunks and the agent's session history, and
both connect the same way: the workspace client finds the project's branch and compute endpoint,
mints a Postgres credential for the current identity (a person in VS Code or a notebook, the
deployment service principal in a job) and opens one TLS connection with it. The token is used once
and never written anywhere. Connections are opened per call rather than pooled: Lakebase credentials
expire after an hour, which a long-lived pool outlives, and the project's compute scales to zero
between sessions anyway.

A deployed Databricks app exposes its Lakebase resource as `LAKEBASE_ENDPOINT`, `PGHOST` and
`PGDATABASE`; when those are set they take precedence over the branch lookup.
"""

import os
import urllib.parse
from collections.abc import Iterator
from contextlib import contextmanager

import psycopg
from databricks.sdk import WorkspaceClient

DEFAULT_DATABASE = "databricks_postgres"  # every Lakebase branch starts with this database


class LakebaseConnector:
    """Resolve a Lakebase project's endpoint and open connections for the current identity."""

    def __init__(
        self,
        project: str,
        workspace: WorkspaceClient | None = None,
        database: str = DEFAULT_DATABASE,
        branch: str | None = None,
    ) -> None:
        if not project:
            raise ValueError("a Lakebase project id is required (lakebase_instance in project_config.yml)")
        self.w = workspace or WorkspaceClient()
        self.project_name = project if project.startswith("projects/") else f"projects/{project}"
        self.branch_name = branch
        self.database = database
        self._endpoint_name: str | None = None
        self._host: str | None = None

    def resolve_endpoint(self) -> tuple[str, str]:
        """Find the branch's compute endpoint and host (the first branch of the project unless one is given)."""
        if self._endpoint_name is None or self._host is None:
            app_endpoint = os.environ.get("LAKEBASE_ENDPOINT")
            if app_endpoint and os.environ.get("PGHOST"):
                self._endpoint_name, self._host = app_endpoint, os.environ["PGHOST"]
                self.database = os.environ.get("PGDATABASE", self.database)
                return self._endpoint_name, self._host
            if self.branch_name is None:
                branches = list(self.w.postgres.list_branches(parent=self.project_name))
                if not branches:
                    raise RuntimeError(f"{self.project_name} has no branches")
                self.branch_name = branches[0].name
            endpoints = list(self.w.postgres.list_endpoints(parent=self.branch_name))
            if not endpoints:
                raise RuntimeError(f"{self.branch_name} has no compute endpoint")
            self._endpoint_name = endpoints[0].name
            self._host = endpoints[0].status.hosts.host
        return self._endpoint_name, self._host

    def username(self) -> str:
        """Return the Postgres role of the current identity: a service principal's client id, else the user name."""
        if self.w.config.auth_type == "oauth-m2m" and self.w.config.client_id:
            return self.w.config.client_id
        return urllib.parse.quote_plus(self.w.current_user.me().user_name)

    def connection_string(self) -> str:
        """Build a Postgres URI with a freshly minted OAuth token for the current identity (never logged)."""
        endpoint_name, host = self.resolve_endpoint()
        credential = self.w.postgres.generate_database_credential(endpoint=endpoint_name)
        return f"postgresql://{self.username()}:{credential.token}@{host}:5432/{self.database}?sslmode=require"

    @contextmanager
    def connect(self, autocommit: bool = True) -> Iterator[psycopg.Connection]:
        """Open one connection with a fresh token; closed on exit."""
        with psycopg.connect(self.connection_string(), autocommit=autocommit) as conn:
            yield conn
