# Retrieval log

Run at 2026-11-03T12:28:03+00:00 against `llmops_dev.bharadwajpopuri.paper_chunks_synced` (Lakebase project `lb-llmops-bharadwajpopuri`), queries embedded with `course_ops.gateway.embed`. Top-5 per mode; a *hit* is a result whose paper is linked by the registry to one of the question's expected trials.

## Questions

| Id | Question | Probes | Expected trials | Filter |
|---|---|---|---|---|
| Q1 | What did SURMOUNT-J report for body weight change with tirzepatide in Japanese participants? | exact trial name; filter by therapy | NCT04844918 | tirzepatide |
| Q2 | Do cardiometabolic risk improvements persist over two years of treatment, and what happens after stopping? | paraphrased concept, no trial named | NCT03548935, NCT03548987, NCT03693430 | – |
| Q3 | Wegovy pen ease of use and injection acceptability | brand name the papers never use (alias resolution belongs to the agent) | NCT04074161 | – |
| Q4 | obstructive sleep apnea outcomes | same question, two therapy filters | NCT01557166, NCT05412004 | liraglutide / tirzepatide |
| Q5 | apnea-hypopnea index AHI reduction with tirzepatide | technical term plus acronym: keyword strength | NCT05412004 | – |
| Q6 | neuropsychiatric adverse events, depression and suicidal ideation during treatment | cross-therapy safety question | NCT01272219, NCT04184622 | – |
| Q7 | health-related quality of life and physical functioning improvements | date constraint as a filter rather than words in the query | NCT01272219, NCT04184622, NCT04657016 | year ≥ 2024 |
| Q8 | oral semaglutide 50 mg OASIS 1 trial weight loss results | not in the corpus: what comes back with no threshold | – | – |

## Summary

| Mode | questions | hit@5 | mean first-hit rank | mean latency (s) |
|---|---:|---:|---:|---:|
| semantic (section) | 8 | 7/7 | 1.14 | 0.90 |
| semantic (element) | 8 | 6/7 | 1.33 | 0.82 |
| keyword (section) | 8 | 7/7 | 1.29 | 0.86 |
| keyword all-terms (section) | 8 | 4/7 | 1.00 | 0.76 |
| hybrid (section) | 8 | 7/7 | 1.00 | 2.01 |
| semantic+filter (tirzepatide) | 2 | 2/2 | 1.00 | 0.76 |
| semantic+filter (liraglutide) | 1 | 1/1 | 1.00 | 0.81 |
| semantic+filter (year>=2024) | 1 | 1/1 | 1.00 | 0.78 |

Mean Jaccard overlap of the top-5 sets, semantic vs hybrid on section chunks: 0.37.

## Results by question

### Q1: What did SURMOUNT-J report for body weight change with tirzepatide in Japanese participants?

**semantic (section)** — 1.0 s, first hit at rank 1

| # | score | paper | year | section | text |
|---:|---:|---|---:|---|---|
| 1 | 0.918 | PMC12803658 | 2026 | 1 | INTRODUCTION | In the global phase 3 SURMOUNT clinical studies, participants with obe-sity or overweight had clinically meaningful improvements in body wei… |
| 2 | 0.914 | PMC12933229 | 2026 | 4 | Discussion | In conjunction with lifestyle interventions, Japanese adults with obesity or overweight from the SURMOUNT-­1 trial demonstrated significant … |
| 3 | 0.911 | PMC12933229 | 2026 | 2.1 | Participants | This was a subpopulation analysis of Japanese participants from the SURMOUNT-­1 trial (NCT04184622), conducted in nine countries, that inves… |

**semantic (element)** — 0.81 s, first hit at rank –

| # | score | paper | year | section | text |
|---:|---:|---|---:|---|---|
| 1 | 0.916 | PMC12933229 | 2026 | 2.1 | Participants | This was a subpopulation analysis of Japanese participants from the SURMOUNT-­1 trial (NCT04184622), conducted in nine countries, that inves… |
| 2 | 0.914 | PMC12933229 | 2026 | 4 | Discussion | In conjunction with lifestyle interventions, Japanese adults with obesity or overweight from the SURMOUNT-­1 trial demonstrated significant … |
| 3 | 0.909 | PMC12933229 | 2026 | Study Importance | • What is already known? ○ The global, multicenter, phase 3 SURMOUNT-­1 trial demonstrated substantial and sustained body weight reductions … |

**keyword (section)** — 0.86 s, first hit at rank 1

