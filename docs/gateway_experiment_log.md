# Gateway experiment log

Run at 2026-11-03T12:52:48+00:00 against `course_ops.gateway.chat` (chat) and `course_ops.gateway.embed` (embeddings) via `https://dbc-e81ca4d2-f6bd.cloud.databricks.com/ai-gateway/mlflow/v1/`.

| Prompt | Latency (s) | Prompt tokens | Completion tokens | Total | Finish |
|---|---:|---:|---:|---:|---|
| summarise_record | 1.46 | 707 | 181 | 888 | stop |
| compare_two_trials | 2.09 | 719 | 355 | 1074 | stop |
| results_without_context | 3.79 | 135 | 757 | 892 | stop |
| alias_resolution | 0.28 | 205 | 29 | 234 | stop |

Embeddings: 3 inputs, dimension 1024, usage {'prompt_tokens': 94, 'total_tokens': 94}.

## Responses

### summarise_record

- **Population:** Adults ≥ 18 years with overweight or obesity (no diabetes required) (NCT03548935, minimum_age).
- **Intervention & Comparator:** Semaglutide 2.4 mg once‑weekly vs. matching placebo (NCT03548935, interventions).
- **Primary Endpoint & Time Frame:** Percent change in body weight from baseline to week 68 (and proportion achieving ≥5 % loss) (NCT03548935, primary_outcomes).
- **Enrollment:** 1,961 participants were planned/ enrolled (NCT03548935, enrollment_count).
- **Status:** The trial is completed (NCT03548935, overall_status).

Usage detail: `{'completion_tokens': 181, 'prompt_tokens': 707, 'total_tokens': 888, 'completion_tokens_details': None, 'prompt_tokens_details': {'audio_tokens': None, 'cached_tokens': 0}, 'cache_read_input_tokens': 0}`

### compare_two_trials

**Side‑by‑side comparison**

| Characteristic | **NCT03548935 (STEP 1)** | **NCT04184622 (SURMOUNT‑1)** |
|----------------|---------------------------|------------------------------|
| **Population age limits** | Minimum 18 years; no stated maximum (18 Years, minimum_age) | Minimum 18 years; no stated maximum (18 Years, minimum_age) |
| **Intervention** | Semaglutide 2.4 mg once‑weekly (drug) (interventions) | Tirzepatide once‑weekly (drug) (interventions) |
| **Comparator** | Placebo (semaglutide) (interventions) | Placebo (interventions) |
| **Primary endpoint** | Change in body weight % from baseline to week 68; proportion achieving ≥5 % weight loss (primary_outcomes) | Percent change in body weight from baseline to week 72; proportion achieving ≥5 % weight loss (primary_outcomes) |
| **Treatment duration** | 68 weeks (implied by primary outcome time‑point) (primary_outcomes) | 72 weeks (implied by primary outcome time‑point) (primary_outcomes) |
| **Enrollment** | 1,961 participants (enrollment_count) | 2,539 participants (enrollment_count) |

**Head‑to‑head comparability**
Because the two trials used different investigational drugs, slightly different follow‑up periods (68 weeks vs 72 weeks), and were conducted independently, their results cannot be directly compared head‑to‑head.

Usage detail: `{'completion_tokens': 355, 'prompt_tokens': 719, 'total_tokens': 1074, 'completion_tokens_details': None, 'prompt_tokens_details': {'audio_tokens': None, 'cached_tokens': 0}, 'cache_read_input_tokens': 0}`

### results_without_context

**Weight‑loss outcomes at the primary endpoints**

| Trial | Drug (dose) | Mean % body‑weight loss at the primary endpoint* | Journal (year) |
|-------|--------------|--------------------------------------------------|----------------|
| **STEP 1** (Semaglutide Treatment Effect in People with obesity) | Tirzepatide 15 mg (once‑weekly) | **≈ 15 %** (15.0 % ± 0.4 % in the tirzepid​e group vs 2.4 % ± 0.2 % with placebo) | *The New England Journal of Medicine* – 2023 (Ludwig et al.) |
| **SURMOUNT‑1** (Semaglutide Treatment in the Management of Obesity) | Semaglutide 2.4 mg (once‑weekly) | **≈ 14.9 %** (14.9 % ± 0.2 % in the semaglutide group vs 2.4 % ± 0.2 % with placebo) | *The New England Journal of Medicine* – 2021 (Wilding et al.) |

\*The percentages reported are the **mean change from baseline** in body weight at the end of the double‑blind treatment period that was pre‑specified as the primary efficacy endpoint (72 weeks for STEP 1 and 68 weeks for SURMOUNT‑1).

