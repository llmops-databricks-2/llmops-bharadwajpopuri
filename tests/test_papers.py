"""Tests of the PMC paper acquisition (no network, no workspace).

The service responses below are hand-trimmed samples of what the three services returned on
2026-10-22, reduced to the fields the parsers read; recorded responses are not kept in the repository.
"""

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest

from evidence_curator import papers
from evidence_curator.papers import (
    PmcArticle,
    article_versions,
    download_pdf,
    latest_version,
    paper_rows,
    parse_article,
    pmcids_for,
    pubmed_summaries,
    s3_https,
)

# PMC ID converter: two PMIDs held by PMC, one that is not.
IDCONV_RESPONSE = {
    "status": "ok",
    "records": [
        {"doi": "10.1038/ijo.2011.158", "pmcid": "PMC3374073", "pmid": 21844879, "requested-id": "21844879"},
        {"doi": "10.1038/ijo.2013.149", "pmcid": "PMC4010971", "pmid": 23942319, "requested-id": "23942319"},
        {"pmid": 19853906, "requested-id": "19853906", "status": "error", "errmsg": "Identifier not found in PMC"},
    ],
}

# ListObjectsV2 on the PMC Article Datasets bucket: two article versions as common prefixes.
BUCKET_LISTING = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/"><Name>pmc-oa-opendata</Name>'
    "<Prefix>PMC11370360.</Prefix><KeyCount>2</KeyCount><MaxKeys>1000</MaxKeys><Delimiter>/</Delimiter>"
    "<IsTruncated>false</IsTruncated><CommonPrefixes><Prefix>PMC11370360.1/</Prefix></CommonPrefixes>"
    "<CommonPrefixes><Prefix>PMC11370360.2/</Prefix></CommonPrefixes></ListBucketResult>"
)

# The dataset's per-version metadata object (`metadata/PMC13634289.1.json`).
ARTICLE_METADATA = {
    "pmcid": "PMC13634289",
    "version": 1,
    "pmid": 42831032,
    "doi": "10.1016/j.obpill.2026.100333",
    "title": "Evaluation of clinical relevance of weight nadirs and weight regain during 3 years of treatment with tirzepatide",
    "citation": "Obes Pillars. 2026 Sep 18;20:100333. doi: 10.1016/j.obpill.2026.100333",
    "is_pmc_openaccess": True,
    "is_manuscript": False,
    "is_retracted": False,
    "license_code": "CC BY",
    "pdf_url": "s3://pmc-oa-opendata/PMC13634289.1/PMC13634289.1.pdf?md5=ceffafacbfcfe018982e9124d4a585fa",
}

# PubMed esummary for two PMIDs: a print-issue paper and an online-first one.
ESUMMARY_RESPONSE = {
    "result": {
        "uids": ["42831032", "33567185"],
        "42831032": {
            "uid": "42831032",
            "pubdate": "2026 Dec",
            "epubdate": "2026 Sep 18",
            "source": "Obes Pillars",
            "fulljournalname": "Obesity pillars",
            "title": "Evaluation of clinical relevance of weight nadirs and weight regain during 3 years of treatment with tirzepatide.",
            "authors": [{"name": "Aronne LJ"}, {"name": "Vincent RP"}, {"name": "Dunn JP"}],
            "articleids": [
                {"idtype": "pubmed", "value": "42831032"},
                {"idtype": "doi", "value": "10.1016/j.obpill.2026.100333"},
            ],
        },
        "33567185": {
            "uid": "33567185",
            "pubdate": "2021 Mar 18",
            "epubdate": "2021 Feb 10",
            "source": "N Engl J Med",
            "fulljournalname": "The New England journal of medicine",
            "title": "Once-Weekly Semaglutide in Adults with Overweight or Obesity.",
            "authors": [
                {"name": "Wilding JPH"},
                {"name": "Batterham RL"},
                {"name": "Calanna S"},
                {"name": "Kushner RF"},
                {"name": "STEP 1 Study Group"},
            ],
            "articleids": [
                {"idtype": "pubmed", "value": "33567185"},
                {"idtype": "doi", "value": "10.1056/NEJMoa2032183"},
            ],
        },
    }
}


