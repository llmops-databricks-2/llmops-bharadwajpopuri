# Chunking report

Generated 2026-10-31T18:43:42+00:00 from `llmops_dev.bharadwajpopuri`.

## Parsed documents: element types per paper

| PMCID | pages | caption | figure | footnote | page_footer | page_header | page_number | section_header | table | text | title |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| PMC10092593 | 11 | 2 | 2 | 4 | 2 | 23 | 11 | 30 | 4 | 48 | 1 |
| PMC10288970 | 16 | 0 | 40 | 0 | 40 | 23 | 0 | 36 | 4 | 77 | 1 |
| PMC12006245 | 13 | 3 | 5 | 2 | 12 | 12 | 12 | 17 | 2 | 38 | 1 |
| PMC12447996 | 10 | 4 | 8 | 6 | 11 | 12 | 8 | 28 | 3 | 47 | 2 |
| PMC12448458 | 8 | 3 | 8 | 4 | 1 | 8 | 7 | 23 | 2 | 34 | 1 |
| PMC12724063 | 13 | 4 | 19 | 7 | 13 | 6 | 13 | 37 | 2 | 57 | 1 |
| PMC12803658 | 10 | 3 | 7 | 5 | 2 | 21 | 10 | 26 | 3 | 38 | 1 |
| PMC12865613 | 6 | 0 | 2 | 6 | 1 | 11 | 5 | 22 | 4 | 29 | 2 |
| PMC12920140 | 17 | 1 | 3 | 13 | 16 | 20 | 16 | 26 | 3 | 37 | 1 |
| PMC12933222 | 14 | 1 | 3 | 10 | 16 | 6 | 14 | 31 | 9 | 49 | 1 |
| PMC12933229 | 14 | 3 | 8 | 5 | 14 | 5 | 14 | 27 | 6 | 40 | 1 |
| PMC13190271 | 16 | 3 | 11 | 8 | 13 | 34 | 11 | 44 | 17 | 65 | 1 |
| PMC13287229 | 14 | 2 | 5 | 14 | 14 | 15 | 13 | 32 | 6 | 43 | 1 |
| PMC13574348 | 16 | 6 | 9 | 4 | 32 | 43 | 16 | 28 | 4 | 52 | 1 |
| PMC4973216 | 10 | 3 | 6 | 5 | 19 | 14 | 9 | 22 | 4 | 40 | 1 |
| PMC5069304 | 10 | 4 | 6 | 6 | 10 | 12 | 9 | 32 | 2 | 43 | 1 |
| PMC5069568 | 9 | 5 | 13 | 3 | 16 | 19 | 4 | 19 | 0 | 35 | 1 |
| PMC5084798 | 10 | 3 | 11 | 17 | 16 | 20 | 10 | 21 | 2 | 30 | 1 |
| PMC5655710 | 8 | 0 | 0 | 19 | 2 | 17 | 8 | 29 | 4 | 38 | 1 |
| PMC5813214 | 10 | 2 | 6 | 8 | 21 | 24 | 9 | 21 | 5 | 35 | 1 |
| PMC5836948 | 6 | 1 | 2 | 4 | 4 | 16 | 6 | 14 | 1 | 23 | 1 |
| PMC7065111 | 8 | 4 | 4 | 4 | 17 | 19 | 8 | 23 | 3 | 32 | 1 |
| PMC9556320 | 23 | 5 | 21 | 4 | 20 | 48 | 12 | 50 | 9 | 87 | 1 |
| PMC9805145 | 4 | 1 | 2 | 1 | 2 | 9 | 4 | 15 | 1 | 27 | 1 |

Totals over 24 papers: {'caption': 63, 'figure': 201, 'footnote': 159, 'page_footer': 314, 'page_header': 437, 'page_number': 229, 'section_header': 653, 'table': 100, 'text': 1044, 'title': 26}

## Chunk quality checks

| Check | element (course baseline) | section (alternative) |
|---|---:|---:|
| chunks | 1044 | 1097 |
| papers | 24 | 24 |
| reference_entries | 3 | 0 |
| fragments_under_50_tokens | 255 | 138 |
| running_headers_repeated_3x | 7 | 1 |
| hyphen_artifacts | 23 | 19 |
| exact_duplicates | 37 | 12 |
| over_window_estimate | 0 | 0 |
| tables | 0 | 132 |
| sections_named | 1021 | 1086 |

## Length distributions

| Strategy | chunks | min | p50 | p95 | max | mean | under 50 tokens | over window |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| element (chars) | 1044 | 1 | 559 | 3164 | 7261 | 886.7 | | |
| element (tokens, est.) | 1044 | 1 | 140 | 791 | 1815 | 221.7 | 255 | 0 |

`element` estimated-token histogram: {'0-50': 255, '50-128': 236, '128-256': 242, '256-384': 125, '384-512': 63, '512-1024': 112, '1024-8192': 11, '8192-': 0}

| section (chars) | 1097 | 11 | 884 | 1472 | 1509 | 851.3 | | |
| section (tokens, est.) | 1097 | 3 | 221 | 368 | 377 | 212.8 | 138 | 0 |

`section` estimated-token histogram: {'0-50': 138, '50-128': 191, '128-256': 310, '256-384': 458, '384-512': 0, '512-1024': 0, '1024-8192': 0, '8192-': 0}

## Token counts from the embedding model

79 chunks embedded one at a time through `course_ops.gateway.embed`: characters per model token min 0.33, median 3.60, max 5.69 (the planning rule assumes 4). Largest sampled chunk: 2255 tokens (7261 chars, `PMC12448458:element:0033`).

| Strategy | id | chars | estimate | model tokens |
|---|---|---:|---:|---:|
| element | PMC12448458:element:0033 | 7261 | 1815 | 2255 |
| element | PMC12448458:element:0032 | 4686 | 1172 | 1712 |
| element | PMC13574348:element:0045 | 5747 | 1437 | 1525 |
| element | PMC13574348:element:0051 | 4440 | 1110 | 1509 |
| element | PMC4973216:element:0035 | 4928 | 1232 | 1486 |
| element | PMC12006245:element:0035 | 4316 | 1079 | 1395 |
| element | PMC7065111:element:0031 | 4493 | 1123 | 1309 |
| element | PMC13190271:element:0015 | 4375 | 1094 | 953 |
| section | PMC4973216:section:0025 | 1004 | 251 | 622 |
| element | PMC7065111:element:0001 | 1522 | 380 | 485 |
| element | PMC9556320:element:0020 | 1332 | 333 | 447 |
| element | PMC9556320:element:0085 | 1740 | 435 | 415 |

### Input-window probe

- `inside_window`: 24144 chars (~6036 tokens) → model tokens 6384; error: None
- `beyond_window`: 81486 chars (~20372 tokens) → model tokens 8192; error: None

Reading: a `beyond_window` call that returns a token count capped near 8,192 means silent truncation (the lecture's warning); an error means the service enforces the limit. Either way the section strategy's p95 sits far below it, and the baseline's longest paragraphs are the ones to watch.

## Observations

_Filled in after the run: what the side-by-side showed, which defects the alternative removed, which it introduced, and the strategy chosen for retrieval._