---

### Sources

1. **STEP 1**
   - Ludwig, D., et al. “Effect of Tirzepatide vs Placebo on Weight Loss in Adults with Obesity.” *The New England Journal of Medicine* 389, no. 21 (2023): 2017‑2028. DOI: 10.1056/NEJMoa2207203.
   - The abstract and full text state: “At week 72, mean percent change in body weight was –15.0 % (SE 0.4) with tirzepatide 15 mg vs –2.4 % (SE 0.2) with placebo (P < 0.001).”

2. **SURMOUNT‑1**
   - Wilding, J. P. H., et al. “Once‑weekly Semaglutide in Adults with Overweight or Obesity.” *The New England Journal of Medicine* 384, no. 11 (2021): 989‑1002. DOI: 10.1056/NEJMoa2032183.
   - The primary endpoint result is reported as: “At week 68, mean percent change in body weight was –14.9 % (SE 0.2) with semaglutide 2.4 mg vs –2.4 % (SE 0.2) with placebo (P < 0.001).”

These two phase‑III, randomized, placebo‑controlled trials represent the largest published data sets on tirzepatide (STEP 1) and on the high‑dose formulation of semaglutide (SURMOUNT‑1) for obesity treatment.

Usage detail: `{'completion_tokens': 757, 'prompt_tokens': 135, 'total_tokens': 892, 'completion_tokens_details': None, 'prompt_tokens_details': {'audio_tokens': None, 'cached_tokens': 0}, 'cache_read_input_tokens': 0}`

### alias_resolution

not found in the dataset

Usage detail: `{'completion_tokens': 29, 'prompt_tokens': 205, 'total_tokens': 234, 'completion_tokens_details': None, 'prompt_tokens_details': {'audio_tokens': None, 'cached_tokens': 0}, 'cache_read_input_tokens': 0}`

## Limitations observed

Two runs of the same four prompts (14 Oct 2026, `reasoning_effort="low"`, `max_tokens=1024`); the first run's responses are summarised where they differed.

1. **Response format.** Through the gateway, `message.content` arrives as a list of parts — a `reasoning` summary followed by the `text` — not as a string. The first run crashed on it in the log writer. Agent code cannot assume the OpenAI string contract for this service; `evidence_curator.gateway.split_content` now separates the two.

2. **Grounded prompts behave, with one precision slip.** With records in context, every fact was cited as (NCT ID, field) and the comparison refused to rank the trials. But the summary said "planned sample size of 1,961" when the registry marks that count as ACTUAL — I had not passed `enrollment_type`, and the model filled the gap with a guess. Tools must return the qualifying fields, not just the values.

3. **Run-to-run variance.** Same prompt, same settings: run 1 reported treatment duration as "not found in the dataset", run 2 as "68 weeks (implicit from primary outcome time point)". Both are defensible, but a brief's wording changes between runs, so evaluation has to score meaning (right trial, right field, right number) rather than exact strings.

4. **No context, confident answers.** Asked for STEP 1 and SURMOUNT-1 results with no records attached, both runs produced precise percentages, NEJM references and DOIs. Run 1 gave SURMOUNT-1 as −15.0% at 15 mg (to my knowledge that figure belongs to the 5 mg arm). Run 2 swapped the trials — STEP 1 labelled as tirzepatide at −22.5%, SURMOUNT-1 as semaglutide — and its own reasoning summary shows the confusion ("STEP 1 trial (tirzepatide?)"). The two runs gave different DOIs and page numbers for the same paper, so at least one set is invented, and run 1 added bracketed citation markers as if passages had been retrieved when nothing was. Reported results must come from retrieved passages or the registry's posted results, with every citation checked against its source; the model's memory is not a source.

5. **Over-constrained system prompt.** The alias question returned "not found in the dataset" because the system prompt forbids outside knowledge. Alias resolution belongs to the `drug_aliases` table lookup, not to the model; the agent should route it there.

6. **Cost and latency.** 0.6–3.8 s per call; 27–554 completion tokens. `completion_tokens_details` is null, so hidden reasoning tokens are not itemised — only the short visible summary — which makes reasoning cost hard to attribute. Prompt caching is visible (`cached_tokens: 128` on the fourth call). Embeddings: GTE Large returns 1024 dimensions (pgvector column `vector(1024)`), three inputs cost 94 prompt tokens, and the question scored 0.838 against the relevant passage versus 0.662 against the other. No call hit `max_tokens`; longer briefs will need a higher limit.
