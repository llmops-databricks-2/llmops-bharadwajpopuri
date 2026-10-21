"""ClinicalTrials.gov API v2 ingestion: fetch pinned trials and flatten them into table rows.

This module is pure Python so it can be unit-tested with recorded API responses and reused from a
notebook, a job, or a local script. Spark enters only in the notebook that writes the Delta tables.

Provenance rules of the project are applied here: every row carries the retrieval timestamp and the
source URL, registry metadata (planned endpoints, enrollment, dates) is kept separate from reported
findings (which live in papers), and the registry's own publication links are preserved as rows of
their own so the agent can join trials to papers without guessing.
"""

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterable, Iterator, Sequence
from datetime import UTC, datetime
from typing import Any

import backoff

from evidence_curator.aliases import DRUG_ALIASES, canonical_therapy
from evidence_curator.seed import SEED_TRIALS, SeedTrial

API_BASE = "https://clinicaltrials.gov/api/v2/studies"
SOURCE = "ClinicalTrials.gov API v2"
USER_AGENT = "evidence-curator/0.1 (LLMOps course project; contact via GitHub llmops-bharadwajpopuri)"

# The modules we need; the API returns everything (including posted results, which can be megabytes
# per trial) unless `fields` narrows it.
FIELDS = (
    "protocolSection.identificationModule",
    "protocolSection.statusModule",
    "protocolSection.sponsorCollaboratorsModule",
    "protocolSection.conditionsModule",
    "protocolSection.designModule",
    "protocolSection.armsInterventionsModule",
    "protocolSection.outcomesModule",
    "protocolSection.eligibilityModule",
    "protocolSection.referencesModule",
    "hasResults",
)

# Delta table layouts, as Spark DDL. Flat columns only: easy for SQL, Genie and the agent's query tool.
TRIALS_SCHEMA = (
    "nct_id STRING, therapy STRING, program STRING, seed_note STRING, acronym STRING, "
    "brief_title STRING, official_title STRING, study_type STRING, phase STRING, overall_status STRING, "
    "lead_sponsor STRING, sponsor_class STRING, collaborators STRING, conditions STRING, "
    "interventions STRING, intervention_therapies STRING, enrollment_count INT, enrollment_type STRING, "
    "allocation STRING, intervention_model STRING, masking STRING, primary_purpose STRING, "
    "primary_outcomes STRING, n_primary_outcomes INT, start_date STRING, primary_completion_date STRING, "
    "completion_date STRING, sex STRING, minimum_age STRING, maximum_age STRING, eligibility_criteria STRING, "
    "has_results BOOLEAN, results_first_post_date STRING, last_update_post_date STRING, n_references INT, "
    "source STRING, source_url STRING, retrieved_at TIMESTAMP"
)
REFERENCES_SCHEMA = (
    "nct_id STRING, pmid STRING, reference_type STRING, citation STRING, source STRING, retrieved_at TIMESTAMP"
)
ALIASES_SCHEMA = "therapy STRING, alias STRING, alias_type STRING"

_NCT = re.compile(r"^NCT\d{8}$")


def columns_of(ddl: str) -> list[str]:
    """Column names of a flat DDL schema string, in order."""
    return [part.strip().split(" ")[0] for part in ddl.split(",")]


def rows_in_schema_order(records: Iterable[dict[str, Any]], ddl: str) -> list[tuple]:
    """Turn dict records into tuples ordered like the schema, so Spark never has to guess by name."""
    cols = columns_of(ddl)
    return [tuple(record.get(col) for col in cols) for record in records]


def _batched(items: Sequence[str], size: int) -> Iterator[Sequence[str]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]


@backoff.on_exception(backoff.expo, (urllib.error.URLError, TimeoutError), max_tries=4, max_time=90)
def _get_json(url: str, timeout: float) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


def studies_url(nct_ids: Sequence[str], page_token: str | None = None, page_size: int = 100) -> str:
    """Build the API URL for a batch of NCT IDs (also recorded on every row as `source_url`)."""
    params: dict[str, str | int] = {
        "filter.ids": ",".join(nct_ids),
        "fields": ",".join(FIELDS),
        "pageSize": page_size,
        "format": "json",
    }
    if page_token:
        params["pageToken"] = page_token
    return f"{API_BASE}?{urllib.parse.urlencode(params)}"


def fetch_studies(nct_ids: Sequence[str], batch_size: int = 25, timeout: float = 60.0) -> list[dict[str, Any]]:
    """Fetch raw study records for the given NCT IDs, in batches, following pagination.

    One request per 25 IDs keeps URLs short and stays far below the API's rate limit; the whole
    30-trial snapshot is two requests.
    """
    bad = [i for i in nct_ids if not _NCT.match(i)]
    if bad:
        raise ValueError(f"Not NCT IDs: {bad}")
    studies: list[dict[str, Any]] = []
    for batch in _batched(list(nct_ids), batch_size):
        token: str | None = None
        while True:
            page = _get_json(studies_url(batch, token), timeout)
            studies.extend(page.get("studies", []))
            token = page.get("nextPageToken")
            if not token:
                break
    return studies


def _join(values: Iterable[str | None], sep: str = " | ") -> str | None:
    cleaned = [v.strip() for v in values if v and v.strip()]
    return sep.join(cleaned) if cleaned else None


def _date(struct: dict[str, Any] | None) -> str | None:
    return (struct or {}).get("date")


