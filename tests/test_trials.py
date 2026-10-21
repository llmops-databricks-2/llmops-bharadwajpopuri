"""Tests for the ClinicalTrials.gov ingestion: recorded API responses in, table rows out.

No network: `tests/fixtures/ctgov_two_studies.json` is a trimmed API v2 response for STEP 1 and
SURMOUNT-1 recorded on 2026-10-14. Fetching is covered by the job run, not by unit tests.
"""

import json
import re
from datetime import UTC, datetime
from pathlib import Path

import pytest

from evidence_curator.aliases import DRUG_ALIASES, canonical_therapy
from evidence_curator.seed import SEED_TRIALS, seed_by_id
from evidence_curator.trials import (
    ALIASES_SCHEMA,
    REFERENCES_SCHEMA,
    TRIALS_SCHEMA,
    alias_rows,
    build_snapshot,
    columns_of,
    flatten_study,
    rows_in_schema_order,
    studies_url,
    study_references,
)

FIXTURE = Path(__file__).parent / "fixtures" / "ctgov_two_studies.json"
RETRIEVED = datetime(2026, 10, 14, 12, 0, tzinfo=UTC)


@pytest.fixture
def studies() -> list[dict]:
    """Load the two recorded studies."""
    return json.loads(FIXTURE.read_text())["studies"]


def test_seed_ids_are_unique_and_well_formed() -> None:
    """The snapshot is a fixed list of valid, distinct NCT IDs with a canonical therapy each."""
    ids = [t.nct_id for t in SEED_TRIALS]
    assert len(ids) == len(set(ids))
    assert all(re.fullmatch(r"NCT\d{8}", i) for i in ids)
    assert {t.therapy for t in SEED_TRIALS} == {"semaglutide", "tirzepatide", "liraglutide"}
    assert 20 <= len(ids) <= 30


def test_aliases_resolve_brand_code_and_dose_forms() -> None:
    """Any spelling of a therapy maps to its canonical name; placebo and class names do not."""
    assert canonical_therapy("Wegovy") == "semaglutide"
    assert canonical_therapy("LY3298176") == "tirzepatide"
    assert canonical_therapy("Semaglutide 2.4 mg") == "semaglutide"
    assert canonical_therapy("liraglutide 3.0 mg once daily") == "liraglutide"
    assert canonical_therapy("Placebo") is None
    assert canonical_therapy("GLP-1 receptor agonist") is None
    assert len({(a.therapy, a.alias) for a in DRUG_ALIASES}) == len(DRUG_ALIASES)


def test_flatten_study_maps_registry_fields(studies: list[dict]) -> None:
    """The flattened row carries the registry facts and the curator's labels, typed for the schema."""
    surmount_1 = next(s for s in studies if s["protocolSection"]["identificationModule"]["nctId"] == "NCT04184622")
    row = flatten_study(surmount_1, seed_by_id()["NCT04184622"], RETRIEVED)

    assert row["nct_id"] == "NCT04184622"
    assert row["therapy"] == "tirzepatide"
    assert row["program"] == "SURMOUNT"
    assert row["acronym"] == "SURMOUNT-1"
    assert row["phase"] == "PHASE3"
    assert row["overall_status"] == "COMPLETED"
    assert row["lead_sponsor"] == "Eli Lilly and Company"
    assert row["enrollment_count"] == 2539
    assert row["has_results"] is True
    assert row["start_date"] == "2019-12-04"
    assert row["intervention_therapies"] == "tirzepatide"
    assert row["interventions"] == "DRUG: Tirzepatide | DRUG: Placebo"
    assert row["primary_outcomes"].startswith("Percent Change From Baseline in Body Weight")
    assert row["n_primary_outcomes"] >= 1
    assert row["source_url"] == "https://clinicaltrials.gov/study/NCT04184622"
    assert row["retrieved_at"] == RETRIEVED
    assert set(row) == set(columns_of(TRIALS_SCHEMA))


def test_references_keep_pmid_links(studies: list[dict]) -> None:
    """Registry publication links become reference rows keyed by NCT ID and PMID."""
    rows = study_references(studies[0], RETRIEVED)
    assert rows, "fixture study has references"
    assert all(re.fullmatch(r"\d+", r["pmid"]) for r in rows)
    assert all(r["reference_type"] in {"BACKGROUND", "RESULT", "DERIVED"} for r in rows)
    assert set(rows[0]) == set(columns_of(REFERENCES_SCHEMA))


def test_build_snapshot_reports_missing_ids(studies: list[dict]) -> None:
    """Rows come back in seed order and seed IDs absent from the API response are listed, not dropped silently."""
    trial_rows, reference_rows, missing = build_snapshot(studies, retrieved_at=RETRIEVED)
    assert [r["nct_id"] for r in trial_rows] == ["NCT03548935", "NCT04184622"]
    assert len(reference_rows) == 6
    assert len(missing) == len(SEED_TRIALS) - 2
    assert "NCT01272219" in missing


def test_rows_follow_schema_order() -> None:
    """Tuples are built in DDL column order so Spark receives positional rows that match the schema."""
    assert columns_of(ALIASES_SCHEMA) == ["therapy", "alias", "alias_type"]
    rows = rows_in_schema_order(alias_rows(), ALIASES_SCHEMA)
    assert rows[0] == ("semaglutide", "semaglutide", "inn")
    assert len(rows) == len(DRUG_ALIASES)


def test_studies_url_pins_fields_and_ids() -> None:
    """The request narrows the payload to the modules we store and carries the IDs as a filter."""
    url = studies_url(["NCT03548935", "NCT04184622"], page_size=50)
    assert url.startswith("https://clinicaltrials.gov/api/v2/studies?")
    assert "filter.ids=NCT03548935%2CNCT04184622" in url
    assert "protocolSection.referencesModule" in url
    assert "pageSize=50" in url
