"""PubMed Central open-access papers: from the registry's PMIDs to PDFs in a Unity Catalog volume.

The literature half of the Evidence Curator's data, the counterpart of the arXiv curator's
"search arXiv → download PDFs → `arxiv_papers` table" step. The paper set is not a free-text search:
ClinicalTrials.gov already names the publications of each pinned trial (`trial_references`, one row
per trial and PMID), so the corpus is derived from those links and every paper arrives tied to at
least one trial by the registry itself. That is the paper-to-trial mapping the project needs.

Two public, keyless NCBI services do the resolution:

- the PMC ID converter maps PMIDs to PMCIDs (a paper has a PMCID when PubMed Central holds its text);
- the PMC Article Datasets on AWS (the "PMC Cloud Service", a world-readable S3 bucket served over
  plain HTTPS) hold, per article version, a JSON metadata object saying whether the version is in the
  Open Access Subset, under which licence, whether it is retracted, and where its PDF is. The PMC OA
  web service that used to answer these questions was discontinued in 2026; the bucket is the route
  NCBI documents for automated retrieval.

PubMed's `esummary` adds journal, dates and authors for the `papers` table.

Everything here is pure Python so it can be unit-tested on recorded responses; Spark and the volume
enter only in the notebook that calls it.
"""

import hashlib
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import backoff

IDCONV_URL = "https://pmc.ncbi.nlm.nih.gov/tools/idconv/api/v1/articles/"
ESUMMARY_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
PMC_BUCKET = "pmc-oa-opendata"
PMC_BUCKET_URL = f"https://{PMC_BUCKET}.s3.amazonaws.com"
TOOL = "evidence-curator"
USER_AGENT = "evidence-curator/0.1 (LLMOps course project; contact via GitHub llmops-bharadwajpopuri)"
SOURCE = "PubMed Central Open Access Subset (PMC Article Datasets on AWS)"

# NCBI asks for at most three requests a second from one address without an API key.
NCBI_PAUSE_S = 0.35

# Delta table layout, as Spark DDL, flat like the trials tables. One row per paper in the corpus.
PAPERS_SCHEMA = (
    "pmcid STRING, pmc_version INT, pmid STRING, doi STRING, title STRING, journal STRING, pub_year INT, "
    "pub_date STRING, epub_date STRING, authors STRING, license STRING, is_manuscript BOOLEAN, "
    "nct_ids STRING, therapies STRING, reference_types STRING, n_trials INT, citation STRING, "
    "pdf_url STRING, volume_path STRING, source STRING, retrieved_at TIMESTAMP"
)

# The registry's own labels for a link, from most to least directly about the trial.
REFERENCE_TYPE_RANK = {"RESULT": 0, "DERIVED": 1, "BACKGROUND": 2}

_PMCID = re.compile(r"^PMC\d+$")
_PREFIX = re.compile(r"<CommonPrefixes><Prefix>([^<]+)</Prefix>")


@dataclass(frozen=True)
class PmcArticle:
    """One article version as the PMC Article Datasets describe it (the per-version JSON object)."""

    pmcid: str
    version: int
    pmid: str | None
    doi: str | None
    title: str | None
    citation: str | None
    is_open_access: bool
    is_manuscript: bool
    is_retracted: bool
    license_code: str | None
    pdf_url: str | None

    @property
    def usable(self) -> bool:
        """In the Open Access Subset, under a Creative Commons licence, not retracted, with a PDF.

        Author manuscripts whose licence code is `TDM` are text-minable but carry no PDF and no reuse
        licence, so they are excluded; a manuscript with a CC licence is kept like any other version.
        """
        return (
            self.is_open_access
            and not self.is_retracted
            and bool(self.pdf_url)
            and (self.license_code or "").upper().startswith("CC")
        )

    @property
    def pdf_https_url(self) -> str | None:
        """The PDF's HTTPS form (the JSON gives `s3://` URLs; the bucket serves the same keys over HTTPS)."""
        return s3_https(self.pdf_url) if self.pdf_url else None

    @property
    def pdf_md5(self) -> str | None:
        """The MD5 digest the dataset publishes for the PDF, carried as the URL's `md5` parameter."""
        if not self.pdf_url:
            return None
        return urllib.parse.parse_qs(urllib.parse.urlsplit(self.pdf_url).query).get("md5", [None])[0]


