# Use case: Pharma R&D Evidence Curator — GLP-1–based therapies for obesity

## The problem and who has it

A clinical development scientist or competitive-intelligence analyst preparing a landscape review of
an indication works across two disconnected sources: the literature (PubMed/PMC) and the trial
registry (ClinicalTrials.gov). The same drug appears under its INN, its brand and its sponsor code
(semaglutide / Wegovy / NN9535), so queries phrased one way miss records stored another way, and the
comparison tables that end up in a review are assembled by hand with the sources pasted in afterwards.

The Evidence Curator helps that person find the relevant trials and publications, compare trial designs
side by side, and produce a short evidence brief in which every claim links to its source. It is the
course's arXiv curator transposed to pharma: papers are the documents, the registry is the structured
data, and an agent with three tools composes cited briefs from both.

## Scope of the smallest useful version

One indication, obesity, and three therapies on a fixed snapshot of records:

| Therapy | Programme | Sponsor |
|---|---|---|
| semaglutide 2.4 mg once weekly | STEP (plus SELECT and a phase 2 dose-finding trial) | Novo Nordisk |
| tirzepatide (dual GIP/GLP-1 agonist) | SURMOUNT | Eli Lilly |
| liraglutide 3.0 mg once daily | SCALE (plus a phase 2 dose-ranging trial) | Novo Nordisk |

Comparisons describe differences in design and reported outcomes; they never rank therapies across
separate trials. Every brief names its sources and its gaps. Out of scope for the course: automated
refreshes, additional indications, broader literature coverage, cross-trial efficacy ranking.

## Data

**Structured data (this week).** 30 ClinicalTrials.gov records, pinned by NCT ID in
`src/evidence_curator/seed.py` and fetched through the ClinicalTrials.gov API v2 into
`llmops_dev.bharadwajpopuri.trials`: design, status, sponsor, phase, enrollment, planned primary
outcomes, dates, posted-results flag, and a retrieval timestamp on every row. The registry's own
publication links (PMIDs) land in `trial_references`, the seed of the paper-to-trial mapping; a
hand-built alias table (`drug_aliases`) maps INN, brand, sponsor code and dose labels to one canonical
therapy name.

**Documents (next weeks).** 15–20 full-text papers on the three therapies from the PubMed Central Open
Access Subset, limited to CC BY / CC0 licences: loaded into a Unity Catalog volume, parsed with
`ai_parse_document`, chunked, embedded through `course_ops.gateway.embed`, and indexed in Lakebase
pgvector (no Vector Search endpoint is provisioned in this workspace). Pivotal results are often
paywalled, so the open-access set leans toward secondary and pooled analyses, meta-analyses and
reviews; where a pivotal result exists only behind a paywall, the brief cites the registry's posted
results and says so.

**Provenance rules.** Registry metadata (planned endpoints, enrollment, status) is kept distinct from
published findings, and every trial row carries its retrieval date.

## How the data serves the agent

| Example prompt | Tool(s) |
|---|---|
| "Which phase 2 and phase 3 trials in our dataset test GLP-1–based therapies for obesity? Group them by sponsor and recruitment status." | `query_trials` over `trials` |
| "Compare the populations, primary endpoints and treatment durations of STEP 1, SURMOUNT-1 and SCALE Obesity and Prediabetes." | `query_trials` for design fields + `search_papers` for reported results |
| "Find the publications linked to NCT03548935 and summarize their reported findings with citations." | `get_linked_sources` via `trial_references` + `search_papers` scoped to them |
| "Prepare a short landscape brief for our three therapies, highlighting differences in trial design and where evidence is missing." | all three |

## Evidence of quality (demo day)

A golden set of about 20 questions with expected trial IDs and passages; retrieval hit rate and
citation faithfulness measured separately from answer quality, so retrieval failures can be told apart
from generation failures; MLflow traces on every call; evaluation and traces logged per environment
(dev / acc / prd) through the course bundle.
