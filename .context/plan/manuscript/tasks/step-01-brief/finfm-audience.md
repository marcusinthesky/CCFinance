---
title: FinFM readership and review brief
description: Public venue signals and working assumptions for the CCFinance benchmark paper.
---

# FinFM readership and review brief

Checked 22 November 2026. Step 01 owns this brief. Update it when the venue publishes new instructions or when a cold read reveals a mistaken assumption.

## Public evidence

FinFM brings together AI researchers, finance academics, practitioners and regulators. Its topics give particular weight to evaluation under realistic information and cost constraints, uncertainty, and model risk. The tentative industry session and production-validation panel give the practical audience a place in the program. The organizing team describes a mix of ML, quantitative finance, data science and responsible AI expertise. [Overview and topics](https://finfm.finhorizons.org/#topics) · [Program](https://finfm.finhorizons.org/#program) · [Organizers](https://finfm.finhorizons.org/#organizers)

The benchmark track explicitly accepts datasets and evaluation protocols. Short and long papers allow four and seven technical pages respectively, with references and appendices outside that allowance. Reviewers may skip supplementary material. The venue plans at least two double-blind reviews and an organizer meta-review. PC recruitment targets researchers and practitioners in ML, computational finance and financial NLP. The FAQ describes private submissions and reviews. The public OpenReview page confirmed the venue but exposed no review text or scoring rubric in this inspection. [CFP](https://finfm.finhorizons.org/#cfp) · [Committee](https://finfm.finhorizons.org/#committee) · [FAQ](https://finfm.finhorizons.org/#faq) · [OpenReview](https://openreview.net/group?id=AAAI.org/2027/Workshop/FinFM)

## Editorial implications for CCFinance

Working recommendation: benchmark track. Choose the length when budgeting the exhibits. The assumptions below describe plausible reader needs; test them against the manuscript during review.

| Reader | Likely familiar ground | Premise to supply | Question the paper should answer |
| --- | --- | --- | --- |
| ML and financial NLP researcher | Embeddings, extraction and evaluation splits | A recognized name can map to different issuers over time, and crawl time can differ from the first public release | Can I rerun a comparable evaluation on the same stories, labels and split? |
| Empirical finance researcher | Trading sessions, portfolio construction and sample selection | A company mention, dated issuer link and company-focused story define different observations; model-adjudicated labels have measured error | Which firms and dates survive my research design, and how sensitive is my result to that choice? |
| Practitioner or risk validator | Operational cutoffs, validation and audit trails | Which corpus revision, link evidence and representation generated an observation, and which artifacts can another team obtain? | Can I trace a consequential error and decide whether this field is reliable enough for my use? |
| Policy or regulatory reader | Accountability and the need to substantiate claims | Define the coverage population, annotation provenance and conditions of text access in plain language | Which uses does the evidence support, and where does an access or coverage limit qualify the conclusion? |

Lead with the reproducibility problem and the resource a reader can use. Use the three replications to demonstrate what changes when the unit shifts from publisher-month to bank pair to firm-session. A main-text exhibit comparing usable and company-focused coverage directly serves readers choosing a sample. In the return study, explain publication time, capture time, the trading cutoff and the retrospective encoder before discussing drift or costs.

## How to research and revisit the brief

Read the current call and public submission instructions for requirements, then the topics, program and committee remit for audience signals. Record the date, source and editorial implication of each material change. Use a relevant publicly available benchmark paper to inspect how it defines a reusable unit or presents uncertainty; describe the specific practice and whether it fits CCFinance. Organizer biographies and public research can clarify terminology. Reviewer assignments, personal tastes and private review criteria are unknown. Record assumptions as such and revise them when a reader cannot follow an inference.
