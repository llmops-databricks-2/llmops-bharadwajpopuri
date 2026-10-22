# The paper corpus

Resolved on 2026-10-22 from the registry's publication links (`trial_references`, 184 links to 123 distinct PMIDs) by
`evidence_curator.papers`: 73 PMIDs are held by PubMed Central; 54 of those are usable, in the Open Access Subset under
a Creative Commons licence with a PDF (21 CC BY, 15 CC BY-NC, 22 CC BY-NC-ND). The other 19 are excluded: 8 have no
article version in the PMC Article Datasets, 4 are CC-licensed but without a PDF, 3 are open access without a
machine-readable licence code, 4 are text-mining-only author manuscripts. The cap of 24 is filled round-robin across the
three therapies, trial-result papers first, then the paper that adds the most trials not yet represented, then the most
recent; the 30 usable papers left out are one `max_papers` change away.

Licence as PubMed Central's dataset reports it; `Link` is how the registry labels the paper's relation to each trial
(RESULT: reports the trial's results; DERIVED: found by PubMed linkage; BACKGROUND: cited by the sponsor). This file is
rewritten from the `papers` table by `notebooks/chunk_inspection.py` after each ingestion run.

| PMCID | Therapies | Year | Journal | Licence | Link | Trials | Title |
|---|---|---:|---|---|---|---|---|
| PMC4973216 | liraglutide | 2016 | Int J Obes (Lond) | CC BY-NC-ND | RESULT | NCT01557166 | Effect of liraglutide 3.0 mg in individuals with obesity and moderate or severe obstructive sleep apnea: the SCALE Sleep Apnea randomized clinical trial |
| PMC5069304 | liraglutide | 2016 | Clin Pharmacokinet | CC BY-NC | RESULT | NCT01272219, NCT01272232 | Liraglutide 3.0 mg for Weight Management: A Population Pharmacokinetic Analysis |
| PMC5069568 | liraglutide | 2016 | Diabetes Obes Metab | CC BY-NC-ND | RESULT | NCT01272219, NCT01272232 | Exposure-response analyses of liraglutide 3.0 mg for weight management |
| PMC5084798 | liraglutide | 2016 | Clin Obes | CC BY-NC-ND | RESULT | NCT01272219 | Improvements in health-related quality of life with liraglutide 3.0 mg compared with placebo in weight management |
| PMC5655710 | liraglutide | 2017 | Diabetes Obes Metab | CC BY-NC-ND | RESULT | NCT00422058, NCT00781937, NCT01272219, NCT01272232, NCT01557166 | Neuropsychiatric safety with liraglutide 3.0 mg for weight management: Results from randomized controlled phase 2 and 3a trials |
| PMC5813214 | liraglutide | 2018 | Clin Obes | CC BY-NC-ND | RESULT | NCT01272219 | Improvements in health-related quality of life over 3 years with liraglutide 3.0 mg compared with placebo in participants with overweight or obesity |
| PMC5836948 | liraglutide | 2018 | Diabetes Obes Metab | CC BY-NC | RESULT | NCT00422058, NCT00781937, NCT01272219, NCT01272232, NCT01557166 | Liraglutide and cardiovascular outcomes in adults with overweight or obesity: A post hoc analysis from SCALE randomized controlled trials |
| PMC7065111 | liraglutide | 2020 | Obesity (Silver Spring) | CC BY-NC-ND | RESULT | NCT02963935 | Liraglutide 3.0 mg and Intensive Behavioral Therapy (IBT) for Obesity in Primary Care: The SCALE IBT Randomized Controlled Trial |
| PMC9556320 | semaglutide | 2022 | Nat Med | CC BY | DERIVED | NCT03693430 | Two-year effects of semaglutide in adults with overweight or obesity: the STEP 5 trial |
| PMC9805145 | semaglutide | 2022 | Diabetes Obes Metab | CC BY-NC | DERIVED | NCT04074161 | Ease-of-use and acceptability of the novel semaglutide 2.4 mg single-dose pen-injector in people with overweight or obesity in the STEP 8 phase III trial |
| PMC10092593 | semaglutide | 2023 | Diabetes Obes Metab | CC BY-NC | DERIVED | NCT03548935, NCT03548987 | Semaglutide improves cardiometabolic risk factors in adults with overweight or obesity: STEP 1 and 4 exploratory analyses |
| PMC10288970 | semaglutide | 2023 | J Comp Eff Res | CC BY | DERIVED | NCT04102189 | Semaglutide treatment for obesity in teenagers: a plain language summary of the STEP TEENS research study |
| PMC12006245 | semaglutide | 2025 | Adv Ther | CC BY-NC | DERIVED | NCT03574597 | The Composite Number Needed to Treat for Semaglutide in Populations with Overweight or Obesity and Established Cardiovascular Disease Without Diabetes |
| PMC12447996 | semaglutide | 2025 | JHEP Rep | CC BY | DERIVED | NCT03548935, NCT03552757 | Proteomic signatures reflect effects of semaglutide treatment for MASH |
| PMC13190271 | semaglutide | 2026 | Nat Med | CC BY | DERIVED | NCT03574597 | Semaglutide on liver fibrosis and heart outcomes in patients at high risk of liver fibrosis: a prespecified analysis of the SELECT randomized trial |
| PMC13574348 | semaglutide | 2026 | Circulation | CC BY | DERIVED | NCT03574597 | Effect of Semaglutide on the Inflammatory Biomarker High-Sensitivity CRP in Patients With Established Cardiovascular Disease and Overweight or Obesity in SELECT: A Prespecified Secondary Analysis |
| PMC12448458 | tirzepatide | 2025 | Eur Heart J Open | CC BY | DERIVED | NCT05822830 | Tirzepatide compared with semaglutide and 10-year cardiovascular disease risk reduction in obesity: post-hoc analysis of the SURMOUNT-5 trial |
| PMC12724063 | tirzepatide | 2026 | Obesity (Silver Spring) | CC BY | DERIVED | NCT04184622, NCT04657016, NCT04660643 | People With Lowest Physical Functioning Scores Showed Greatest Improvement After Tirzepatide Treatment |
| PMC12803658 | tirzepatide | 2026 | Diabetes Obes Metab | CC BY-NC | DERIVED | NCT04844918 | Association of baseline characteristics with clinical outcomes of tirzepatide treatment in Japanese patients with obesity disease: A subgroup analysis of the SURMOUNT-J trial |
| PMC12865613 | tirzepatide | 2026 | Obes Pillars | CC BY-NC-ND | DERIVED | NCT04657016, NCT04660643 | Nutritional status with tirzepatide in obesity: A post hoc analysis of the SURMOUNT-1-4 randomized clinical trials |
| PMC12920140 | tirzepatide | 2026 | Nat Med | CC BY-NC-ND | DERIVED | NCT05412004 | Tirzepatide on obstructive sleep apnea-related cardiometabolic risk: secondary outcomes of the SURMOUNT-OSA randomized trial |
| PMC12933222 | tirzepatide | 2026 | Obesity (Silver Spring) | CC BY | DERIVED | NCT04184622, NCT04657003, NCT04657016 | Psychiatric Safety of Tirzepatide in People With Obesity and No Known Major Psychopathology: A Post Hoc Analysis of SURMOUNT |
| PMC12933229 | tirzepatide | 2026 | Obesity (Silver Spring) | CC BY | DERIVED | NCT04184622 | Efficacy and Safety of Tirzepatide in Japanese Participants With Obesity: A Subpopulation Analysis of the SURMOUNT-1 Trial |
| PMC13287229 | tirzepatide | 2026 | Patient | CC BY-NC | DERIVED | NCT05412004 | Patients' Experiences of Obstructive Sleep Apnea and Tirzepatide Treatment: An Exit Interview Study |

Trials with at least one paper in the corpus: 20 of 30 (NCT00422058, NCT00781937, NCT01272219, NCT01272232, NCT01557166, NCT02963935, NCT03548935, NCT03548987, NCT03552757, NCT03574597, NCT03693430, NCT04074161, NCT04102189, NCT04184622, NCT04657003, NCT04657016, NCT04660643, NCT04844918, NCT05412004, NCT05822830).

Pinned trials without an open-access paper here (their evidence comes from the registry's posted results): the semaglutide
phase 2 dose-finding trial, STEP 3, STEP 6, STEP UP, STEP Young, SURMOUNT-MMO, the tirzepatide adolescent trial, SCALE Teens,
SCALE Insulin and SCALE KIDS.
