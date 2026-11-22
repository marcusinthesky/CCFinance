---
title: Section map, exhibits and length budgets
description: Reading order, exhibit assignments and page budgets for the shared FinFM and arXiv manuscript.
---

# Section map, exhibits and length budgets

Use the reviewed [reader brief](../step-01-brief/finfm-audience.md) and [evidence map](../step-02-evidence/enrichment.md) for the claims, frozen estimates and citation versions. Both PDF targets use the same section files, argument and exhibit placement.

## Reading order

| Section file | Reader question | Argument and handoff |
| --- | --- | --- |
| `00_abstract.tex` | Can I reconstruct the news sample behind a financial result? | A researcher can reconstruct a specified sample when the capture, dated issuer and eligibility decision are traceable, and the spread between raw and focused roster counts gives the introduction a concrete reason to distinguish archived text from study observations. |
| `01_introduction.tex` | What do I need beyond a published estimator? | Rebuilding a study requires the observed story version and the rules that admit it, which establishes the contribution and raises the question of which existing sources supply that evidence. |
| `02_literature_review.tex` | What can I recover from prior corpora and archives? | Compare Reuters research releases and proprietary news measures, the withdrawn Rémy–Ding downloads, Nasdaq-based samples and CC-News derivatives on text, time, identifiers and access, then ask how the chosen archive can supply a dated issuer observation. |
| `03_methodology.tex` | How does a captured article become an eligible issuer observation? | Follow a captured page from the frozen Fine News publisher selection through publication-date evidence and canonicalization to extracted spans, dated issuer links and a focus screen, then ask how each step changes the evaluated population. |
| `04_empirical_design_and_data.tex` | What survives these rules and what can the validation establish? | Define each audit and financial study population, show the firm coverage lost under the focus screen and distinguish day-level dating from cutoff evidence, then ask what those samples support at publisher-month, bank-pair and firm-session scales. |
| `05_results.tex` | What financial measurements do the reconstructed samples support? | Move from contemporaneous volatility tracking to bank-pair counts and overnight drift, reporting the estimate, uncertainty or sensitivity and empirical support for each so the conclusion can specify what a researcher can reuse. |
| `06_conclusion.tex` | What can I use and what evidence do I still need? | Choose the eligibility rule for the proposed financial observation, report who and what survives it, and distinguish public upstream inputs from restricted CCFinance artifacts before using the appendix to inspect protocols and access requirements. |
| `07_appendices.tex` | How can I inspect the decisions, results and dependencies? | Provide the frozen revisions, evaluation designs, diagnostics, access and reproduction requirements behind the technical pages so a researcher can assess a proposed rebuild. |

