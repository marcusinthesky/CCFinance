---
title: Compiled draft measurements
description: Word counts, exhibit placement and technical-page boundaries at the first shared-draft gate.
---

# Compiled draft measurements

The [shared sections](../../../../../src/latex/projects/ccfinance/src/sections/) contain the completed body and appendix, with one bibliography for both layouts. `just latex::count arxiv` counts shared prose separately from 65 heading words and 480 caption words. `pdfinfo` gives total pages, and `pdftotext` locates headings and exhibits in each rendered PDF. Page entries below give the start of the section and the pages carrying its exhibits. Sections can share a page.

| Shared section | Scored prose target | Draft prose words | FinFM start and exhibits | arXiv start and exhibits |
| --- | ---: | ---: | --- | --- |
| Abstract | 170 | 163 | 1 | 1 |
| Introduction | 430 | 406 | 1 | 1 |
| Related corpora | 370 | 345 | 1 | 2 |
| Construction | 690 | 742 | 2; Table 1 on 2 | 2; Table 1 on 3 |
| Coverage and evaluation | 670 | 660 | 3; Table 2 on 3 | 4; Table 2 on 4 |
| Financial applications | 860 | 810 | 3; Table 3 on 4 | 6; Table 3 on 5 |
| Conclusion | 230 | 209 | 5 | 7 |
| **Technical subtotal** | **3,420** | **3,335** | **1–5** | **1–7** |
| References | — | — | 5 | 7–8 |
| A. Corpus lineage and source pilot | 300 | 217 | 6; Table A1 on 7 | 9; Table A1 on 10 |
| B. Extractor and metadata audits | 500 | 482 | 6; Tables A2–A3 on 7 and 8 | 10; Tables A2–A3 on 10 and 11 |
| C. Issuer identity, focus and coverage | 450 | 346 | 6; Tables A4–A5 on 9 | 12; Tables A4–A5 on 12 and 13 |
| D. Body embeddings and issuer conditioning | 350 | 246 | 7; Table A6 on 10 | 12; Table A6 on 13 |
| E. Study details and sensitivities | 800 | 601 | 7; Tables A7–A9 on 10 | 13; Tables A7–A9 on 14 and 15 |
| F. Access and reproduction | 300 | 176 | 8; Table A10 on 10 | 15; Table A10 on 16 |
| **Appendix subtotal** | **2,700** | **2,068** | **6–10** | **9–16** |
| **Total** | **6,120** | **5,403** | **10 pages** | **16 pages** |

The draft uses five FinFM technical pages against the seven-page cap. This counts the conclusion page, which also starts the references. All three main exhibits fall within the technical pages. The single-column arXiv draft uses seven technical pages and sixteen overall against provisional targets of eleven and twenty-five. Its abstract contains 1,133 characters after normalizing whitespace, below the 1,920-character metadata limit. [Scored budgets](../step-05-score/score.md) · [Venue rules](../step-03-sections/section-map.md#length-budgets)

The construction section uses 52 more words than planned to distinguish the CoreNLP precedent from the Stanza comparison and state the denominator and result of the issuer-conditioning pilot. The financial-applications section and shorter introductory and closing passages absorb that allocation. The appendix uses 632 fewer prose words than planned because its ten exhibits carry the detailed counts, comparisons and restoration ledger. Five FinFM appendix exhibits share the final float page and remain cross-referenced from their respective sections. The layout leaves room for substantive edits during review.

Both targets passed `just latex::check` in the pinned shell. The builds have resolved citations and references, with distinct appendix table destinations in the arXiv PDF. The arXiv log reports underfull spacing in one bibliography entry with a long source URL. The working draft uses the existing arXiv byline placeholder and publishes no identifying CCFinance repository or staging URL in the FinFM text.
