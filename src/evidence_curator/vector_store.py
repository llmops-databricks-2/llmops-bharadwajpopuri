"""Lakebase pgvector copy of the chunk table: synced-table lifecycle, indexes and the retrieval SQL.

The serving side of the retrieval foundation, the project's version of the course's
`LakebasePgVectorManager`. Delta stays the source of truth (`paper_chunks`, written by the
processing job with Change Data Feed on); a Databricks *synced table* mirrors it into the student's
Lakebase project through a managed, triggered pipeline, with `id` as primary key and `embedding`
declared `vector(1024)` so pgvector operators work on it. Nothing writes to the Postgres copy
directly: to change the index, change the Delta table and trigger an update.

Retrieval is plain SQL on that table, which is why the course prefers this route to AI Search:
metadata predicates, hybrid scoring and reranking are all under the application's control, and the
project's compute scales to zero between sessions.

Credentials: the workspace client mints a short-lived Postgres token for the current identity
(the user in VS Code or a notebook, the deployment service principal in a job); the token is used
once to open a connection and never written anywhere. The embedding model service that produced the
document vectors embeds the queries, so both live in one vector space.
"""

import re
import time
import urllib.parse
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

import psycopg
from databricks.sdk import WorkspaceClient
from databricks.sdk.errors import NotFound, ResourceDoesNotExist
from databricks.sdk.service.postgres import (
    NewPipelineSpec,
    SyncedTable,
    SyncedTableState,
    SyncedTableSyncedTableSpec,
    SyncedTableSyncedTableSpecPgSpecificType,
    SyncedTableSyncedTableSpecSyncedTableSchedulingPolicy,
    SyncedTableSyncedTableSpecTypeOverride,
)
from openai import OpenAI
from psycopg import sql

from arxiv_curator.config import ProjectConfig
from evidence_curator.chunking import SECTIONS
from evidence_curator.gateway import create_embeddings, gateway_client

EMBEDDING_DIMENSION = 1024  # GTE Large through course_ops.gateway.embed
DEFAULT_DATABASE = "databricks_postgres"  # every Lakebase branch starts with this database
RRF_K = 60  # the usual constant of reciprocal rank fusion
CANDIDATES = 50  # candidates taken from each ranking before fusion

READY_STATES = {
    SyncedTableState.SYNCED_TABLE_ONLINE,
    SyncedTableState.SYNCED_TABLE_ONLINE_NO_PENDING_UPDATE,
    SyncedTableState.SYNCED_TABLE_ONLINE_CONTINUOUS_UPDATE,
}
FAILED_STATES = {
    SyncedTableState.SYNCED_TABLE_OFFLINE_FAILED,
    SyncedTableState.SYNCED_TABLE_ONLINE_PIPELINE_FAILED,
}

RESULT_COLUMNS = (
    "id",
    "pmcid",
    "chunk_seq",
    "strategy",
    "kind",
    "section",
    "page",
    "title",
    "journal",
    "pub_year",
    "therapies",
    "nct_ids",
    "text",
)
_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass(frozen=True)
class SearchFilters:
    """Metadata predicates applied in SQL before ranking (the lecture's "filtered search")."""

    strategy: str | None = SECTIONS  # which chunking's rows to search; None searches both
    therapy: str | None = None  # canonical therapy that must be among the paper's `therapies`
    nct_id: str | None = None  # trial that must be among the paper's `nct_ids`
    year_from: int | None = None
    year_to: int | None = None
    kind: str | None = None  # text | table


def vector_literal(vector: Sequence[float]) -> str:
    """Format a vector as pgvector's text input, `[0.1,0.2,...]`."""
    return "[" + ",".join(f"{v:.8g}" for v in vector) + "]"


def filter_clauses(filters: SearchFilters, alias: str = "c") -> tuple[list[sql.Composable], list[Any]]:
    """Translate filters into SQL fragments and parameters; list-valued columns are split on commas."""
    clauses: list[sql.Composable] = []
    params: list[Any] = []
    column = sql.SQL("{}.{}").format
    a = sql.Identifier(alias)
    if filters.strategy:
        clauses.append(sql.SQL("{} = %s").format(column(a, sql.Identifier("strategy"))))
        params.append(filters.strategy)
    if filters.therapy:
        clauses.append(sql.SQL("%s = ANY(string_to_array({}, ','))").format(column(a, sql.Identifier("therapies"))))
        params.append(filters.therapy)
    if filters.nct_id:
        clauses.append(sql.SQL("%s = ANY(string_to_array({}, ','))").format(column(a, sql.Identifier("nct_ids"))))
        params.append(filters.nct_id)
    if filters.year_from is not None:
        clauses.append(sql.SQL("{} >= %s").format(column(a, sql.Identifier("pub_year"))))
        params.append(filters.year_from)
    if filters.year_to is not None:
        clauses.append(sql.SQL("{} <= %s").format(column(a, sql.Identifier("pub_year"))))
        params.append(filters.year_to)
    if filters.kind:
        clauses.append(sql.SQL("{} = %s").format(column(a, sql.Identifier("kind"))))
        params.append(filters.kind)
    return clauses, params


