"""Tests of the Lakebase chunk store's pure parts: SQL fragments, rank fusion, the synced-table spec, waiting.

No Postgres, no workspace: the SDK client is a stub. The connection, sync and search paths are
exercised by the sync job and the retrieval notebook, whose output is kept under docs/.
"""

from pathlib import Path

import pytest
from databricks.sdk.service.postgres import (
    SyncedTable,
    SyncedTableState,
    SyncedTableSyncedTableSpecPgSpecificType,
    SyncedTableSyncedTableSpecSyncedTableSchedulingPolicy,
    SyncedTableSyncedTableStatus,
)
from psycopg import sql

from arxiv_curator.config import ProjectConfig
from evidence_curator.vector_store import (
    LakebaseChunkStore,
    SearchFilters,
    filter_clauses,
    fuse_ranks,
    vector_literal,
)

PROJECT_CONFIG = Path(__file__).resolve().parents[1] / "project_config.yml"


class _Postgres:
    """Stub of `w.postgres` with one branch, one endpoint and a scripted sequence of synced-table states."""

    def __init__(self, states: list[SyncedTableState | None]) -> None:
        self.states = list(states)
        self.calls = 0

    def list_branches(self, parent: str) -> list:
        return [type("Branch", (), {"name": f"{parent}/branches/production"})()]

    def list_endpoints(self, parent: str) -> list:
        hosts = type("Hosts", (), {"host": "ep-test.database.cloud.databricks.com"})()
        status = type("Status", (), {"hosts": hosts})()
        return [type("Endpoint", (), {"name": f"{parent}/endpoints/primary", "status": status})()]

    def get_synced_table(self, name: str) -> SyncedTable:
        self.calls += 1
        state = self.states.pop(0) if self.states else SyncedTableState.SYNCED_TABLE_ONLINE_NO_PENDING_UPDATE
        return SyncedTable(name=name, status=SyncedTableTableStatus(state))


def SyncedTableTableStatus(state: SyncedTableState | None) -> SyncedTableSyncedTableStatus:  # noqa: N802 - reads like the SDK
    """Build a status record with a detailed state and a pipeline id."""
    return SyncedTableSyncedTableStatus(detailed_state=state, pipeline_id="pipe-1", message=f"state {state}")


class _Workspace:
    def __init__(self, states: list[SyncedTableState | None] | None = None) -> None:
        self.postgres = _Postgres(states or [])
        self.config = type("Config", (), {"client_id": None})()


@pytest.fixture
def cfg() -> ProjectConfig:
    """Load the real dev configuration, which carries the provisioned Lakebase project and usage policy."""
    return ProjectConfig.from_yaml(str(PROJECT_CONFIG), "dev")


def test_config_exposes_lakebase_project_and_usage_policy(cfg: ProjectConfig) -> None:
    """The two provisioned values the sync needs are read from project_config.yml."""
    assert cfg.lakebase_instance == "lb-llmops-bharadwajpopuri"
    assert cfg.usage_policy_id == "995f545e-7885-3c66-9825-046d051e0122"


def test_vector_literal_is_pgvector_text_input() -> None:
    """Vectors are passed as `[x,y,...]` text and cast in SQL."""
    assert vector_literal([0.1, -0.25, 1.0]) == "[0.1,-0.25,1]"


def test_filter_clauses_cover_every_filter_and_split_list_columns() -> None:
    """Each filter becomes one parameterised clause; list-valued columns are matched element-wise."""
    filters = SearchFilters(
        strategy="section", therapy="semaglutide", nct_id="NCT03548935", year_from=2022, year_to=2026, kind="table"
    )

    clauses, params = filter_clauses(filters)

    assert len(clauses) == 6 and params == ["section", "semaglutide", "NCT03548935", 2022, 2026, "table"]
    rendered = [c.as_string(None) for c in clauses]
    assert rendered[1] == '%s = ANY(string_to_array("c"."therapies", \',\'))'
    assert rendered[3] == '"c"."pub_year" >= %s'
    assert filter_clauses(SearchFilters(strategy=None)) == ([], [])
    assert SearchFilters().strategy == "section"  # the chosen chunking is the default search space


def test_fuse_ranks_rewards_agreement_and_keeps_singletons() -> None:
    """Reciprocal rank fusion: items in both lists rise; an item in one list only still gets a score."""
    fused = fuse_ranks(["a", "b", "c"], ["b", "a", "d"], vector_weight=0.5, k=60)

    order = [item for item, _ in fused]
    assert order[:2] == ["a", "b"] and set(order[2:]) == {"c", "d"}
    scores = dict(fused)
    assert scores["a"] == pytest.approx(0.5 / 61 + 0.5 / 62)
    assert scores["d"] == pytest.approx(0.5 / 63)
    # Weight tilts the fusion towards one ranking.
    assert [item for item, _ in fuse_ranks(["a", "b"], ["b", "a"], vector_weight=1.0)] == ["a", "b"]
    assert [item for item, _ in fuse_ranks(["a", "b"], ["b", "a"], vector_weight=0.0)] == ["b", "a"]