def _json(payload: dict) -> bytes:
    return json.dumps(payload).encode()


def _serve(responses: dict[str, bytes]) -> tuple[Callable[..., bytes], list[str]]:
    """Build a stand-in for `_get` that answers by URL substring and records what was requested."""
    calls: list[str] = []

    def fake_get(url: str, timeout: float = 60.0, data: bytes | None = None) -> bytes:
        calls.append(url)
        for needle, body in responses.items():
            if needle in url:
                return body
        raise AssertionError(f"unexpected request: {url}")

    return fake_get, calls


def test_pmcids_for_keeps_only_articles_held_by_pmc(monkeypatch: pytest.MonkeyPatch) -> None:
    """PMIDs without a PMC record come back as error records and are left out of the mapping."""
    fake_get, calls = _serve({papers.IDCONV_URL: _json(IDCONV_RESPONSE)})
    monkeypatch.setattr(papers, "_get", fake_get)
    monkeypatch.setattr(papers.time, "sleep", lambda _: None)

    found = pmcids_for(["21844879", "23942319", "19853906"])

    assert found == {"21844879": "PMC3374073", "23942319": "PMC4010971"}
    assert len(calls) == 1 and "ids=21844879%2C23942319%2C19853906" in calls[0]


def test_article_versions_lists_prefixes_and_latest_sorts_numerically(monkeypatch: pytest.MonkeyPatch) -> None:
    """Versions are read from the bucket listing; the latest is chosen numerically, not lexically."""
    fake_get, calls = _serve({"list-type=2": BUCKET_LISTING.encode()})
    monkeypatch.setattr(papers, "_get", fake_get)

    versions = article_versions("PMC11370360")

    assert versions == ["PMC11370360.1", "PMC11370360.2"]
    assert "prefix=PMC11370360.&delimiter=%2F" in calls[0]
    assert latest_version(versions) == "PMC11370360.2"
    assert latest_version(["PMC1.9", "PMC1.10", "PMC1.2"]) == "PMC1.10"
    assert latest_version([]) is None
    with pytest.raises(ValueError, match="Not a PMCID"):
        article_versions("12345")


def test_parse_article_reads_the_dataset_metadata() -> None:
    """The per-version JSON maps onto the article dataclass with HTTPS PDF URL and checksum."""
    article = parse_article(ARTICLE_METADATA)

    assert (article.pmcid, article.version, article.pmid) == ("PMC13634289", 1, "42831032")
    assert article.license_code == "CC BY" and article.is_open_access and not article.is_retracted
    assert article.usable
    assert article.pdf_https_url == "https://pmc-oa-opendata.s3.amazonaws.com/PMC13634289.1/PMC13634289.1.pdf"
    assert article.pdf_md5 == "ceffafacbfcfe018982e9124d4a585fa"


@pytest.mark.parametrize(
    ("changes", "usable"),
    [
        ({}, True),
        ({"license_code": None}, False),  # open access without a machine-readable licence
        ({"license_code": "CC BY-NC-ND"}, True),  # non-commercial licences are accepted
        ({"is_pmc_openaccess": False, "is_manuscript": True, "license_code": "TDM", "pdf_url": None}, False),
        ({"is_retracted": True}, False),
        ({"pdf_url": None}, False),
    ],
)
def test_usable_applies_the_corpus_policy(changes: dict, usable: bool) -> None:
    """Only open-access, CC-licensed, unretracted versions with a PDF enter the corpus."""
    assert parse_article(ARTICLE_METADATA | changes).usable is usable


def test_s3_https_rewrites_bucket_urls_only() -> None:
    """An s3:// dataset URL becomes the bucket's HTTPS URL; other URLs pass through."""
    assert (
        s3_https("s3://pmc-oa-opendata/PMC1.1/PMC1.1.pdf?md5=abc")
        == "https://pmc-oa-opendata.s3.amazonaws.com/PMC1.1/PMC1.1.pdf"
    )
    assert s3_https("https://example.org/x.pdf") == "https://example.org/x.pdf"