def s3_https(url: str) -> str:
    """Rewrite an `s3://bucket/key?md5=...` URL to the bucket's HTTPS endpoint, without the checksum parameter."""
    parts = urllib.parse.urlsplit(url)
    if parts.scheme != "s3":
        return url
    return f"https://{parts.netloc}.s3.amazonaws.com/{parts.path.lstrip('/')}"


def _give_up(error: Exception) -> bool:
    # Retry only what time can fix: network errors, timeouts, 429 and 5xx. A 404 is an answer.
    if isinstance(error, urllib.error.HTTPError):
        return error.code < 500 and error.code != 429
    return False


@backoff.on_exception(backoff.expo, (urllib.error.URLError, TimeoutError), max_tries=4, max_time=120, giveup=_give_up)
def _get(url: str, timeout: float = 60.0, data: bytes | None = None) -> bytes:
    request = urllib.request.Request(url, data=data, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def _batched(items: Sequence[str], size: int) -> Iterable[Sequence[str]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]


def pmcids_for(pmids: Sequence[str], timeout: float = 60.0) -> dict[str, str]:
    """Map PMIDs to PMCIDs with the PMC ID converter (200 IDs a request).

    PMIDs that PubMed Central does not hold come back as `status: error` records and are simply
    absent from the result: most pivotal trial papers are paywalled and never reach PMC.
    """
    found: dict[str, str] = {}
    for batch in _batched(list(pmids), 200):
        query = urllib.parse.urlencode({"ids": ",".join(batch), "format": "json", "tool": TOOL})
        payload = json.loads(_get(f"{IDCONV_URL}?{query}", timeout))
        for record in payload.get("records", []):
            pmcid = record.get("pmcid")
            if pmcid and record.get("status") != "error":
                found[str(record.get("pmid") or record.get("requested-id"))] = pmcid
        time.sleep(NCBI_PAUSE_S)
    return found


def article_versions(pmcid: str, timeout: float = 60.0) -> list[str]:
    """List the article-version prefixes the bucket holds for a PMCID, such as `["PMC11370360.1", "PMC11370360.2"]`.

    A prefix is an S3 key prefix, not an object: the bucket is listed with `ListObjectsV2` and the
    delimiter, as the dataset's README shows. An article may have no version 1 at all.
    """
    if not _PMCID.match(pmcid):
        raise ValueError(f"Not a PMCID: {pmcid}")
    query = urllib.parse.urlencode({"list-type": "2", "prefix": f"{pmcid}.", "delimiter": "/"})
    listing = _get(f"{PMC_BUCKET_URL}/?{query}", timeout).decode("utf-8")
    return [prefix.rstrip("/") for prefix in _PREFIX.findall(listing)]


def latest_version(prefixes: Iterable[str]) -> str | None:
    """Pick the highest-numbered article version among prefixes like `PMC13901.2` (numeric, so `.10` beats `.9`)."""
    prefixes = list(prefixes)
    if not prefixes:
        return None
    return max(prefixes, key=lambda prefix: int(prefix.rsplit(".", 1)[-1]))


def parse_article(metadata: Mapping[str, Any]) -> PmcArticle:
    """Build a `PmcArticle` from the dataset's per-version JSON object."""
    return PmcArticle(
        pmcid=str(metadata["pmcid"]),
        version=int(metadata.get("version") or 0),
        pmid=str(metadata["pmid"]) if metadata.get("pmid") else None,
        doi=metadata.get("doi"),
        title=metadata.get("title"),
        citation=metadata.get("citation"),
        is_open_access=bool(metadata.get("is_pmc_openaccess")),
        is_manuscript=bool(metadata.get("is_manuscript")),
        is_retracted=bool(metadata.get("is_retracted")),
        license_code=metadata.get("license_code"),
        pdf_url=metadata.get("pdf_url"),
    )


def pmc_article(pmcid: str, timeout: float = 60.0) -> PmcArticle | None:
    """Fetch the latest version of an article from the PMC Article Datasets, or None when the bucket has none."""
    version = latest_version(article_versions(pmcid, timeout))
    if version is None:
        return None
    metadata = json.loads(_get(f"{PMC_BUCKET_URL}/metadata/{version}.json", timeout))
    return parse_article(metadata)


def pubmed_summaries(pmids: Sequence[str], timeout: float = 60.0) -> dict[str, dict[str, Any]]:
    """Journal, dates, authors and DOI for PMIDs from PubMed `esummary` (100 IDs a request, by POST).

    `pub_date` is PubMed's publication date (print issue when there is one), `epub_date` the online
    date; `pub_year` is taken from `pub_date` so that a year filter means the year of record.
    """
    summaries: dict[str, dict[str, Any]] = {}
    for batch in _batched(list(pmids), 100):
        body = urllib.parse.urlencode({"db": "pubmed", "id": ",".join(batch), "retmode": "json", "tool": TOOL}).encode()
        result = json.loads(_get(ESUMMARY_URL, timeout, data=body)).get("result", {})
        for uid in result.get("uids", []):
            record = result.get(uid, {})
            if "error" in record:
                continue
            pub_date = record.get("pubdate") or ""
            doi = next((a.get("value") for a in record.get("articleids", []) if a.get("idtype") == "doi"), None)
            summaries[uid] = {
                "title": (record.get("title") or "").rstrip("."),
                "journal": record.get("source"),
                "journal_full": record.get("fulljournalname"),
                "pub_date": pub_date,
                "epub_date": record.get("epubdate") or None,
                "pub_year": int(pub_date[:4]) if pub_date[:4].isdigit() else None,
                "authors": ", ".join(a.get("name", "") for a in record.get("authors", []) if a.get("name")),
                "doi": doi,
            }
        time.sleep(NCBI_PAUSE_S)
    return summaries


def resolve_articles(pmcids: Iterable[str], timeout: float = 60.0) -> dict[str, PmcArticle]:
    """Look every PMCID up in the datasets, politely paced; PMCIDs the bucket does not hold are absent."""
    articles: dict[str, PmcArticle] = {}
    for pmcid in pmcids:
        article = pmc_article(pmcid, timeout)
        if article is not None:
            articles[pmcid] = article
        time.sleep(NCBI_PAUSE_S)
    return articles


def _year_of(citation: str | None) -> int | None:
    match = re.search(r"\b(19|20)\d{2}\b", citation or "")
    return int(match.group(0)) if match else None


def paper_rows(
    references: Iterable[Mapping[str, Any]],
    therapy_of: Mapping[str, str],
    pmcid_of: Mapping[str, str],
    articles: Mapping[str, PmcArticle],
    summaries: Mapping[str, Mapping[str, Any]] | None = None,
    max_papers: int = 24,
    retrieved_at: datetime | None = None,
) -> list[dict[str, Any]]:
    """Select the corpus and build the rows of the `papers` table.

    Args:
        references: rows of `trial_references` (`nct_id`, `pmid`, `reference_type`).
        therapy_of: canonical therapy of each pinned trial, from the seed list.
        pmcid_of: PMID → PMCID, from `pmcids_for`.
        articles: PMCID → latest article version, from `resolve_articles`.
        summaries: PMID → PubMed summary, from `pubmed_summaries`; the dataset's own title and
            citation fill in when a summary is missing.
        max_papers: size cap of the corpus (parsing and embedding cost scale with it).
        retrieved_at: provenance timestamp written on every row.

    Selection policy, deterministic so the corpus is reproducible from the same inputs: keep usable
    article versions only (open access, CC licence, PDF, not retracted); fill the cap round-robin
    across therapies so no therapy is crowded out by another's larger literature; within a therapy
    take the paper with the most direct registry link first (RESULT before DERIVED before BACKGROUND),
    then the one that adds the most trials not yet represented (breadth across the programme), then
    the most recent. A paper linked to several trials keeps all of them in `nct_ids`.

    """
    retrieved_at = retrieved_at or datetime.now(UTC)
    summaries = summaries or {}
    links: dict[str, dict[str, set[str]]] = defaultdict(lambda: {"nct_ids": set(), "types": set(), "therapies": set()})
    for ref in references:
        pmid, nct_id = str(ref["pmid"]), ref["nct_id"]
        links[pmid]["nct_ids"].add(nct_id)
        links[pmid]["types"].add(ref.get("reference_type") or "")
        if nct_id in therapy_of:
            links[pmid]["therapies"].add(therapy_of[nct_id])

    candidates: dict[str, list[tuple[int, int, str, str]]] = defaultdict(list)
    for pmid, link in links.items():
        pmcid = pmcid_of.get(pmid)
        article = articles.get(pmcid) if pmcid else None
        if article is None or not article.usable or not link["therapies"]:
            continue
        summary = summaries.get(pmid, {})
        year = summary.get("pub_year") or _year_of(article.citation) or 0
        type_rank = min(REFERENCE_TYPE_RANK.get(t, 9) for t in link["types"])
        candidates[sorted(link["therapies"])[0]].append((type_rank, -year, pmcid, pmid))

    selected: list[str] = []
    covered: set[str] = set()  # trials already represented by a selected paper

    def pick(therapy: str) -> str | None:
        # Directness of the link first; then the paper that covers the most trials not yet represented
        # (so the corpus spans the programmes rather than piling onto one trial); then recency.
        best = min(
            candidates[therapy],
            key=lambda c: (c[0], -len(links[c[3]]["nct_ids"] - covered), c[1], c[2]),
            default=None,
        )
        if best is None:
            return None
        candidates[therapy].remove(best)
        covered.update(links[best[3]]["nct_ids"])
        return best[3]

    while len(selected) < max_papers and any(candidates.values()):
        for therapy in sorted(candidates):
            if len(selected) < max_papers:
                pmid = pick(therapy)
                if pmid is not None:
                    selected.append(pmid)

    rows: list[dict[str, Any]] = []
    for pmid in selected:
        pmcid = pmcid_of[pmid]
        article = articles[pmcid]
        summary = summaries.get(pmid, {})
        link = links[pmid]
        rows.append(
            {
                "pmcid": pmcid,
                "pmc_version": article.version,
                "pmid": pmid,
                "doi": summary.get("doi") or article.doi,
                "title": summary.get("title") or article.title,
                "journal": summary.get("journal"),
                "pub_year": summary.get("pub_year") or _year_of(article.citation),
                "pub_date": summary.get("pub_date"),
                "epub_date": summary.get("epub_date"),
                "authors": summary.get("authors"),
                "license": article.license_code,
                "is_manuscript": article.is_manuscript,
                "nct_ids": ",".join(sorted(link["nct_ids"])),
                "therapies": ",".join(sorted(link["therapies"])),
                "reference_types": ",".join(sorted(t for t in link["types"] if t)),
                "n_trials": len(link["nct_ids"]),
                "citation": article.citation,
                "pdf_url": article.pdf_https_url,
                "volume_path": None,  # set by the notebook once the PDF is in the volume
                "source": SOURCE,
                "retrieved_at": retrieved_at,
            }
        )
    rows.sort(key=lambda r: (r["therapies"], r["pub_year"] or 0, r["pmcid"]))
    return rows


def download_pdf(article: PmcArticle, destination: str | Path, timeout: float = 180.0) -> int:
    """Fetch the article's PDF into `destination`, verifying the dataset's MD5; returns the byte count.

    An existing file with the right checksum is left alone, so re-running the job does not re-download
    the corpus. A checksum mismatch raises rather than leaving a corrupt PDF for the parser.
    """
    if not article.pdf_https_url:
        raise ValueError(f"{article.pmcid}.{article.version} has no PDF in the datasets")
    path = Path(destination)
    expected = article.pdf_md5
    if path.exists() and expected and hashlib.md5(path.read_bytes()).hexdigest() == expected:
        return path.stat().st_size
    content = _get(article.pdf_https_url, timeout)
    if not content.startswith(b"%PDF"):
        raise ValueError(f"{article.pdf_https_url} did not return a PDF")
    if expected and hashlib.md5(content).hexdigest() != expected:
        raise ValueError(f"MD5 mismatch for {article.pdf_https_url}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return len(content)