| # | score | paper | year | section | text |
|---:|---:|---|---:|---|---|
| 1 | 1.600 | PMC12803658 | 2026 | 2.3 | Statistical analyses | This analysis includes data from 17 medical research centres in Japan (data from 1 of 18 study sites were excluded due to a regulatory non-c… |
| 2 | 1.200 | PMC12803658 | 2026 | 2.3 | Statistical analyses | Estimated treatment differences (ETDs) are reported as least squares mean (LSM) (95% confidence interval [CI]). The proportion of participan… |
| 3 | 4.600 | PMC12920140 | 2026 | Mediation analysis | body weight alone. However, the proportion mediated by changes in OSA metrics, AHI and SASHB alone, was not statistically significant (Fig. … |

**keyword all-terms (section)** — 0.79 s, first hit at rank 1

| # | score | paper | year | section | text |
|---:|---:|---|---:|---|---|
| 1 | 0.001 | PMC12803658 | 2026 | 2.3 | Statistical analyses | Estimated treatment differences (ETDs) are reported as least squares mean (LSM) (95% confidence interval [CI]). The proportion of participan… |
| 2 | 0.001 | PMC12803658 | 2026 | 2.3 | Statistical analyses | This analysis includes data from 17 medical research centres in Japan (data from 1 of 18 study sites were excluded due to a regulatory non-c… |

**hybrid (section)** — 2.45 s, first hit at rank 1

| # | score | paper | year | section | text |
|---:|---:|---|---:|---|---|
| 1 | 0.016 (v1/t5) | PMC12803658 | 2026 | 1 | INTRODUCTION | In the global phase 3 SURMOUNT clinical studies, participants with obe-sity or overweight had clinically meaningful improvements in body wei… |
| 2 | 0.015 (v2/t8) | PMC12933229 | 2026 | 4 | Discussion | In conjunction with lifestyle interventions, Japanese adults with obesity or overweight from the SURMOUNT-­1 trial demonstrated significant … |
| 3 | 0.015 (v11/t6) | PMC12933229 | 2026 | ABSTRACT | Objective: This prespecified subpopulation analysis aimed to assess the efficacy and safety of once-­weekly tirzepatide versus placebo along… |

**semantic+filter (tirzepatide)** — 0.75 s, first hit at rank 1

| # | score | paper | year | section | text |
|---:|---:|---|---:|---|---|
| 1 | 0.918 | PMC12803658 | 2026 | 1 | INTRODUCTION | In the global phase 3 SURMOUNT clinical studies, participants with obe-sity or overweight had clinically meaningful improvements in body wei… |
| 2 | 0.914 | PMC12933229 | 2026 | 4 | Discussion | In conjunction with lifestyle interventions, Japanese adults with obesity or overweight from the SURMOUNT-­1 trial demonstrated significant … |
| 3 | 0.911 | PMC12933229 | 2026 | 2.1 | Participants | This was a subpopulation analysis of Japanese participants from the SURMOUNT-­1 trial (NCT04184622), conducted in nine countries, that inves… |

### Q2: Do cardiometabolic risk improvements persist over two years of treatment, and what happens after stopping?

**semantic (section)** — 1.05 s, first hit at rank 2

| # | score | paper | year | section | text |
|---:|---:|---|---:|---|---|
| 1 | 0.793 | PMC12920140 | 2026 | Table 2 | | Changes in cardiometabolic risk measures… |
| 2 | 0.746 | PMC10092593 | 2023 | 4 | DISCUSSION | The greatest reductions in cardiometabolic risk factors were generally observed over the first 20 weeks of semaglutide treatment in both stu… |
| 3 | 0.734 | PMC10092593 | 2023 | 4 | DISCUSSION | analyses, data from STEP 4 indicated that the potential benefits of semaglutide treatment on cardiometabolic risk factors were not main-tain… |

**semantic (element)** — 0.79 s, first hit at rank 3

| # | score | paper | year | section | text |
|---:|---:|---|---:|---|---|
| 1 | 0.793 | PMC12920140 | 2026 | Table 2 | | Changes in cardiometabolic risk measures… |
| 2 | 0.739 | PMC12933222 | 2026 | 1 | Introduction | significantly greater improvements than behavioral weight loss interventions in blood pressure, blood glucose, and other mea-sures of cardio… |
| 3 | 0.720 | PMC10092593 | 2023 | 2.3.3 | Effects on antihypertensive and  | Changes in use of antihypertensive and lipid-lowering medications (stopped, decrease, no change or increase) from week 0 (STEP 1) or week 20… |

**keyword (section)** — 0.82 s, first hit at rank 2

| # | score | paper | year | section | text |
|---:|---:|---|---:|---|---|
| 1 | 2.000 | PMC12448458 | 2025 | Discussion | While the results are pending, consistent data show improvement in several cardiometabolic risk factors with tirzepatide.9,11 The results ar… |
| 2 | 1.800 | PMC10092593 | 2023 | 4 | DISCUSSION | These analyses of data from the STEP 1 and 4 trials report the effects of once-weekly s.c. semaglutide 2.4 mg, as an adjunct to lifestyle in… |
| 3 | 1.800 | PMC12448458 | 2025 | Methods and results | SURMOUNT-5 was a Phase 3b, open-label, randomized trial conducted in participants with obesity and without Type-2 diabetes, comparing tirzep… |

**keyword all-terms (section)** — 0.68 s, first hit at rank –

_no rows_

**hybrid (section)** — 1.97 s, first hit at rank 1

| # | score | paper | year | section | text |
|---:|---:|---|---:|---|---|
| 1 | 0.015 (v3/t8) | PMC10092593 | 2023 | 4 | DISCUSSION | analyses, data from STEP 4 indicated that the potential benefits of semaglutide treatment on cardiometabolic risk factors were not main-tain… |
| 2 | 0.015 (v11/t2) | PMC10092593 | 2023 | 4 | DISCUSSION | These analyses of data from the STEP 1 and 4 trials report the effects of once-weekly s.c. semaglutide 2.4 mg, as an adjunct to lifestyle in… |
| 3 | 0.015 (v13/t4) | PMC12448458 | 2025 | Table 2 Estimated 10-year cardiovascular | Longitudinal trajectories of the predicted 10-year cardiovascular risk and its contributing risk factors—BMI, SBP, and use of antihyper­tens… |

### Q3: Wegovy pen ease of use and injection acceptability

**semantic (section)** — 0.98 s, first hit at rank 1

| # | score | paper | year | section | text |
|---:|---:|---|---:|---|---|
| 1 | 0.762 | PMC9805145 | 2022 | 4 | DISCUSSION | Based on responses from 151 participants. IDEA, Injection Device Experience and Acceptability results suggest that the SPI is easy to use fo… |
| 2 | 0.724 | PMC9805145 | 2022 | 3 | RESULTS | One hundred and fifty-five participants switched to the SPI at week 44 (Table 1). At week 44, site staff rated training as ‘very easy’ for 7… |
| 3 | 0.723 | PMC9805145 | 2022 | 4 | DISCUSSION | However, only 59% answered ‘agree’/ ‘strongly agree’ to the item ‘I am likely to continue using the pen’, potentially reflecting the fact th… |

**semantic (element)** — 0.75 s, first hit at rank 1

| # | score | paper | year | section | text |
|---:|---:|---|---:|---|---|
| 1 | 0.748 | PMC9805145 | 2022 | 4 | DISCUSSION | results suggest that the SPI is easy to use for participants, with mini-mal training burden for HCPs. Participants were familiar with self-i… |
| 2 | 0.747 | PMC9805145 | 2022 | 3 | RESULTS | One hundred and fifty-five participants switched to the SPI at week 44 (Table 1). At week 44, site staff rated training as ‘very easy’ for 7… |
| 3 | 0.731 | PMC9805145 | 2022 | REFERENCES | 1. Food and Drug Administration. Wegovy – prescribing information. 2021. https://www.accessdata.fda.gov/scripts/cder/daf/index.cfm? event=ov… |

**keyword (section)** — 0.82 s, first hit at rank 1

| # | score | paper | year | section | text |
|---:|---:|---|---:|---|---|
| 1 | 1.900 | PMC9805145 | 2022 | 2.3 | Assessments | At week 44, immediately following training in SPI use, the site staff member who had administered the training assessed the ease-of-training… |
| 2 | 1.700 | PMC9805145 | 2022 | 2.2 | Design and procedures | The design of STEP 8 is reported elsewhere.7 Participants were ran-domized to 68 weeks of once-weekly semaglutide 2.4 mg or matching placebo… |
| 3 | 1.600 | PMC9805145 | 2022 | 3 | RESULTS | One hundred and fifty-five participants switched to the SPI at week 44 (Table 1). At week 44, site staff rated training as ‘very easy’ for 7… |

**keyword all-terms (section)** — 0.71 s, first hit at rank –

_no rows_

**hybrid (section)** — 1.82 s, first hit at rank 1

| # | score | paper | year | section | text |
|---:|---:|---|---:|---|---|
| 1 | 0.016 (v1/t4) | PMC9805145 | 2022 | 4 | DISCUSSION | Based on responses from 151 participants. IDEA, Injection Device Experience and Acceptability results suggest that the SPI is easy to use fo… |
| 2 | 0.016 (v2/t3) | PMC9805145 | 2022 | 3 | RESULTS | One hundred and fifty-five participants switched to the SPI at week 44 (Table 1). At week 44, site staff rated training as ‘very easy’ for 7… |
| 3 | 0.016 (v6/t1) | PMC9805145 | 2022 | 2.3 | Assessments | At week 44, immediately following training in SPI use, the site staff member who had administered the training assessed the ease-of-training… |

### Q4: obstructive sleep apnea outcomes

**semantic (section)** — 0.8 s, first hit at rank 1

| # | score | paper | year | section | text |
|---:|---:|---|---:|---|---|
| 1 | 0.821 | PMC13287229 | 2026 | 1 Introduction | Obstructive sleep apnea (OSA) is a common sleep disor-der that affects more than 900 million adults worldwide [1, 2]. Characterized by recur… |
| 2 | 0.769 | PMC4973216 | 2016 | INTRODUCTION | Obstructive sleep apnea (OSA) is a prevalent yet underdiagnosed chronic disorder.1 Together with daytime hypersomnolence, it is estimated to… |
| 3 | 0.744 | PMC12920140 | 2026 | Abstract | Based on the mediation analysis, treating both sleep-disordered breathing and obesity is likely required to optimize the treatment effect on… |

**semantic (element)** — 0.81 s, first hit at rank 1

| # | score | paper | year | section | text |
|---:|---:|---|---:|---|---|
| 1 | 0.773 | PMC13287229 | 2026 | 1 Introduction | Obstructive sleep apnea (OSA) is a common sleep disor-der that affects more than 900 million adults worldwide [1, 2]. Characterized by recur… |
| 2 | 0.771 | PMC13287229 | 2026 | References | 1. Benjafield AV, Ayas NT, Eastwood PR, et al. Estimation of the global prevalence and burden of obstructive sleep apnoea: a lit-eraturebase… |
| 3 | 0.769 | PMC4973216 | 2016 | INTRODUCTION | Obstructive sleep apnea (OSA) is a prevalent yet underdiagnosed chronic disorder.1 Together with daytime hypersomnolence, it is estimated to… |

**keyword (section)** — 0.76 s, first hit at rank 1

| # | score | paper | year | section | text |
|---:|---:|---|---:|---|---|
| 1 | 1.300 | PMC12920140 | 2026 | Competing interests | A.M. is funded by the NIH. A.M. reports income from Eli Lilly, Livanova, Zoll and Powell Mansfield. ResMed gave a philanthropic donation to … |
| 2 | 1.300 | PMC4973216 | 2016 | Outcome measures | The primary efficacy end point was change in AHI (using the American Academy of Sleep Medicine’s recommended 2007 definition, with hypopnea … |
| 3 | 1.200 | PMC12920140 | 2026 | Abstract | Despite advances in obesity pharmacotherapy, the obesity epidemic is predicted to continue to increase over time, leading to a rising preval… |

**keyword all-terms (section)** — 0.76 s, first hit at rank 1

| # | score | paper | year | section | text |
|---:|---:|---|---:|---|---|
| 1 | 0.045 | PMC12920140 | 2026 | Abstract | Obstructive sleep apnea (OSA) is associated with obesity and cardiovascular risk. The SURMOUNT-OSA master protocol comprised two, 52-week, r… |
| 2 | 0.021 | PMC12920140 | 2026 | Abstract | Based on the mediation analysis, treating both sleep-disordered breathing and obesity is likely required to optimize the treatment effect on… |
| 3 | 0.020 | PMC12920140 | 2026 | Competing interests | A.M. is funded by the NIH. A.M. reports income from Eli Lilly, Livanova, Zoll and Powell Mansfield. ResMed gave a philanthropic donation to … |

**hybrid (section)** — 1.74 s, first hit at rank 1

| # | score | paper | year | section | text |
|---:|---:|---|---:|---|---|
| 1 | 0.016 (v4/t2) | PMC4973216 | 2016 | Outcome measures | The primary efficacy end point was change in AHI (using the American Academy of Sleep Medicine’s recommended 2007 definition, with hypopnea … |
| 2 | 0.016 (v3/t6) | PMC12920140 | 2026 | Abstract | Based on the mediation analysis, treating both sleep-disordered breathing and obesity is likely required to optimize the treatment effect on… |
| 3 | 0.014 (v27/t4) | PMC12920140 | 2026 | Abstract | Obstructive sleep apnea (OSA) is associated with obesity and cardiovascular risk. The SURMOUNT-OSA master protocol comprised two, 52-week, r… |

**semantic+filter (liraglutide)** — 0.81 s, first hit at rank 1

| # | score | paper | year | section | text |
|---:|---:|---|---:|---|---|
| 1 | 0.769 | PMC4973216 | 2016 | INTRODUCTION | Obstructive sleep apnea (OSA) is a prevalent yet underdiagnosed chronic disorder.1 Together with daytime hypersomnolence, it is estimated to… |
| 2 | 0.744 | PMC4973216 | 2016 | Outcome measures | The primary efficacy end point was change in AHI (using the American Academy of Sleep Medicine’s recommended 2007 definition, with hypopnea … |
| 3 | 0.732 | PMC4973216 | 2016 | DISCUSSION | This trial examined the effect of weight loss on OSA severity in participants with obesity and moderate/severe OSA who were unable or unwill… |

**semantic+filter (tirzepatide)** — 0.77 s, first hit at rank 1

| # | score | paper | year | section | text |
|---:|---:|---|---:|---|---|
| 1 | 0.821 | PMC13287229 | 2026 | 1 Introduction | Obstructive sleep apnea (OSA) is a common sleep disor-der that affects more than 900 million adults worldwide [1, 2]. Characterized by recur… |
| 2 | 0.744 | PMC12920140 | 2026 | Abstract | Based on the mediation analysis, treating both sleep-disordered breathing and obesity is likely required to optimize the treatment effect on… |
| 3 | 0.735 | PMC13287229 | 2026 | 3.2.6 Treatment Expectations | [10293_DE_TZP] Others reported (in describing whether their expectations had been met): Probably 110%, yeah. I’m now not using the CPAP. My … |

### Q5: apnea-hypopnea index AHI reduction with tirzepatide

**semantic (section)** — 0.79 s, first hit at rank 1

| # | score | paper | year | section | text |
|---:|---:|---|---:|---|---|
| 1 | 0.848 | PMC12920140 | 2026 | Objectives | First, this analysis investigated the association of tirzepatide with changes in cardiometabolic risk markers in participants with moderate-… |
| 2 | 0.838 | PMC12920140 | 2026 | Abstract | Despite advances in obesity pharmacotherapy, the obesity epidemic is predicted to continue to increase over time, leading to a rising preval… |
| 3 | 0.830 | PMC13287229 | 2026 | Abstract | Greater proportions of tirzepatide-treated than placebo-treated patients reported improvements in key symptoms and impacts of obstructive sl… |

**semantic (element)** — 0.78 s, first hit at rank 1

| # | score | paper | year | section | text |
|---:|---:|---|---:|---|---|
| 1 | 0.850 | PMC12920140 | 2026 | Objectives | First, this analysis investigated the association of tirzepatide with changes in cardiometabolic risk markers in participants with moderate-… |
| 2 | 0.827 | PMC13287229 | 2026 | Key Points for Decision Makers | To gain a robust understanding of the obstructive sleep apnea disease burden from the patient perspective and to explore trial participant e… |
| 3 | 0.825 | PMC12920140 | 2026 | Abstract | Despite advances in obesity pharmacotherapy, the obesity epidemic is predicted to continue to increase over time, leading to a rising preval… |

**keyword (section)** — 0.91 s, first hit at rank 2

| # | score | paper | year | section | text |
|---:|---:|---|---:|---|---|
| 1 | 1.800 | PMC12448458 | 2025 | Table 2 Estimated 10-year cardiovascular | Data are least-square mean for per cent (%) change from baseline. Error bars indicate standard error. MTD, maximum tolerated dose; SEMA, sem… |
| 2 | 1.700 | PMC12920140 | 2026 | Mediation analysis | body weight alone. However, the proportion mediated by changes in OSA metrics, AHI and SASHB alone, was not statistically significant (Fig. … |
| 3 | 1.700 | PMC13287229 | 2026 | 1 Introduction | Obstructive sleep apnea (OSA) is a common sleep disor-der that affects more than 900 million adults worldwide [1, 2]. Characterized by recur… |

**keyword all-terms (section)** — 0.86 s, first hit at rank –

_no rows_

**hybrid (section)** — 2.13 s, first hit at rank 1

| # | score | paper | year | section | text |
|---:|---:|---|---:|---|---|
| 1 | 0.016 (v1/t6) | PMC12920140 | 2026 | Objectives | First, this analysis investigated the association of tirzepatide with changes in cardiometabolic risk markers in participants with moderate-… |
| 2 | 0.016 (v2/t5) | PMC12920140 | 2026 | Abstract | Despite advances in obesity pharmacotherapy, the obesity epidemic is predicted to continue to increase over time, leading to a rising preval… |
| 3 | 0.014 (v3/t21) | PMC13287229 | 2026 | Abstract | Greater proportions of tirzepatide-treated than placebo-treated patients reported improvements in key symptoms and impacts of obstructive sl… |

### Q6: neuropsychiatric adverse events, depression and suicidal ideation during treatment

**semantic (section)** — 1.02 s, first hit at rank 1

| # | score | paper | year | section | text |
|---:|---:|---|---:|---|---|
| 1 | 0.755 | PMC5655710 | 2017 | Funding information | Nine (0.3%) individuals receiving liraglutide and 2 (0.1%) receiving placebo reported adverse events of suicidal ideation or behaviour. In p… |
| 2 | 0.755 | PMC5655710 | 2017 | 4 | DISCUSSION | Thus, longitudinal assessment of neuropsychiatric safety in clinical trials may benefit from the combi-nation of adverse event reporting and… |
| 3 | 0.743 | PMC5655710 | 2017 | 4 | DISCUSSION | Although there was a small numerical imbalance in suicidal ideation with liraglu-tide, as indicated through adverse event reporting, no betw… |

**semantic (element)** — 0.9 s, first hit at rank 1

| # | score | paper | year | section | text |
|---:|---:|---|---:|---|---|
| 1 | 0.742 | PMC5655710 | 2017 | 3.3.2 | Columbia-Suicide Severity Rating | On the C-SSRS at baseline, 110 individuals (3.3%) in the liraglutide 3.0 mg group vs 67 (3.6%) in the placebo group reported suicidal… |
| 2 | 0.735 | PMC5655710 | 2017 | Funding information | Aims: Liraglutide, a GLP-1 receptor agonist, regulates appetite via receptors in the brain. Because of concerns regarding the potential of c… |
| 3 | 0.734 | PMC5655710 | 2017 | 4 | DISCUSSION | This was a pooled post hoc analysis of neuropsychiatric safety data across weight management trials with liraglutide 3.0 mg. The overall inc… |

**keyword (section)** — 1.05 s, first hit at rank 1

| # | score | paper | year | section | text |
|---:|---:|---|---:|---|---|
| 1 | 2.700 | PMC5655710 | 2017 | 4 | DISCUSSION | Nevertheless, and in accordance with regulatory guidance, US prescribing information states that patients treated with liraglutide 3.0 mg sh… |
| 2 | 2.000 | PMC5655710 | 2017 | 3.2.2 | Suicidal ideation and behaviour | Nine of 3384 individuals (0.3%, 0.2 events/100 person-years) in the liraglutide 3.0 mg group vs 2 of 1941 (0.1%, <0.1 events/100 person-year… |
| 3 | 1.800 | PMC5655710 | 2017 | Funding information | Nine (0.3%) individuals receiving liraglutide and 2 (0.1%) receiving placebo reported adverse events of suicidal ideation or behaviour. In p… |

**keyword all-terms (section)** — 0.77 s, first hit at rank 1

| # | score | paper | year | section | text |
|---:|---:|---|---:|---|---|
| 1 | 0.004 | PMC5655710 | 2017 | 4 | DISCUSSION | Although there was a small numerical imbalance in suicidal ideation with liraglu-tide, as indicated through adverse event reporting, no betw… |
| 2 | 0.003 | PMC5655710 | 2017 | Funding information | Nine (0.3%) individuals receiving liraglutide and 2 (0.1%) receiving placebo reported adverse events of suicidal ideation or behaviour. In p… |
| 3 | 0.001 | PMC5655710 | 2017 | 4 | DISCUSSION | This was a pooled post hoc analysis of neuropsychiatric safety data across weight management trials with liraglutide 3.0 mg. The overall inc… |

**hybrid (section)** — 2.04 s, first hit at rank 1

| # | score | paper | year | section | text |
|---:|---:|---|---:|---|---|
| 1 | 0.016 (v1/t3) | PMC5655710 | 2017 | Funding information | Nine (0.3%) individuals receiving liraglutide and 2 (0.1%) receiving placebo reported adverse events of suicidal ideation or behaviour. In p… |
| 2 | 0.016 (v4/t1) | PMC5655710 | 2017 | 4 | DISCUSSION | Nevertheless, and in accordance with regulatory guidance, US prescribing information states that patients treated with liraglutide 3.0 mg sh… |
| 3 | 0.016 (v3/t6) | PMC5655710 | 2017 | 4 | DISCUSSION | Although there was a small numerical imbalance in suicidal ideation with liraglu-tide, as indicated through adverse event reporting, no betw… |

### Q7: health-related quality of life and physical functioning improvements

**semantic (section)** — 0.79 s, first hit at rank 1

| # | score | paper | year | section | text |
|---:|---:|---|---:|---|---|
| 1 | 0.772 | PMC12724063 | 2026 | 4.1 | Strengths | Similarly, people with severe baseline physical impairments, like advanced joint degeneration, may experience less improvement in mobility a… |
| 2 | 0.760 | PMC12724063 | 2026 | 4.2 | Limitations | As this was a post hoc analysis, the findings are hypothesis generating rather than confirming. The study relied on self-­reported physical … |
| 3 | 0.732 | PMC5813214 | 2018 | What this study adds | • Durability of changes in HRQoL is of importance in chronic diseases, whereby improvements in HRQoL evident in the short term may not be ma… |

**semantic (element)** — 0.81 s, first hit at rank 1

| # | score | paper | year | section | text |
|---:|---:|---|---:|---|---|
| 1 | 0.800 | PMC12724063 | 2026 | 4.1 | Strengths | and predictors of improvement in physical functioning. A better understanding of these determinants can support more effective treatment dec… |
| 2 | 0.762 | PMC12724063 | 2026 | B) Change in SF-36v2 scores by SF-36v2 P | Highest scores indicate low physical function limitations… |
| 3 | 0.762 | PMC12724063 | 2026 | 4 | Discussion | Highest scores indicate low physical function limitations… |

**keyword (section)** — 0.8 s, first hit at rank 1

| # | score | paper | year | section | text |
|---:|---:|---|---:|---|---|
| 1 | 2.200 | PMC5084798 | 2016 | Introduction | Obesity is a chronic disease associated with an increased risk of type 2 diabetes, cardiovascular disease, select can-cers and a reduced lif… |
| 2 | 1.900 | PMC5813214 | 2018 | Health-related quality of life measures | The 31-item IWQOL-Lite assesses an individual’s perception of the impact of weight on qual-ity of life in five domains (physical function, s… |
| 3 | 1.900 | PMC5813214 | 2018 | Table 4 Change in HRQoL summary scores b | Data analysed using a linear regression model. Missing values post-baseline were imputed using last observation carried forward. HRQoL, heal… |

**keyword all-terms (section)** — 0.72 s, first hit at rank 1

| # | score | paper | year | section | text |
|---:|---:|---|---:|---|---|
| 1 | 0.004 | PMC5084798 | 2016 | Materials and methods | The IWQOL-Lite provides a total score and scores for five subscales: physical function, self-esteem, sexual life, public distress and work. … |
| 2 | 0.003 | PMC5813214 | 2018 | Discussion | Change in score: / Liraglutide 3.0 mg / Placebo / ETD / P-value Physical function / 13.47 / 8.99 / 4.48 / <0.0001 Self-esteem / 14.92 / 11.4… |
| 3 | 0.003 | PMC5084798 | 2016 | Discussion | The proportions of participants with the maximum score (ceiling effect) were high in the IWQOL-Lite sexual life, public distress and work an… |

**hybrid (section)** — 1.91 s, first hit at rank 1

| # | score | paper | year | section | text |
|---:|---:|---|---:|---|---|
| 1 | 0.016 (v3/t4) | PMC5813214 | 2018 | What this study adds | • Durability of changes in HRQoL is of importance in chronic diseases, whereby improvements in HRQoL evident in the short term may not be ma… |
| 2 | 0.015 (v8/t2) | PMC5813214 | 2018 | Health-related quality of life measures | The 31-item IWQOL-Lite assesses an individual’s perception of the impact of weight on qual-ity of life in five domains (physical function, s… |
| 3 | 0.015 (v12/t1) | PMC5084798 | 2016 | Introduction | Obesity is a chronic disease associated with an increased risk of type 2 diabetes, cardiovascular disease, select can-cers and a reduced lif… |

**semantic+filter (year>=2024)** — 0.78 s, first hit at rank 1

| # | score | paper | year | section | text |
|---:|---:|---|---:|---|---|
| 1 | 0.772 | PMC12724063 | 2026 | 4.1 | Strengths | Similarly, people with severe baseline physical impairments, like advanced joint degeneration, may experience less improvement in mobility a… |
| 2 | 0.760 | PMC12724063 | 2026 | 4.2 | Limitations | As this was a post hoc analysis, the findings are hypothesis generating rather than confirming. The study relied on self-­reported physical … |
| 3 | 0.730 | PMC12724063 | 2026 | 4 | Discussion | This post hoc analysis found that tirzepatide treatment was as-sociated with substantial weight reduction across all levels of baseline phys… |

### Q8: oral semaglutide 50 mg OASIS 1 trial weight loss results

**semantic (section)** — 0.77 s, first hit at rank –

| # | score | paper | year | section | text |
|---:|---:|---|---:|---|---|
| 1 | 0.823 | PMC9556320 | 2022 | Discussion | In STEP 5, once-weekly treatment with semaglutide 2.4 mg as an adjunct to behavioral intervention in adults with overweight (with at least o… |
| 2 | 0.817 | PMC9556320 | 2022 | Discussion | Thus, our findings indicate that the substantial weight losses reported during 68 weeks’ treatment with semaglutide 2.4 mg in prior STEP tri… |
| 3 | 0.814 | PMC9556320 | 2022 | Two-year effects of semaglutide in adult | More participants in the semaglutide group than in the placebo group achieved weight loss ≥5% from baseline at week 104 (77.1% versus 34.4%;… |

**semantic (element)** — 0.87 s, first hit at rank –

| # | score | paper | year | section | text |
|---:|---:|---|---:|---|---|
| 1 | 0.823 | PMC9556320 | 2022 | Discussion | In STEP 5, once-weekly treatment with semaglutide 2.4 mg as an adjunct to behavioral intervention in adults with overweight (with at least o… |
| 2 | 0.817 | PMC9556320 | 2022 | Two-year effects of semaglutide in adult | W. Timothy Garvey 1 , Rachel L. Batterham 2,3,4, Meena Bhatta5, Silvio Buscemi 6,7, Louise N. Christensen5, Juan P. Frias8, Esteban Jódar 9,… |
| 3 | 0.811 | PMC9556320 | 2022 | Two-year effects of semaglutide in adult | (BMI ≥ 27 kg m–2 with at least one weight-related comorbidity) or obe-sity (BMI ≥ 30 kg m–2)2–5, based on results from the Semaglutide Treat… |

**keyword (section)** — 0.9 s, first hit at rank –

| # | score | paper | year | section | text |
|---:|---:|---|---:|---|---|
| 1 | 5.100 | PMC12933222 | 2026 | 4 | Discussion | TABLE 6 / Reports of suicidal ideation (SI) and suicidal behavior (SB) obtained with the Columbia Suicide Severity Rating Scale (C-­SSRS) fr… |
| 2 | 4.000 | PMC12933222 | 2026 | 4 | Discussion | TABLE 6 / Reports of suicidal ideation (SI) and suicidal behavior (SB) obtained with the Columbia Suicide Severity Rating Scale (C-­SSRS) fr… |
| 3 | 3.900 | PMC12865613 | 2026 | Table 4 Incidence of treatment discontin | No. (%) / SURMOUNT-1 / SURMOUNT-2 / SURMOUNT-3 / SURMOUNT-4 / Total PBO / TZP 5 mg / TZP 10 mg / TZP 15 mg / PBO / TZP 10 mg / TZP 15 mg / P… |

**keyword all-terms (section)** — 0.75 s, first hit at rank –

_no rows_

**hybrid (section)** — 1.99 s, first hit at rank –

| # | score | paper | year | section | text |
|---:|---:|---|---:|---|---|
| 1 | 0.016 (v2/t4) | PMC9556320 | 2022 | Discussion | Thus, our findings indicate that the substantial weight losses reported during 68 weeks’ treatment with semaglutide 2.4 mg in prior STEP tri… |
| 2 | 0.015 (v5/t7) | PMC9556320 | 2022 | Two-year effects of semaglutide in adult | 1 / Flow chart of trial participants in the STEP 5 clinical trial. s.c., subcutaneous. (BMI ≥ 27 kg m–2 with at least one weight-related com… |
| 3 | 0.015 (v6/t11) | PMC9556320 | 2022 | Discussion | Obesity is a chronic, relapsing disease that requires continuous effort to control6,17. With all nonsurgical interventions and to some exten… |

## Observations

The first run (2026-10-31) used `websearch_to_tsquery` for the keyword channel, which requires every term; its summary was semantic (section) 7/7 hits, semantic (element) 6/7, keyword 4/7 with **no rows at all for Q2, Q3, Q5 and Q8**, hybrid 7/7, overlap semantic–hybrid 0.66. The keyword channel was then changed to match any stemmed term with all-terms matches ranked first (`keyword` above), the all-terms behaviour kept as `keyword all-terms` for comparison, and the log regenerated; the tables above are from the rerun of 2026-11-03 in the course's new workspace, against the synced table re-created there from the copied `paper_chunks`.

1. **Semantic search on section chunks found the expected trial for 7/7 answerable questions (mean first-hit rank 1.14); on the baseline chunks 6/7 (1.33).** The baseline's noise shows through: for Q1 its top-5 were all the SURMOUNT-1 Japanese-subpopulation paper instead of SURMOUNT-J (cosine 0.916 vs 0.914: the embedding does not separate the two); for Q3 and Q4 a reference-list entry ranked in the top 3 (0.771); for Q8 an author line. The section strategy's results read as evidence and carry usable section labels.
2. **Filters do what the lecture says.** Q4 with `therapy = liraglutide` returns only SCALE Sleep Apnea chunks, including "the primary efficacy end point was change in AHI"; with `tirzepatide` only the two SURMOUNT-OSA papers. Q7 with `pub_year ≥ 2024` drops the 2016/2018 HRQoL papers and returns the 2026 physical-functioning paper first. Same question text, different evidence, and the constraint is a predicate the database applies before ranking rather than words the embedding has to honour.
3. **Requiring every keyword was the weak link.** With AND semantics half of the questions returned nothing, including Q5 where the acronym "AHI" was supposed to be the keyword channel's strength (one of the ANDed terms is always missing from a 1,500-character chunk); where it matched it was precise (Q1: the SURMOUNT-J paper, which the vectors could not tell from the SURMOUNT-1 subpopulation paper; Q7: the IWQOL-Lite papers via the exact phrase "physical function"). Hybrid collapsed to semantic on those four questions (`v1/t–` in the first run's log) and matched semantic's 7/7 at twice the latency. Where both channels matched, reciprocal rank fusion promoted evidence that neither channel ranked first (Q7's top result had vector rank 8 and text rank 5; Q4's had 3 and 2). With any-term matching the keyword channel hits 7/7 (mean first-hit rank 1.29) and the hybrid's mean first-hit rank is 1.00, the best of all modes, while its top-5 overlap with semantic falls from 0.66 to 0.37 because the text channel now contributes on every question; `keyword all-terms` keeps the first run's 4/7 for comparison. Postgres `ts_rank_cd` has no IDF, so a trial name weighs no more than "participants", which is why all-terms matches are ranked ahead of partial ones.
4. **Cosine similarity is not a relevance threshold on this corpus.** The out-of-corpus question (OASIS 1, oral semaglutide 50 mg) scored 0.823 against STEP 5 chunks, higher than the correct answers to Q2 (0.746), Q3 (0.762) and Q6 (0.755); the scores of all answered questions sit in a 0.74–0.92 band with margins of a few thousandths between the right paper and a near neighbour. In the first run the only signal of absence was the empty keyword result for the named trial; with any-term matching even that is gone (Q8's keyword channel now returns rows from other semaglutide papers, top score 5.1), so an entity check is the only reliable signal. The agent will need an entity check (the trial name or NCT ID present in the retrieved evidence, or `trial_references` consulted first) rather than a score cutoff.
5. **The brand-name question worked for the wrong reason.** "Wegovy" occurs nowhere in the section chunks (the baseline matched it only in a reference-list entry), yet semantic search found the pen paper at rank 1 on "pen ease of use / injection acceptability" alone. A question whose only anchor is the brand ("Wegovy cardiovascular outcomes") would not be so lucky; alias resolution through `drug_aliases` stays an agent step before retrieval.
6. **Latency and throughput.** About 1.1 s per semantic query, most of it the query-embedding round trip plus a fresh Postgres connection with a minted token per call; hybrid about 2.3 s for two queries. Connection pooling and token reuse (the course's Lakebase memory pattern) are the obvious savings before the agent work. Embedding the corpus took 491,842 tokens in 67 calls and ran into the gateway's per-user tokens-per-minute limit (the first job attempt failed on it; the second waited 60 s across 4 pauses), so re-embedding is a paced batch operation, not an interactive one.