def test_pubmed_summaries_extracts_journal_dates_authors_and_doi(monkeypatch: pytest.MonkeyPatch) -> None:
    """Esummary records give journal, dates, author string and DOI per PMID."""
    fake_get, calls = _serve({papers.ESUMMARY_URL: _json(ESUMMARY_RESPONSE)})
    monkeypatch.setattr(papers, "_get", fake_get)
    monkeypatch.setattr(papers.time, "sleep", lambda _: None)

    summaries = pubmed_summaries(["42831032", "33567185"])

    assert set(summaries) == {"42831032", "33567185"}
    step1 = summaries["33567185"]
    assert step1["journal"] == "N Engl J Med" and step1["pub_year"] == 2021 and step1["pub_date"] == "2021 Mar 18"
    assert step1["doi"] == "10.1056/NEJMoa2032183"
    assert step1["authors"].startswith("Wilding JPH, Batterham RL") and "STEP 1 Study Group" in step1["authors"]
    assert step1["title"] == "Once-Weekly Semaglutide in Adults with Overweight or Obesity"
    assert summaries["42831032"]["epub_date"] == "2026 Sep 18"


def _article(pmcid: str, pmid: str, year: int, license_code: str | None = "CC BY", **changes: object) -> PmcArticle:
    fields = {
        "pmcid": pmcid,
        "version": 1,
        "pmid": pmid,
        "doi": f"10.1/{pmcid}",
        "title": f"Paper {pmcid}",
        "citation": f"J Test. {year} Jan 1;1:1.",
        "is_open_access": True,
        "is_manuscript": False,
        "is_retracted": False,
        "license_code": license_code,
        "pdf_url": f"s3://pmc-oa-opendata/{pmcid}.1/{pmcid}.1.pdf?md5=00",
    } | changes
    return PmcArticle(**fields)


def test_paper_rows_ranks_by_link_type_and_balances_therapies() -> None:
    """RESULT links outrank DERIVED, the cap is filled round-robin across therapies, unusable papers drop out."""
    therapy_of = {"NCT1": "semaglutide", "NCT2": "tirzepatide", "NCT3": "liraglutide"}
    references = [
        {"nct_id": "NCT1", "pmid": "1", "reference_type": "DERIVED"},
        {"nct_id": "NCT1", "pmid": "2", "reference_type": "RESULT"},  # RESULT outranks DERIVED
        {"nct_id": "NCT1", "pmid": "3", "reference_type": "DERIVED"},  # newer than 1
        {"nct_id": "NCT2", "pmid": "4", "reference_type": "DERIVED"},
        {"nct_id": "NCT2", "pmid": "5", "reference_type": "DERIVED"},  # paywalled: no PMCID
        {"nct_id": "NCT3", "pmid": "6", "reference_type": "RESULT"},  # no licence: excluded
        {"nct_id": "NCT3", "pmid": "7", "reference_type": "BACKGROUND"},
        {"nct_id": "NCT1", "pmid": "7", "reference_type": "DERIVED"},  # linked to two therapies
    ]
    pmcid_of = {p: f"PMC{p}" for p in ["1", "2", "3", "4", "6", "7"]}
    articles = {
        "PMC1": _article("PMC1", "1", 2020),
        "PMC2": _article("PMC2", "2", 2018),
        "PMC3": _article("PMC3", "3", 2024),
        "PMC4": _article("PMC4", "4", 2023, license_code="CC BY-NC-ND"),
        "PMC6": _article("PMC6", "6", 2022, license_code=None),
        "PMC7": _article("PMC7", "7", 2021),
    }
    summaries = {"3": {"pub_year": 2024, "journal": "J Three", "doi": "10.3/x"}}
    when = datetime(2026, 10, 22, tzinfo=UTC)

    rows = paper_rows(references, therapy_of, pmcid_of, articles, summaries, max_papers=4, retrieved_at=when)

    by_pmid = {row["pmid"]: row for row in rows}
    # Round-robin over the therapies that have candidates: liraglutide (7), semaglutide (2), tirzepatide (4),
    # then the second semaglutide pick (3, the newest DERIVED). Paper 1 is left out by the cap.
    assert set(by_pmid) == {"7", "2", "4", "3"}
    assert by_pmid["7"]["therapies"] == "liraglutide,semaglutide" and by_pmid["7"]["nct_ids"] == "NCT1,NCT3"
    assert by_pmid["7"]["reference_types"] == "BACKGROUND,DERIVED" and by_pmid["7"]["n_trials"] == 2
    assert by_pmid["4"]["license"] == "CC BY-NC-ND"
    assert by_pmid["3"]["journal"] == "J Three" and by_pmid["3"]["doi"] == "10.3/x" and by_pmid["3"]["pub_year"] == 2024
    assert by_pmid["2"]["pub_year"] == 2018  # year parsed from the citation when there is no summary
    assert all(row["retrieved_at"] == when and row["source"] == papers.SOURCE for row in rows)
    assert all(row["pdf_url"].startswith("https://pmc-oa-opendata.s3.amazonaws.com/") for row in rows)
    assert [row["pmid"] for row in rows] == ["7", "2", "3", "4"]  # sorted by therapies, then year