The capture-to-focus walk describes evidence dependencies. The documented source lineage is CC-News (launched in 2016), extraction and indexing by Infini-News, filtering and deduplication by Fine News, and the frozen CCFinance staging selection. The four-source pilot compares separate release frames and diagnoses the yield of the historical hostname rule. RefinedWeb is a filtering precedent and comparison source. Keep reported publication time, capture time and retrospective identity/encoding evidence distinct. Use study reference versions specified in Step 02 when assigning dates or attributing estimates. [CC-News launch](https://commoncrawl.org/blog/news-dataset-available) · [Frozen acquisition](../../../../../data/inputs/fine-news/README.md) · [Evidence map](../step-02-evidence/enrichment.md)

## Main exhibits in both layouts

Caption each table with its unit and denominator. Give the finance exercises one row each, with support and uncertainty alongside each estimate.

| Exhibit and location | Reader question | Source, unit and denominator | Space in pages, FinFM / arXiv |
| --- | --- | --- | ---: |
| Table 1, §03, source selection | What yield does the hostname rule give on each candidate archive? | Source comparison `comparison.csv` and `methods.json`. English physical-record yield under each pinned source's native language definition, denominator the estimated English-record total in that source frame. Four independent file–row-group draws with replacement per source. Show weighted yield with exploratory 95% interval and note native filtering/deduplication differences. State the frozen staging count separately in prose. | 0.28 / 0.42 |
| Table 2, §04, audit funnel and issuer sample | How many distinct IDs and which issuer rosters survive the analytical restrictions? | Coverage `metrics.json`. Panel A counts IDs once by capture cohort, across 14,807,287 frozen IDs. Show consistently dated, usable canonical, usable with accepted issuer and usable with at least one focused issuer. Panel B counts issuers meeting 47 associated articles in each publication year 2018–2022, denominator 100 fixed reference firms or 6,591 evidenced issuers. Show raw, usable and focused thresholds. | 0.34 / 0.52 |
| Table 3, §05, financial exercises | At each scale, what changes when the reference input is replaced with the reconstructed sample? | Frozen replication reports. EMV uses R² and paired block interval on 49 common months, with 675,234 eligible articles from four hosts. Bank count uses distinct unordered pairs from each study week, with 33 of 34 reference nodes mapped in CCFinance. Show Reuters-only direction and the matched-week range, with 682 stories per week and 31 publishers, labelled as subsampling variation. Drift uses gross basis points per evaluated session across 277 sessions, including 123 zero-leg sessions and 42 with both legs, and a 21-session block interval conditional on saved predictions. Show clock-recovery support and estimate on its 340-session refit. | 0.55 / 0.75 |

The main paper defines GLiNER2.5 Small spans and dated link abstention and reports held-out mention precision/recall separately from whole-article subject recovery. Give the focus precision–recall trade-off on 183 held-out articles with 65 reference-positive issuer pairs and identify the model judges. A short metadata sentence names the press-release and transaction limitations. Put validation matrices and ancillary tasks in the appendix. Describe the return timing rule, retrospective encoder, and limited two-leg support before the estimate. Flag capture scope and the unknown overlap with encoder pretraining. State in the conclusion that upstream archive paths are public and frozen code and processed artifacts require access, with exact staging access unverified. Keep author-identifying links and paths out of the anonymous target.

## Appendix exhibit allocation in both layouts

Assign each appendix exhibit to the subsection whose question it answers. Page allowances include captions, headings and prose. The sources and exact output and paper versions for each row are recorded in the [evidence map](../step-02-evidence/enrichment.md).

| Appendix and exhibit | Question, source, unit and denominator | Prose words | Pages, FinFM / arXiv |
| --- | --- | ---: | ---: |
| A, Table A1, corpus lineage and source pilot | What inputs and draws define the samples? Acquisition README and source-comparison manifests, `methods.json` and `comparison.csv`. Give physical-record counts and weighting within the four draws per English source frame, sampled English/matched counts and estimated matched totals, alongside frozen IDs and month shards from the staging revision. | 300 | 0.85 / 1.25 |
| B, Tables A2–A3, extractor and metadata audits | Where do the annotation and extraction errors occur? Stanza microbenchmark and metadata `validation.json`. A2 gives exact company-span precision, recall and paired F1 difference on 40 frozen leads, 118 reference spans and ten repeated leads, plus model versions and within-year resampling. Cite Stanford's Stanza model documentation as context for its different all-class task and use the completed microbenchmark protocol for the corpus comparison. A3 separates article form, local span attributes and event-window classes, weighted over 400 units per held-out frame after exclusions. Include reference-positive counts, intervals, judge disagreement and throughput in the audit notes. | 500 | 1.45 / 2.15 |
| C, Tables A4–A5, identity, focus and coverage | Which errors and sample changes follow from link and focus decisions? Company-links `summary.tex`, focus and coverage `metrics.json`. A4 separates extracted-span mentions, reference-positive article–issuer pairs and audits of 300 sampled anchors and 300 sampled decorated-name additions. Give unresolved and ambiguous cases and explain that full-corpus alias priors limit date-valid inference. A5 gives the yearly funnel and issuer coverage profiles, with capture-year denominators for article IDs and publication-year denominators for issuer-specific counts. | 450 | 1.25 / 1.85 |
| D, Table A6, article vectors and issuer conditioning | What has been established for the vector artifacts? Vector census and paired pilot. Start with the vector-alignment census of 14,807,287 nonblank body IDs. Give the pilot funnel from 150 held-out stories to 18 primary-judge eligible and 16 common-fit stories, paired success by arm/encoder and the separate eight audit-eligible stories. Keep deal retrieval and role-swap diagnostics with their pilot denominators. | 350 | 1.05 / 1.55 |
| E, Tables A7–A9, study details and sensitivities | How do design substitutions affect the estimates? A7 gives VIX and realized-volatility fits, including leave-one-publisher-out R² gaps on 49 common months and 47 months after excluding March–April 2020, with 40 calibration months held fixed. A8 gives roster mapping, syndication handling, the original matched weeks and the 14-week extension, covering seven nonoverlapping comparisons with 32 mapped nodes and 158 stories per week. Both January–April 2020 subsampling ranges cross zero in the extension. A9 gives the body/issuer eligibility ledger, session leg support and timing refit, then summarizes paired title/body probes on the same 996 bodies and cost scenarios on all 277 evaluated sessions, including zero-leg days. Distinguish block intervals from matched-story subsampling ranges. [Publisher influence](../../../replication/tasks/baker-emv/tasks/publisher-influence/results.md) · [Bank calendar extension](../../../replication/tasks/kazinnik-banks/tasks/placebo-coverage/results.md) · [Title/body and inference](../../../replication/comparison.md) · [Drift costs](../../../replication/tasks/lopez-lira-tang/tasks/drift-costs/results.md) | 800 | 2.10 / 3.20 |
| F, Table A10, access and reproduction ledger | What can be obtained, and what is needed to rerun each stage? Acquisition, availability ledger and study protocols. Use artifact and stage as units, enumerating the upstream inputs, author archives, local and private artifacts and external dependencies used by the paper. Include verified terms, revision or checksum, and command and prerequisites where applicable. | 300 | 0.80 / 1.20 |
| **Appendix content subtotal** | | **2,700** | **7.50 / 11.20** |

## Length budgets

The FinFM Track 02 long-paper limit is seven pages of technical content in the anonymous AAAI-27 template. The workshop excludes references and appendices from the limit and permits supplemental material that reviewers may skip. Count every PDF page from the title through the last technical content, including front matter, tables and captions and any page they share with references. Check the last technical float as well as the conclusion at proof. Start the references after the technical material if this makes the boundary clearer and clear pending technical floats first. [FinFM call for papers](https://finfm.finhorizons.org/#cfp)

The arXiv page budget is provisional. The arXiv submission overview provides no general manuscript page cap. The submission metadata abstract has a separate 1,920-character maximum. Check the shared abstract against that cap in plain text, with a provisional target of 170 words. [arXiv submission overview](https://info.arxiv.org/help/submit/index.html) · [arXiv metadata instructions](https://info.arxiv.org/help/prep.html#abstract-required)

These are allocations for shared prose and layout estimates, including headings and any exhibits with their captions. Word totals exclude headings, captions, table cells, metadata and bibliography entries. The reserves cover float placement, page boundaries and variation in line wrapping.

| Section or allowance | Shared prose words | FinFM pages | arXiv pages |
| --- | ---: | ---: | ---: |
| Title block and front matter | — | 0.28 | 0.68 |
| `00_abstract.tex` | 170 | 0.30 | 0.38 |
| `01_introduction.tex` | 430 | 0.63 | 1.00 |
| `02_literature_review.tex` | 370 | 0.50 | 0.83 |
| `03_methodology.tex`, incl. Table 1 | 690 | 1.20 | 1.95 |
| `04_empirical_design_and_data.tex`, incl. Table 2 | 610 | 1.24 | 1.99 |
| `05_results.tex`, incl. Table 3 | 920 | 1.75 | 2.65 |
| `06_conclusion.tex` | 230 | 0.34 | 0.52 |
| **Technical content subtotal** | **3,420** | **6.24** | **10.00** |
| Technical layout reserve | — | 0.76 | 1.00 |
| **Technical page budget including reserve** | **3,420** | **7.00** | **11.00** |
| References | — | 1.50 | 2.00 |
| `07_appendices.tex`, incl. Tables A1–A10 | 2,700 | 7.50 | 11.20 |
| Back-matter layout reserve | — | 1.00 | 0.80 |
| **Back-matter budget including reserve** | **2,700** | **10.00** | **14.00** |
| **Overall editorial target including reserve** | **6,120** | **17.00** | **25.00** |

The FinFM allocation fits 3,420 shared prose words, three tables and their captions in an estimated 6.24 technical pages, leaving 0.76 page before the cap. The title and abstract establish the contribution, Table 2 and its audit text establish the evaluation populations and filtering costs, Table 3 carries the three estimates and their limits, and the conclusion states what inputs are accessible. Prove the seven-page fit on the compiled draft. If floats consume the margin, shorten literature positioning or move further methodological details to the appendix while keeping validation populations, capture and identity limits, study support and the access statement in the technical pages.