def test_synced_table_spec_matches_the_lecture_recipe(cfg: ProjectConfig) -> None:
    """Triggered policy, `id` key, `embedding` → vector(1024), pipeline under the usage policy in the student's schema."""
    store = LakebaseChunkStore(cfg, workspace=_Workspace())  # type: ignore[arg-type]

    spec = store.synced_table_spec()

    assert spec.source_table_full_name == "llmops_dev.bharadwajpopuri.paper_chunks"
    assert store.synced_table_id == "llmops_dev.bharadwajpopuri.paper_chunks_synced"
    assert spec.primary_key_columns == ["id"]
    assert spec.scheduling_policy == SyncedTableSyncedTableSpecSyncedTableSchedulingPolicy.TRIGGERED
    assert spec.branch == "projects/lb-llmops-bharadwajpopuri/branches/production"
    assert spec.postgres_database == "databricks_postgres" and spec.create_database_objects_if_missing is True
    override = spec.type_overrides[0]
    assert (override.column_name, override.pg_type, override.size) == (
        "embedding",
        SyncedTableSyncedTableSpecPgSpecificType.PG_SPECIFIC_TYPE_VECTOR,
        1024,
    )
    assert spec.new_pipeline_spec.budget_policy_id == cfg.usage_policy_id
    assert (spec.new_pipeline_spec.storage_catalog, spec.new_pipeline_spec.storage_schema) == (
        "llmops_dev",
        "bharadwajpopuri",
    )
    assert store.table.as_string(None) == '"bharadwajpopuri"."paper_chunks_synced"'


def test_store_rejects_missing_project_and_odd_identifiers(cfg: ProjectConfig) -> None:
    """A configuration without a Lakebase project, or a table name that is not an identifier, is refused early."""
    with pytest.raises(ValueError, match="Not a plain SQL identifier"):
        LakebaseChunkStore(cfg, workspace=_Workspace(), synced_table="chunks; drop table x")  # type: ignore[arg-type]
    bare = cfg.model_copy(update={"lakebase_instance": None})
    with pytest.raises(ValueError, match="lakebase_instance"):
        LakebaseChunkStore(bare, workspace=_Workspace())  # type: ignore[arg-type]


def test_wait_until_synced_polls_to_ready_and_raises_on_failure(
    cfg: ProjectConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Provisioning states are waited out; a failed state raises with the platform's message."""
    monkeypatch.setattr("evidence_curator.vector_store.time.sleep", lambda _: None)
    workspace = _Workspace(
        [
            SyncedTableState.SYNCED_TABLE_PROVISIONING,
            SyncedTableState.SYNCED_TABLE_PROVISIONING_INITIAL_SNAPSHOT,
            SyncedTableState.SYNCED_TABLE_ONLINE_NO_PENDING_UPDATE,
        ]
    )
    store = LakebaseChunkStore(cfg, workspace=workspace)  # type: ignore[arg-type]

    table = store.wait_until_synced(timeout_s=60, poll_s=0)

    assert table.status.detailed_state == SyncedTableState.SYNCED_TABLE_ONLINE_NO_PENDING_UPDATE
    assert workspace.postgres.calls == 3

    failing = LakebaseChunkStore(cfg, workspace=_Workspace([SyncedTableState.SYNCED_TABLE_ONLINE_PIPELINE_FAILED]))  # type: ignore[arg-type]
    with pytest.raises(RuntimeError, match="SYNCED_TABLE_ONLINE_PIPELINE_FAILED"):
        failing.wait_until_synced(timeout_s=60, poll_s=0)


def test_search_sql_is_composed_with_identifiers_quoted(cfg: ProjectConfig) -> None:
    """The full-text expression and the result projection are built from quoted identifiers, never f-strings."""
    store = LakebaseChunkStore(cfg, workspace=_Workspace())  # type: ignore[arg-type]

    assert isinstance(store.document_tsvector, sql.Composed)
    assert store.document_tsvector.as_string(None) == (
        "to_tsvector('english', coalesce(\"c\".title, '') || ' ' || coalesce(\"c\".text, ''))"
    )
    statement = store._select(sql.SQL("1 AS score")).as_string(None)
    assert statement.startswith('SELECT c."id", c."pmcid", c."chunk_seq"') and statement.endswith(
        'FROM "bharadwajpopuri"."paper_chunks_synced" AS c'
    )