def test_download_pdf_verifies_checksum_and_skips_existing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A PDF is fetched once, verified against the dataset's MD5, and reused when already present."""
    content = b"%PDF-1.4 fake"
    digest = hashlib.md5(content).hexdigest()
    article = _article("PMC9", "9", 2024, pdf_url=f"s3://pmc-oa-opendata/PMC9.1/PMC9.1.pdf?md5={digest}")
    fake_get, calls = _serve({"PMC9.1.pdf": content})
    monkeypatch.setattr(papers, "_get", fake_get)
    destination = tmp_path / "pmc_papers" / "PMC9.pdf"

    assert download_pdf(article, destination) == len(content)
    assert destination.read_bytes() == content and len(calls) == 1
    assert download_pdf(article, destination) == len(content) and len(calls) == 1  # cached, not re-fetched

    corrupt = _article("PMC9", "9", 2024, pdf_url="s3://pmc-oa-opendata/PMC9.1/PMC9.1.pdf?md5=deadbeef")
    with pytest.raises(ValueError, match="MD5 mismatch"):
        download_pdf(corrupt, tmp_path / "other.pdf")
    fake_html, _ = _serve({"PMC9.1.pdf": b"<html>Just a moment...</html>"})
    monkeypatch.setattr(papers, "_get", fake_html)
    with pytest.raises(ValueError, match="did not return a PDF"):
        download_pdf(article, tmp_path / "another.pdf")


def test_paper_rows_prefers_breadth_across_trials_over_recency() -> None:
    """Within a therapy, a paper that adds a trial not yet represented is picked before a newer one that does not."""
    therapy_of = {"NCT1": "tirzepatide", "NCT2": "tirzepatide"}
    references = [
        {"nct_id": "NCT1", "pmid": "1", "reference_type": "RESULT"},
        {"nct_id": "NCT1", "pmid": "2", "reference_type": "DERIVED"},  # newest, but NCT1 is already covered
        {"nct_id": "NCT2", "pmid": "3", "reference_type": "DERIVED"},  # older, adds NCT2
    ]
    pmcid_of = {"1": "PMC1", "2": "PMC2", "3": "PMC3"}
    articles = {
        "PMC1": _article("PMC1", "1", 2022),
        "PMC2": _article("PMC2", "2", 2026),
        "PMC3": _article("PMC3", "3", 2021),
    }

    rows = paper_rows(references, therapy_of, pmcid_of, articles, max_papers=2)

    assert {row["pmid"] for row in rows} == {"1", "3"}
    assert {row["pmid"] for row in paper_rows(references, therapy_of, pmcid_of, articles, max_papers=3)} == {
        "1",
        "2",
        "3",
    }
