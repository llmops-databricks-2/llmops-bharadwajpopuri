# The trial snapshot

The 30 ClinicalTrials.gov records pinned in `src/evidence_curator/seed.py`, as fetched on 2026-10-14 by the
`prepare_trials` workflow. Registry fields (phase, status, enrollment, dates, posted results) are refreshed on every run;
the set of trials changes only when the seed list does. Each row's `source_url` is `https://clinicaltrials.gov/study/<NCT ID>`.

| NCT ID | Therapy | Programme | Acronym | Phase | Status | Enrolled | Start | Results posted | PMIDs | Why it is in the snapshot |
|---|---|---|---|---|---|---:|---|---|---:|---|
| NCT02453711 | semaglutide | PHASE2 | — | PHASE2 | COMPLETED | 957 | 2015-10-01 | yes | 2 | Phase 2 dose-finding of once-daily semaglutide in obesity |
| NCT03548935 | semaglutide | STEP | STEP 1 | PHASE3 | COMPLETED | 1961 | 2018-06-04 | yes | 12 | STEP 1: pivotal phase 3 in obesity without T2D |
| NCT03552757 | semaglutide | STEP | STEP 2 | PHASE3 | COMPLETED | 1210 | 2018-06-04 | yes | 7 | STEP 2: phase 3 in overweight/obesity with T2D |
| NCT03548987 | semaglutide | STEP | STEP 4 | PHASE3 | COMPLETED | 902 | 2018-06-04 | yes | 7 | STEP 4: phase 3 withdrawal/maintenance design |
| NCT03611582 | semaglutide | STEP | STEP 3 | PHASE3 | COMPLETED | 611 | 2018-08-01 | yes | 7 | STEP 3: phase 3 with intensive behavioural therapy |
| NCT03693430 | semaglutide | STEP | STEP 5 | PHASE3 | COMPLETED | 304 | 2018-10-05 | yes | 5 | STEP 5: two-year phase 3 |
| NCT03574597 | semaglutide | SELECT | SELECT | PHASE3 | COMPLETED | 17604 | 2018-10-24 | yes | 22 | SELECT: cardiovascular outcomes trial in overweight/obesity |
| NCT03811574 | semaglutide | STEP | STEP 6 | PHASE3 | COMPLETED | 401 | 2019-01-21 | yes | 3 | STEP 6: phase 3 in East Asian participants |
| NCT04074161 | semaglutide | STEP | STEP 8 | PHASE3 | COMPLETED | 338 | 2019-09-11 | yes | 3 | STEP 8: phase 3 head-to-head versus liraglutide 3.0 mg |
| NCT04102189 | semaglutide | STEP | — | PHASE3 | COMPLETED | 201 | 2019-10-07 | yes | 4 | STEP TEENS: phase 3 in adolescents |
| NCT05646706 | semaglutide | STEP | STEP UP | PHASE3 | COMPLETED | 1407 | 2023-01-04 | yes | 2 | STEP UP: phase 3 of the 7.2 mg dose |
| NCT05726227 | semaglutide | STEP | STEP Young | PHASE3 | ACTIVE_NOT_RECRUITING | 212 | 2023-07-07 | no | 0 | STEP Young: phase 3 in children, not yet reported |
| NCT04184622 | tirzepatide | SURMOUNT | SURMOUNT-1 | PHASE3 | COMPLETED | 2539 | 2019-12-04 | yes | 19 | SURMOUNT-1: pivotal phase 3 in obesity without T2D |
| NCT04657003 | tirzepatide | SURMOUNT | SURMOUNT-2 | PHASE3 | COMPLETED | 938 | 2021-03-29 | yes | 5 | SURMOUNT-2: phase 3 in obesity with T2D |
| NCT04657016 | tirzepatide | SURMOUNT | SURMOUNT-3 | PHASE3 | COMPLETED | 579 | 2021-03-29 | yes | 6 | SURMOUNT-3: phase 3 after a lifestyle lead-in |
| NCT04660643 | tirzepatide | SURMOUNT | SURMOUNT-4 | PHASE3 | COMPLETED | 783 | 2021-03-29 | yes | 8 | SURMOUNT-4: phase 3 withdrawal/maintenance design |
| NCT04844918 | tirzepatide | SURMOUNT | SURMOUNT-J | PHASE3 | COMPLETED | 267 | 2021-05-10 | yes | 4 | SURMOUNT-J: phase 3 in Japanese participants |
| NCT05412004 | tirzepatide | SURMOUNT | SURMOUNT-OSA | PHASE3 | COMPLETED | 469 | 2022-06-21 | yes | 9 | SURMOUNT-OSA: phase 3 in obstructive sleep apnoea |
| NCT05556512 | tirzepatide | SURMOUNT | SURMOUNT-MMO | PHASE3 | ACTIVE_NOT_RECRUITING | 15374 | 2022-10-11 | no | 1 | SURMOUNT-MMO: ongoing morbidity/mortality outcomes trial |
| NCT05822830 | tirzepatide | SURMOUNT | SURMOUNT-5 | PHASE3 | COMPLETED | 751 | 2023-04-21 | yes | 4 | SURMOUNT-5: phase 3 head-to-head versus semaglutide 2.4 mg |
| NCT06439277 | tirzepatide | SURMOUNT | — | PHASE3 | RECRUITING | 300 | 2024-06-03 | no | 0 | Phase 3 in adolescents, recruiting |
| NCT00422058 | liraglutide | PHASE2 | — | PHASE2 | COMPLETED | 564 | 2007-01-10 | yes | 6 | Phase 2 dose-ranging of liraglutide in obesity |
| NCT00781937 | liraglutide | SCALE | — | PHASE3 | COMPLETED | 422 | 2008-10-30 | yes | 7 | SCALE Maintenance: phase 3 after diet-induced weight loss |
| NCT01272219 | liraglutide | SCALE | — | PHASE3 | COMPLETED | 3731 | 2011-06-01 | yes | 17 | SCALE Obesity and Prediabetes: pivotal phase 3 |
| NCT01272232 | liraglutide | SCALE | — | PHASE3 | COMPLETED | 846 | 2011-06-01 | yes | 13 | SCALE Diabetes: phase 3 in overweight/obesity with T2D |
| NCT01557166 | liraglutide | SCALE | — | PHASE3 | COMPLETED | 359 | 2012-06-07 | yes | 6 | SCALE Sleep Apnea: phase 3 in obstructive sleep apnoea |
| NCT02918279 | liraglutide | SCALE | — | PHASE3 | COMPLETED | 251 | 2016-09-29 | yes | 2 | SCALE Teens: phase 3 in adolescents |
| NCT02963922 | liraglutide | SCALE | SCALE™ Insulin | PHASE3 | COMPLETED | 396 | 2017-02-06 | yes | 1 | SCALE Insulin: phase 3 in T2D on basal insulin |
| NCT02963935 | liraglutide | SCALE | SCALE™ IBT | PHASE3 | COMPLETED | 282 | 2017-02-06 | yes | 1 | SCALE IBT: phase 3 with intensive behavioural therapy |
| NCT04775082 | liraglutide | SCALE | — | PHASE3 | ACTIVE_NOT_RECRUITING | 78 | 2021-03-04 | no | 1 | SCALE KIDS: phase 3 in children, not yet reported |

## What the tables look like

`trials` (one row per NCT ID): nct_id, therapy, program, seed_note, acronym, brief_title, official_title, study_type, phase, overall_status, lead_sponsor, sponsor_class, collaborators, conditions, interventions, intervention_therapies, enrollment_count, enrollment_type, allocation, intervention_model, masking, primary_purpose, primary_outcomes, n_primary_outcomes, start_date, primary_completion_date, completion_date, sex, minimum_age, maximum_age, eligibility_criteria, has_results, results_first_post_date, last_update_post_date, n_references, source, source_url, retrieved_at

`trial_references` (one row per trial and PMID): nct_id, pmid, reference_type (BACKGROUND / RESULT / DERIVED), citation, source, retrieved_at — 184 rows, 123 distinct PMIDs on 2026-10-14.

`drug_aliases`: therapy, alias, alias_type (inn / brand / sponsor_code / dose_label / mechanism) — 19 rows.

Head-to-head trials carry both therapies in `intervention_therapies` (STEP 8: semaglutide,liraglutide; SURMOUNT-5: semaglutide,tirzepatide; the semaglutide phase 2 trial had a liraglutide arm), while `therapy` names the therapy the trial is pinned for.
