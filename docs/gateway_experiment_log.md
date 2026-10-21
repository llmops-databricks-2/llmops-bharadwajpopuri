# Gateway experiment log

Run at 2026-10-14T22:15:26+00:00 against `course_ops.gateway.chat` (chat) and `course_ops.gateway.embed` (embeddings) via `https://dbc-88df4c2c-4033.cloud.databricks.com/ai-gateway/mlflow/v1/`.

| Prompt | Latency (s) | Prompt tokens | Completion tokens | Total | Finish |
|---|---:|---:|---:|---:|---|
| summarise_record | 1.62 | 707 | 175 | 882 | stop |
| compare_two_trials | 3.14 | 719 | 431 | 1150 | stop |
| results_without_context | 3.8 | 135 | 554 | 689 | stop |
| alias_resolution | 0.6 | 205 | 27 | 232 | stop |

Embeddings: 3 inputs, dimension 1024, usage {'prompt_tokens': 94, 'total_tokens': 94}.

## Responses

### summarise_record

_Reasoning summary returned by the model: We need five lines: population, intervention/comparator, primary endpoint and timeframe, enrollment, status. Cite._

- **Population:** Adults ≥ 18 years with overweight or obesity (no diabetes required) (NCT03548935, minimum_age).
- **Intervention & Comparator:** Randomized to semaglutide 2.4 mg once‑weekly vs matching placebo (NCT03548935, interventions).
- **Primary Endpoint & Time Frame:** Percent change in body weight from baseline to week 68 (NCT03548935, primary_outcomes).
- **Enrollment:** Planned sample size of 1,961 participants (NCT03548935, enrollment_count).
- **Status:** The trial is COMPLETED (NCT03548935, overall_status).

Usage detail: `{'completion_tokens': 175, 'prompt_tokens': 707, 'total_tokens': 882, 'completion_tokens_details': None, 'prompt_tokens_details': {'audio_tokens': None, 'cached_tokens': 0}, 'cache_read_input_tokens': 0}`

### compare_two_trials

_Reasoning summary returned by the model: We need table side by side. Use fields. Provide sentence about head to head comparability._

**Side‑by‑Side Comparison**

| Characteristic | **NCT03548935 (STEP 1)** | **NCT04184622 (SURMOUNT‑1)** |
|----------------|---------------------------|------------------------------|
| **Population age limits** | Minimum 18 years; no upper limit specified (18 Years, minimum_age) | Minimum 18 years; no upper limit specified (18 Years, minimum_age) |
| **Intervention** | Semaglutide 2.4 mg once‑weekly (DRUG: Semaglutide) (interventions) | Tirzepatide once‑weekly (DRUG: Tirzepatide) (interventions) |
| **Comparator** | Placebo (DRUG: Placebo (semaglutide)) (interventions) | Placebo (DRUG: Placebo) (interventions) |
| **Primary endpoint** | Change in body weight % from baseline to week 68; proportion achieving ≥5 % weight loss (primary_outcomes) | Percent change from baseline in body weight at week 72; proportion achieving ≥5 % weight loss at week 72 (primary_outcomes) |
| **Treatment duration** | 68 weeks (implicit from primary outcome time point) (primary_outcomes) | 72 weeks (implicit from primary outcome time point) (primary_outcomes) |
| **Enrollment** | 1,961 participants (enrollment_count) | 2,539 participants (enrollment_count) |

**Comparability statement**
Both trials evaluated a GLP‑1‑based agonist versus placebo in adults with overweight/obesity and used similar weight‑loss primary endpoints, but differences in drug (semaglutide vs tirzepatide), treatment duration (68 weeks vs 72 weeks), and sample size mean the results cannot be directly compared head‑to‑head without indirect‑treatment‑comparison methods.

Usage detail: `{'completion_tokens': 431, 'prompt_tokens': 719, 'total_tokens': 1150, 'completion_tokens_details': None, 'prompt_tokens_details': {'audio_tokens': None, 'cached_tokens': 0}, 'cache_read_input_tokens': 0}`

### results_without_context

_Reasoning summary returned by the model: Need to info: STEP 1 trial (tirzepatide?) weight loss % and journal. SURMOUNT-1 trial (semaglutide weekly) weight loss %. Provide primary endpoints and journals. Cite sources._

**STEP 1 Trial (tirzepatide in adults with obesity)**
| Item | Details |
|------|---------|
| **Primary endpoint** | Mean percent change in body weight from baseline to week 72. |
| **Result reported** | **−22.5 %** weight loss with tirzepatide 15 mg (the highest dose) compared with placebo. |
| **Journal of publication** | *The New England Journal of Medicine* (NEJM).  <br>Reference: Jastreboff AM, et al. “Tirzepatide Once Weekly for the Treatment of Obesity.” **N Engl J Med**. 2022;387:205‑216. DOI: 10.1056/NEJMoa2206226. |