def fuse_ranks(
    vector_ranked: Sequence[str], text_ranked: Sequence[str], vector_weight: float = 0.5, k: int = RRF_K
) -> list[tuple[str, float]]:
    """Reciprocal rank fusion of two rankings of ids: score = w/(k+rank_v) + (1-w)/(k+rank_t).

    This is the fusion AI Search's hybrid mode describes; it combines *ranks*, so the vector
    similarity (0–1) and the full-text rank (unbounded, usually small) never have to share a scale.
    The course's own hybrid SQL uses a weighted sum of the raw scores instead, which makes the
    weighting hard to reason about; the two agree on the top results more often than not.
    """
    scores: dict[str, float] = {}
    for rank, item in enumerate(vector_ranked, start=1):
        scores[item] = scores.get(item, 0.0) + vector_weight / (k + rank)
    for rank, item in enumerate(text_ranked, start=1):
        scores[item] = scores.get(item, 0.0) + (1.0 - vector_weight) / (k + rank)
    return sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))


class LakebaseChunkStore:
    """Manage and query the Lakebase copy of a chunk table."""

    def __init__(
        self,
        config: ProjectConfig,
        workspace: WorkspaceClient | None = None,
        source_table: str = "paper_chunks",
        synced_table: str = "paper_chunks_synced",
        database: str = DEFAULT_DATABASE,
        branch: str | None = None,
        embedding_dimension: int = EMBEDDING_DIMENSION,
        embedding_client: OpenAI | None = None,
    ) -> None:
        if not config.lakebase_instance:
            raise ValueError("project_config.yml has no lakebase_instance for this environment")
        for name in (source_table, synced_table, database):
            if not _IDENT.match(name):
                raise ValueError(f"Not a plain SQL identifier: {name!r}")
        self.cfg = config
        self.w = workspace or WorkspaceClient()
        self.project_name = f"projects/{config.lakebase_instance}"
        self.branch_name = branch
        self.database = database
        self.source_table_full_name = f"{config.catalog}.{config.schema}.{source_table}"
        self.synced_table_id = f"{config.catalog}.{config.schema}.{synced_table}"
        self.pg_schema = config.schema
        self.pg_table = synced_table
        self.embedding_dimension = embedding_dimension
        self._embedding_client = embedding_client
        self._endpoint_name: str | None = None
        self._host: str | None = None

    # ------------------------------------------------------------------ connection

    def resolve_endpoint(self) -> tuple[str, str]:
        """Find the branch's compute endpoint and host (the first branch of the project unless one is given)."""
        if self._endpoint_name is None or self._host is None:
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

    def connection_string(self) -> str:
        """Build a Postgres URI with a freshly minted OAuth token for the current identity (never logged)."""
        endpoint_name, host = self.resolve_endpoint()
        credential = self.w.postgres.generate_database_credential(endpoint=endpoint_name)
        # A service principal (OAuth M2M, as in a deployment job) logs in as its client id; a person as their user name.
        if self.w.config.auth_type == "oauth-m2m" and self.w.config.client_id:
            username = self.w.config.client_id
        else:
            username = urllib.parse.quote_plus(self.w.current_user.me().user_name)
        return f"postgresql://{username}:{credential.token}@{host}:5432/{self.database}?sslmode=require"

    @contextmanager
    def connect(self, autocommit: bool = True) -> Iterator[psycopg.Connection]:
        """Open one connection with a fresh token; closed on exit."""
        with psycopg.connect(self.connection_string(), autocommit=autocommit) as conn:
            yield conn

    # ------------------------------------------------------------------ synced table

    def synced_table_spec(self) -> SyncedTableSyncedTableSpec:
        """Build the synced-table specification: triggered, keyed on `id`, with `embedding` as a pgvector column."""
        if self.branch_name is None:
            self.resolve_endpoint()
        return SyncedTableSyncedTableSpec(
            source_table_full_name=self.source_table_full_name,
            primary_key_columns=["id"],
            scheduling_policy=SyncedTableSyncedTableSpecSyncedTableSchedulingPolicy.TRIGGERED,
            branch=self.branch_name,
            postgres_database=self.database,
            create_database_objects_if_missing=True,
            type_overrides=[
                SyncedTableSyncedTableSpecTypeOverride(
                    column_name="embedding",
                    pg_type=SyncedTableSyncedTableSpecPgSpecificType.PG_SPECIFIC_TYPE_VECTOR,
                    size=self.embedding_dimension,
                )
            ],
            new_pipeline_spec=NewPipelineSpec(
                budget_policy_id=self.cfg.usage_policy_id,
                storage_catalog=self.cfg.catalog,
                storage_schema=self.cfg.schema,
            ),
        )

    def get_synced_table(self) -> SyncedTable | None:
        """Fetch the synced table's current record, or None when it does not exist yet."""
        try:
            return self.w.postgres.get_synced_table(name=f"synced_tables/{self.synced_table_id}")
        except (NotFound, ResourceDoesNotExist):
            return None

    def ensure_extension(self) -> None:
        """Install pgvector in the target database (needed before the vector type override can apply)."""
        with self.connect() as conn:
            conn.execute("CREATE EXTENSION IF NOT EXISTS vector")

    def create_synced_table(self, timeout_s: float = 1800) -> SyncedTable:
        """Create the synced table and wait for its initial snapshot."""
        operation = self.w.postgres.create_synced_table(
            synced_table=SyncedTable(spec=self.synced_table_spec()), synced_table_id=self.synced_table_id
        )
        operation.wait()
        return self.wait_until_synced(timeout_s)

    def trigger_update(self, timeout_s: float = 1800) -> dict[str, Any]:
        """Start one update of the existing synced table's pipeline and wait for that update to finish.

        An already-online table proves nothing about freshness: only the completion of the update
        started here says the Postgres copy holds the source's current rows.
        """
        table = self.get_synced_table()
        if table is None or table.status is None or not table.status.pipeline_id:
            raise RuntimeError(f"{self.synced_table_id} has no pipeline to trigger; create it first")
        pipeline_id = table.status.pipeline_id
        started = self.w.pipelines.start_update(pipeline_id=pipeline_id)
        deadline = time.time() + timeout_s
        while True:
            update = self.w.pipelines.get_update(pipeline_id=pipeline_id, update_id=started.update_id).update
            state = update.state.value if update and update.state else None
            if state == "COMPLETED":
                self.wait_until_synced(max(deadline - time.time(), 60))
                return {"pipeline_id": pipeline_id, "update_id": started.update_id, "state": state}
            if state in {"FAILED", "CANCELED"}:
                raise RuntimeError(f"synced-table update {started.update_id} ended {state}")
            if time.time() > deadline:
                raise TimeoutError(f"synced-table update {started.update_id} still {state} after {timeout_s}s")
            time.sleep(15)

    def create_or_update(self, timeout_s: float = 1800) -> SyncedTable:
        """Create the synced table if missing, otherwise trigger and wait for one update."""
        if self.get_synced_table() is None:
            return self.create_synced_table(timeout_s)
        self.trigger_update(timeout_s)
        return self.get_synced_table()

    def wait_until_synced(self, timeout_s: float = 1800, poll_s: float = 15) -> SyncedTable:
        """Poll the synced table until it is online with no update in flight; fail on a failed state."""
        deadline = time.time() + timeout_s
        while True:
            table = self.get_synced_table()
            state = table.status.detailed_state if table and table.status else None
            if state in READY_STATES:
                return table
            if state in FAILED_STATES:
                raise RuntimeError(f"{self.synced_table_id} is {state.value}: {table.status.message}")
            if time.time() > deadline:
                raise TimeoutError(f"{self.synced_table_id} still {state} after {timeout_s}s")
            time.sleep(poll_s)

    # ------------------------------------------------------------------ indexes and checks

    @property
    def table(self) -> sql.Composed:
        """The schema-qualified Postgres table."""
        return sql.SQL("{}.{}").format(sql.Identifier(self.pg_schema), sql.Identifier(self.pg_table))

    @property
    def document_tsvector(self) -> sql.Composed:
        """The full-text expression: title and chunk text, English stemming (must match the GIN index)."""
        return sql.SQL("to_tsvector('english', coalesce({t}.title, '') || ' ' || coalesce({t}.text, ''))").format(
            t=sql.Identifier("c")
        )

    def ensure_indexes(self, hnsw: bool = True) -> list[str]:
        """Create the full-text GIN index and, by default, an HNSW index for cosine search; returns their names.

        The course leaves HNSW out because its optional Lakebase Search example puts a `lakebase_ann`
        index on the same column; this project does not use that Beta route, so the pgvector index is
        created here. On a few thousand rows an exact scan is fast anyway; the index is for the pattern.
        """
        names = [f"{self.pg_table}_fts_gin"]
        statements = [
            sql.SQL(
                "CREATE INDEX IF NOT EXISTS {name} ON {table} USING GIN "
                "(to_tsvector('english', coalesce(title, '') || ' ' || coalesce(text, '')))"
            ).format(name=sql.Identifier(names[0]), table=self.table)
        ]
        if hnsw:
            names.append(f"{self.pg_table}_embedding_hnsw")
            statements.append(
                sql.SQL("CREATE INDEX IF NOT EXISTS {name} ON {table} USING hnsw (embedding vector_cosine_ops)").format(
                    name=sql.Identifier(names[1]), table=self.table
                )
            )
        with self.connect() as conn:
            for statement in statements:
                conn.execute(statement)
        return names

    def inspect(self) -> dict[str, Any]:
        """Check what the lecture says to check in the database itself: type, rows, null vectors, indexes."""
        with self.connect() as conn:
            row_count = conn.execute(sql.SQL("SELECT count(*) FROM {}").format(self.table)).fetchone()[0]
            null_vectors = conn.execute(
                sql.SQL("SELECT count(*) FROM {} WHERE embedding IS NULL").format(self.table)
            ).fetchone()[0]
            vector_type = conn.execute(
                sql.SQL("SELECT pg_typeof(embedding)::text FROM {} LIMIT 1").format(self.table)
            ).fetchone()
            try:
                dims = conn.execute(
                    sql.SQL("SELECT vector_dims(embedding) FROM {} LIMIT 1").format(self.table)
                ).fetchone()
            except psycopg.Error:  # not a pgvector column: the type override did not apply
                dims = None
            indexes = conn.execute(
                "SELECT indexname, indexdef FROM pg_indexes WHERE schemaname = %s AND tablename = %s ORDER BY indexname",
                (self.pg_schema, self.pg_table),
            ).fetchall()
            by_strategy = conn.execute(
                sql.SQL("SELECT strategy, count(*) FROM {} GROUP BY strategy ORDER BY strategy").format(self.table)
            ).fetchall()
            extension = conn.execute("SELECT extversion FROM pg_extension WHERE extname = 'vector'").fetchone()
        return {
            "table": f"{self.pg_schema}.{self.pg_table}",
            "row_count": row_count,
            "null_vectors": null_vectors,
            "embedding_type": vector_type[0] if vector_type else None,
            "embedding_dims": dims[0] if dims else None,
            "rows_by_strategy": dict(by_strategy),
            "indexes": [{"name": name, "definition": definition} for name, definition in indexes],
            "pgvector_version": extension[0] if extension else None,
        }

    # ------------------------------------------------------------------ retrieval

    @property
    def embedding_client(self) -> OpenAI:
        """The gateway client that embeds queries with the document model service."""
        if self._embedding_client is None:
            self._embedding_client = gateway_client(self.w)
        return self._embedding_client

    def embed_query(self, query: str) -> list[float]:
        """Embed a question with `cfg.embedding_service`, the gateway service that embedded the chunks.

        The gateway client takes the model service name; `cfg.embedding_endpoint` is the serving
        endpoint of the same model, for `ai_query` and agent resources, and the gateway refuses it.
        """
        response = create_embeddings(self.embedding_client, self.cfg.embedding_service, [query])
        return list(response.data[0].embedding)

    def _select(self, extra: sql.Composable) -> sql.Composed:
        columns = sql.SQL(", ").join(sql.SQL("c.{}").format(sql.Identifier(col)) for col in RESULT_COLUMNS)
        return sql.SQL("SELECT {cols}, {extra} FROM {table} AS c").format(cols=columns, extra=extra, table=self.table)

    @staticmethod
    def _where(clauses: list[sql.Composable]) -> sql.Composable:
        if not clauses:
            return sql.SQL("")
        return sql.SQL(" WHERE ") + sql.SQL(" AND ").join(clauses)

    def _rows(self, conn: psycopg.Connection, statement: sql.Composed, params: Sequence[Any]) -> list[dict[str, Any]]:
        cursor = conn.execute(statement, params)
        names = [d.name for d in cursor.description]
        return [dict(zip(names, row, strict=True)) for row in cursor.fetchall()]

    def search(
        self,
        query: str,
        num_results: int = 5,
        filters: SearchFilters | None = None,
        query_vector: Sequence[float] | None = None,
    ) -> list[dict[str, Any]]:
        """Semantic search: cosine similarity between the query vector and stored vectors, after the filters.

        Returns rows with `score` = 1 − cosine distance (higher is closer). `query_vector` lets a
        caller reuse one embedding across several searches of the same question.
        """
        filters = filters or SearchFilters()
        vector = vector_literal(query_vector or self.embed_query(query))
        clauses, params = filter_clauses(filters)
        clauses.insert(0, sql.SQL("c.embedding IS NOT NULL"))
        statement = (
            self._select(sql.SQL("1 - (c.embedding <=> %s::vector) AS score"))
            + self._where(clauses)
            + sql.SQL(" ORDER BY c.embedding <=> %s::vector LIMIT %s")
        )
        with self.connect() as conn:
            return self._rows(conn, statement, [vector, *params, vector, num_results])

    def keyword_search(
        self,
        query: str,
        num_results: int = 5,
        filters: SearchFilters | None = None,
        require_all_terms: bool = False,
    ) -> list[dict[str, Any]]:
        """Full-text search alone: PostgreSQL full text over title and chunk text, ranked by `ts_rank_cd`.

        The keyword-only view that AI Search calls `FULL_TEXT`; useful on its own to see what exact
        terms (acronyms, trial names, doses) retrieve that semantic similarity misses.

        By default a chunk qualifies when it matches *any* stemmed term of the question, chunks that
        match *every* term rank first, and `ts_rank_cd` (cover density) orders the rest. The first
        experiment ran with `websearch_to_tsquery`, which requires every term: half of the eight
        questions returned no rows at all, and hybrid search degenerated to semantic on them.
        `require_all_terms=True` keeps that behaviour for comparison. Postgres ranking has no IDF, so a
        common word weighs as much as a trial name; `all_terms` in the result row says which rows matched
        the whole question.
        """
        filters = filters or SearchFilters()
        clauses, params = filter_clauses(filters)
        all_terms = sql.SQL("plainto_tsquery('english', %s)")
        any_term = sql.SQL("replace(plainto_tsquery('english', %s)::text, ' & ', ' | ')::tsquery")
        match = all_terms if require_all_terms else any_term
        clauses.insert(0, sql.SQL("{} @@ {}").format(self.document_tsvector, match))
        statement = (
            self._select(
                sql.SQL("ts_rank_cd({tsv}, {rank_q}) AS score, ({tsv} @@ {all_q}) AS all_terms").format(
                    tsv=self.document_tsvector, rank_q=match, all_q=all_terms
                )
            )
            + self._where(clauses)
            + sql.SQL(" ORDER BY all_terms DESC, score DESC, c.id LIMIT %s")
        )
        with self.connect() as conn:
            return self._rows(conn, statement, [query, query, query, *params, num_results])

    def hybrid_search(
        self,
        query: str,
        num_results: int = 5,
        filters: SearchFilters | None = None,
        vector_weight: float = 0.5,
        candidates: int = CANDIDATES,
        query_vector: Sequence[float] | None = None,
    ) -> list[dict[str, Any]]:
        """Hybrid search: reciprocal rank fusion of the semantic and the full-text rankings.

        Each ranking contributes its top `candidates`; a chunk found by both rises, a chunk found by
        one only can still make the cut. `vector_weight` tilts the fusion (0.5 treats both equally).
        Rows carry `score` (the fused score), `vector_rank` and `text_rank` (None when absent).
        """
        filters = filters or SearchFilters()
        vector = query_vector or self.embed_query(query)
        semantic = self.search(query, candidates, filters, query_vector=vector)
        lexical = self.keyword_search(query, candidates, filters)
        by_id = {row["id"]: row for row in semantic} | {row["id"]: row for row in lexical}
        vector_rank = {row["id"]: rank for rank, row in enumerate(semantic, start=1)}
        text_rank = {row["id"]: rank for rank, row in enumerate(lexical, start=1)}
        fused = fuse_ranks([r["id"] for r in semantic], [r["id"] for r in lexical], vector_weight)
        results: list[dict[str, Any]] = []
        vector_score = {row["id"]: row["score"] for row in semantic}
        text_score = {row["id"]: row["score"] for row in lexical}
        for chunk_id, score in fused[:num_results]:
            row = dict(by_id[chunk_id])
            row.update(
                score=round(score, 6),
                vector_rank=vector_rank.get(chunk_id),
                text_rank=text_rank.get(chunk_id),
                vector_score=vector_score.get(chunk_id),
                text_score=text_score.get(chunk_id),
            )
            results.append(row)
        return results