def flatten_study(study: dict[str, Any], seed: SeedTrial | None, retrieved_at: datetime) -> dict[str, Any]:
    """Flatten one API study record into a row of the `trials` table.

    Registry fields are copied as the registry states them (status, dates, enrollment, planned
    primary outcomes). The curator's own labels (therapy, program, seed_note) come from the seed list,
    and `intervention_therapies` records which of the three therapies appear among the interventions,
    so head-to-head trials (STEP 8, SURMOUNT-5) are visible under both therapies.
    """
    p = study.get("protocolSection", {})
    ident = p.get("identificationModule", {})
    status = p.get("statusModule", {})
    sponsor = p.get("sponsorCollaboratorsModule", {})
    design = p.get("designModule", {})
    design_info = design.get("designInfo", {})
    arms = p.get("armsInterventionsModule", {})
    outcomes = p.get("outcomesModule", {})
    elig = p.get("eligibilityModule", {})
    conditions = p.get("conditionsModule", {})
    interventions = arms.get("interventions", [])
    primary = outcomes.get("primaryOutcomes", [])
    references = p.get("referencesModule", {}).get("references", [])

    intervention_names = [i.get("name") for i in interventions] + [
        other for i in interventions for other in i.get("otherNames", [])
    ]
    therapies = sorted({t for t in (canonical_therapy(n) for n in intervention_names if n) if t})
    nct_id = ident.get("nctId")

    return {
        "nct_id": nct_id,
        "therapy": seed.therapy if seed else None,
        "program": seed.program if seed else None,
        "seed_note": seed.note if seed else None,
        "acronym": ident.get("acronym"),
        "brief_title": ident.get("briefTitle"),
        "official_title": ident.get("officialTitle"),
        "study_type": design.get("studyType"),
        "phase": _join(design.get("phases", []), sep="/"),
        "overall_status": status.get("overallStatus"),
        "lead_sponsor": sponsor.get("leadSponsor", {}).get("name"),
        "sponsor_class": sponsor.get("leadSponsor", {}).get("class"),
        "collaborators": _join(c.get("name") for c in sponsor.get("collaborators", [])),
        "conditions": _join(conditions.get("conditions", [])),
        "interventions": _join(f"{i.get('type', '?')}: {i.get('name', '?')}" for i in interventions),
        "intervention_therapies": _join(therapies, sep=","),
        "enrollment_count": design.get("enrollmentInfo", {}).get("count"),
        "enrollment_type": design.get("enrollmentInfo", {}).get("type"),
        "allocation": design_info.get("allocation"),
        "intervention_model": design_info.get("interventionModel"),
        "masking": design_info.get("maskingInfo", {}).get("masking"),
        "primary_purpose": design_info.get("primaryPurpose"),
        "primary_outcomes": _join(f"{o.get('measure', '?')} [{o.get('timeFrame', '?')}]" for o in primary),
        "n_primary_outcomes": len(primary),
        "start_date": _date(status.get("startDateStruct")),
        "primary_completion_date": _date(status.get("primaryCompletionDateStruct")),
        "completion_date": _date(status.get("completionDateStruct")),
        "sex": elig.get("sex"),
        "minimum_age": elig.get("minimumAge"),
        "maximum_age": elig.get("maximumAge"),
        "eligibility_criteria": elig.get("eligibilityCriteria"),
        "has_results": bool(study.get("hasResults", False)),
        "results_first_post_date": _date(status.get("resultsFirstPostDateStruct")),
        "last_update_post_date": _date(status.get("lastUpdatePostDateStruct")),
        "n_references": len(references),
        "source": SOURCE,
        "source_url": f"https://clinicaltrials.gov/study/{nct_id}" if nct_id else None,
        "retrieved_at": retrieved_at,
    }


def study_references(study: dict[str, Any], retrieved_at: datetime) -> list[dict[str, Any]]:
    """Rows of the `trial_references` table: the registry's own publication links for one trial.

    `reference_type` is the registry's label: BACKGROUND (cited by the sponsor), RESULT (reports
    results of this trial) or DERIVED (found by PubMed linkage). These are the verified paper-to-trial
    links the mapping table starts from; which of them are open access is resolved later, against PMC.
    """
    nct_id = study.get("protocolSection", {}).get("identificationModule", {}).get("nctId")
    references = study.get("protocolSection", {}).get("referencesModule", {}).get("references", [])
    return [
        {
            "nct_id": nct_id,
            "pmid": ref.get("pmid"),
            "reference_type": ref.get("type"),
            "citation": ref.get("citation"),
            "source": SOURCE,
            "retrieved_at": retrieved_at,
        }
        for ref in references
        if ref.get("pmid")
    ]


def alias_rows() -> list[dict[str, Any]]:
    """Rows of the `drug_aliases` table."""
    return [{"therapy": a.therapy, "alias": a.alias, "alias_type": a.alias_type} for a in DRUG_ALIASES]


def build_snapshot(
    studies: Iterable[dict[str, Any]],
    seeds: Sequence[SeedTrial] = SEED_TRIALS,
    retrieved_at: datetime | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    """Flatten fetched studies into trial rows and reference rows; report seed IDs the API did not return.

    Rows come back in seed order, so the table reads the way the snapshot is documented.
    """
    retrieved_at = retrieved_at or datetime.now(UTC)
    fetched = {s.get("protocolSection", {}).get("identificationModule", {}).get("nctId"): s for s in studies}
    trial_rows: list[dict[str, Any]] = []
    reference_rows: list[dict[str, Any]] = []
    missing: list[str] = []
    for seed in seeds:
        study = fetched.get(seed.nct_id)
        if study is None:
            missing.append(seed.nct_id)
            continue
        trial_rows.append(flatten_study(study, seed, retrieved_at))
        reference_rows.extend(study_references(study, retrieved_at))
    return trial_rows, reference_rows, missing