**SURMOUNT‑1 Trial (semaglutide 2.4 mg for weight management)**
| Item | Details |
|------|---------|
| **Primary endpoint** | Percent change in body weight from baseline to week 68. |
| **Result reported** | **−14.9 %** weight loss with semaglutide 2.4 mg versus placebo. |
| **Journal of publication** | *The New England Journal of Medicine* (NEJM).  <br>Reference: Wilding JPH, et al. “Once‑Weekly Semaglutide in Adults with Overweight or Obesity.” **N Engl J Med**. 2021;384:989‑1002. DOI: 10.1056/NEJMoa2032183. |

**Sources**

1. Jastreboff AM, et al. “Tirzepatide Once Weekly for the Treatment of Obesity.” *N Engl J Med*. 2022;387:205‑216. https://doi.org/10.1056/NEJMoa2206226.
2. Wilding JPH, et al. “Once‑Weekly Semaglutide in Adults with Overweight or Obesity.” *N Engl J Med*. 2021;384:989‑1002. https://doi.org/10.1056/NEJMoa2032183.

Both studies met their primary efficacy endpoints by demonstrating statistically significant and clinically meaningful reductions in body weight, with the percentages above representing the mean weight loss observed at the pre‑specified primary time points.

Usage detail: `{'completion_tokens': 554, 'prompt_tokens': 135, 'total_tokens': 689, 'completion_tokens_details': None, 'prompt_tokens_details': {'audio_tokens': None, 'cached_tokens': 0}, 'cache_read_input_tokens': 0}`

### alias_resolution

_Reasoning summary returned by the model: Need dataset, but none provided. So answer not found._

not found in the dataset

Usage detail: `{'completion_tokens': 27, 'prompt_tokens': 205, 'total_tokens': 232, 'completion_tokens_details': None, 'prompt_tokens_details': {'audio_tokens': None, 'cached_tokens': 128}, 'cache_read_input_tokens': 128}`

## Limitations observed

Two runs of the same four prompts (14 Oct 2026, `reasoning_effort="low"`, `max_tokens=1024`); the first run's responses are summarised where they differed.

1. **Response format.** Through the gateway, `message.content` arrives as a list of parts — a `reasoning` summary followed by the `text` — not as a string. The first run crashed on it in the log writer. Agent code cannot assume the OpenAI string contract for this service; `evidence_curator.gateway.split_content` now separates the two.

2. **Grounded prompts behave, with one precision slip.** With records in context, every fact was cited as (NCT ID, field) and the comparison refused to rank the trials. But the summary said "planned sample size of 1,961" when the registry marks that count as ACTUAL — I had not passed `enrollment_type`, and the model filled the gap with a guess. Tools must return the qualifying fields, not just the values.

3. **Run-to-run variance.** Same prompt, same settings: run 1 reported treatment duration as "not found in the dataset", run 2 as "68 weeks (implicit from primary outcome time point)". Both are defensible, but a brief's wording changes between runs, so evaluation has to score meaning (right trial, right field, right number) rather than exact strings.

4. **No context, confident answers.** Asked for STEP 1 and SURMOUNT-1 results with no records attached, both runs produced precise percentages, NEJM references and DOIs. Run 1 gave SURMOUNT-1 as −15.0% at 15 mg (to my knowledge that figure belongs to the 5 mg arm). Run 2 swapped the trials — STEP 1 labelled as tirzepatide at −22.5%, SURMOUNT-1 as semaglutide — and its own reasoning summary shows the confusion ("STEP 1 trial (tirzepatide?)"). The two runs gave different DOIs and page numbers for the same paper, so at least one set is invented, and run 1 added bracketed citation markers as if passages had been retrieved when nothing was. Reported results must come from retrieved passages or the registry's posted results, with every citation checked against its source; the model's memory is not a source.

5. **Over-constrained system prompt.** The alias question returned "not found in the dataset" because the system prompt forbids outside knowledge. Alias resolution belongs to the `drug_aliases` table lookup, not to the model; the agent should route it there.

6. **Cost and latency.** 0.6–3.8 s per call; 27–554 completion tokens. `completion_tokens_details` is null, so hidden reasoning tokens are not itemised — only the short visible summary — which makes reasoning cost hard to attribute. Prompt caching is visible (`cached_tokens: 128` on the fourth call). Embeddings: GTE Large returns 1024 dimensions (pgvector column `vector(1024)`), three inputs cost 94 prompt tokens, and the question scored 0.838 against the relevant passage versus 0.662 against the other. No call hit `max_tokens`; longer briefs will need a higher limit.
