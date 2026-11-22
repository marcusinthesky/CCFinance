---
title: FinFM submission-readiness review
description: Task-by-task assessment of the final manuscript, with independent checks of the issuer frame, audit sample, historical timing and reviewer access.
---

# FinFM submission-readiness review

## Revision disposition

The numbered findings below document the original proof. The revised paper uses its own annual listing-evidence population throughout. The first exhibit now reports coverage at 1, 10 and 50 articles for 34,781 issuer-years in 2017–2025. At 50 usable articles, the lowest and highest annual public-float quintiles qualify in 329 of 6,533 and 5,790 of 6,526 cases. The four-source pilot remains in Appendix A.

The introduction motivates issuer assignment and documents access. The worked Monday-to-Thursday example shows how one canonical story enters two usable issuer counts and one focused count. The main evaluation identifies extraction, accepted-link and article-focus denominators, including the development split and the company-detection condition. The applications report the directions of the bank-pair changes and disclose full-archive alias evidence and baseline solver warnings beside the drift result. Marcus Gawronsky is the sole approved author for the current arXiv byline and has confirmed that he has an OpenReview account.

Reviewed 22 November 2026 on revision `b4a409d`. **Revise before submitting as a FinFM long benchmark paper.** On the fixed 100-firm roster, requiring at least three mentions of the issuer reduces coverage from 94 firms to 57 under the same annual article minimum. I reproduced those counts. Table 2 misidentifies the broader issuer population, and the focus audit conditions on an earlier extraction step that readers need to know about. The workshop PDF fits the venue and the principal corrections use evidence already in the repository. [Coverage and evaluation](../../../../../src/latex/projects/ccfinance/src/sections/04_empirical_design_and_data.tex) · [FinFM call](https://finfm.finhorizons.org/#cfp)

## 01. Frame the paper and its audience

The title poses a question a finance researcher can bring to an NLP benchmark. Can a second team reconstruct which stories and firms entered an estimate? FinFM explicitly accepts evaluation protocols, and CCFinance can show a reviewer how to reconstruct a sample decision. Independent reuse of the dataset depends on access. Anonymous requests to the exact staging revision and to the first four bytes of a named Parquet shard both returned HTTP 401. The same metadata service returned HTTP 200 for the pinned upstream Fine News revision and reported it public and ungated. The code and processed store are private. Update the introduction, conclusion and Appendix F with the observed access status. An anonymized row showing the publication time, capture time, issuer evidence and inclusion decision would let a reviewer work through the rule in the PDF. Rights in article bodies remain source-specific. [Acquisition and revisions](../../../../../data/inputs/fine-news/README.md) · [Reproduction statement](../../../../../src/latex/projects/ccfinance/src/sections/07_appendices.tex) · [FinFM benchmark track](https://finfm.finhorizons.org/#cfp)

## 02. Map claims to evidence

**Correct Table 2, Panel B, and the opening paragraph of Section 4.** The panel builder takes the union of issuer-years with listing evidence and issuer-years with article counts. The five-year screen starts with every distinct issuer in that stored panel. Of its 6,591 issuers, 4,972 have the listing-evidence flag in at least one panel year. A fresh count from the frozen Parquet gives the following results at 47 articles in each of 2018–2022. [Panel construction](../../../../../src/python/apps/pipeline/src/pipeline/stages/research/coverage.py) · [Five-year screen](../../../../../src/python/apps/pipeline/src/pipeline/stages/research/experiments/coverage.py)

| Frame | Issuers | Raw links | Usable links | Focused links |
| --- | ---: | ---: | ---: | ---: |
| Fixed Nasdaq reference roster | 100 | 95 | 94 | 57 |
| All issuers in the stored panel, as counted in Table 2 | 6,591 | 1,147 | 1,102 | 408 |
| Issuers with listing evidence in each of the five study years | 3,188 | 884 | 848 | 328 |

The smallest correction is to label the second row **all issuers in the stored panel**, and say which two routes admit an issuer-year. If the intended comparison requires evidence of listing throughout the window, the third row supplies that distinct comparison. It counts issuers with five flagged years and five years meeting the relevant threshold. The fixed roster answers the published Nasdaq comparison using its own membership rule. [Coverage protocol](../../../../../data/inputs/coverage/README.md) · [Reference study, Appendix A](https://arxiv.org/html/2410.23447v3#Sx1)

The two broader rows can be reproduced in DuckDB from the repository root.

```sql
WITH years_per_issuer AS (
    SELECT cik,
           count_if(year BETWEEN 2018 AND 2022 AND in_universe) AS evidenced,
           count_if(year BETWEEN 2018 AND 2022 AND raw >= 47) AS raw_years,
           count_if(year BETWEEN 2018 AND 2022 AND usable >= 47) AS usable_years,
           count_if(year BETWEEN 2018 AND 2022 AND focused >= 47) AS focused_years
    FROM read_parquet('data/research/coverage/panel.parquet')
    GROUP BY cik
)
SELECT 'All panel issuers' AS frame, count(*) AS issuers,
       count_if(raw_years = 5) AS raw, count_if(usable_years = 5) AS usable,
       count_if(focused_years = 5) AS focused
FROM years_per_issuer
UNION ALL
SELECT 'Listing evidence in all five years', count(*), count_if(raw_years = 5),
       count_if(usable_years = 5), count_if(focused_years = 5)
FROM years_per_issuer WHERE evidenced = 5;
```

## 03. Plan the sections and exhibits

Tables 1 and 2 sit side by side on FinFM page 3. The first gives four exploratory hostname-yield estimates. The second lets a reader see which observations survive and which firms can enter a study. Give Table 2 visual and narrative precedence. Put the source-yield estimates in Appendix A, where they already appear, and retain the comparison in the main prose. Use some of that room for a financial consequence already measured. Among issuer-years in the lowest and highest annual public-float quintiles over 2017–2025, respectively, 5.5% and 89.4% clear 47 usable articles in that year. These are single-year shares. They explain whose coverage is thin, a different question from the five-year roster count. Introduce the collection here as English-language news from selected publisher hosts, covering August 2016–April 2026, with linking to US-listed issuers. The hostname screen also admits general-interest reporting. The frozen report gives the quintile comparison in `data/research/experiments/coverage/tables/size.tex`. [Section map](../step-03-sections/section-map.md) · [Coverage report and inputs](../../../../../data/inputs/coverage/README.md)

## 04. Outline the paragraphs

Keep the author's sequence from proprietary archives and bounded releases through collection, public web archives, cleaning, financial enrichment and the three applications. The opening Reuters example gives the access problem a named study and two identifiable inputs. The reader then travels six paragraphs before CCFinance enters the body in paragraph seven. Give the first paragraph a question to carry through the history. One possible final sentence is “Because a story can mention a firm while reporting on a competitor, two researchers who recover the same text can still construct different firm panels.” When the history moves from GPT-3 in 2020 to CC-News in 2016, cue the step back by explaining that the web archive behind the training example predates GPT-3. That makes the introduction of the foundation's dedicated news crawl easier to follow. [Introduction](../../../../../src/latex/projects/ccfinance/src/sections/01_introduction.tex) · [Paragraph outline](../step-04-paragraphs/paragraph-outline.md)

## 05. Score the emphasis and pacing

**Explain why three mentions, and which articles could enter the audit.** Section 3 states the threshold. Section 4 gives its performance. Three mentions attained the best development F1 across the tested count, position and relevance settings on 217 articles. The 183 held-out articles came from IDs with at least one GLiNER company extraction. The article judge saw the title and up to 12,000 body characters, with five held-out bodies truncated. The rule retained 37 of 65 judged subject pairs, down from 60 of 65. Precision rose from 60 of 188 predicted pairs to 37 of 56. Add the selection rule and frame at first use, and specify the frame in the Table A4 caption. Estimating subject recall across all articles would require sampling articles with zero detected companies as well. [Article draw](../../../../../src/python/apps/pipeline/src/pipeline/stages/processed/experiments/sample_links.py) · [Judge inputs](../../../../../src/python/apps/pipeline/src/pipeline/stages/processed/experiments/company_links.py) · [Threshold selection](../../../../../src/python/apps/pipeline/src/pipeline/stages/research/experiments/company_focus.py)

## 06. Draft for both disciplines

The abstract gives the annual threshold and its consequence before describing the applications. Keep that ordering. “Reverses sign in the Reuters subset” makes the reader supply the comparison. Say that bank-pair counts rose across publishers and fell within Reuters. Gloss the two portfolio legs as the long and short portfolios. [Abstract](../../../../../src/latex/projects/ccfinance/src/sections/00_abstract.tex)

In the technical pages, place the extractor result beside the 96.8% precision of accepted issuer links. Across 40 leads with 118 model-reference company spans, GLiNER and Stanza each recovered 69 exact spans. The 8.43-point F1 difference has a paired 95% interval of −1.76 to +18.76. Stanza's broader organization category includes noncompany entities that count as false positives on this task. Giving the publication year, within-year rank and each system's true-positive, false-positive and false-negative counts per lead would let a reviewer reproduce the scores and paired bootstrap from the stated seed without the article bodies. Keep the separate result on issuer sentences, 10 successes in 16 stories, as a pilot. [Exact-span scoring exercise](../../../../../data/inputs/stanza-microbench/README.md) · [Issuer-vector experiments](../../../../../data/inputs/entity-embeddings/README.md)

## 07. Review the financial evidence

The three reimplementations give the paper a progression. A publisher-month tracker needs a denominator, a bank edge needs two identified institutions, and an overnight portfolio needs dated text and enough securities with signals on the same day. The common-calendar VIX fit difference of −0.132 has a paired interval spanning zero. The bank-pair increase of 177 to 242 becomes a decrease from 50 to 35 for Reuters, a restriction that changes both source mix and volume. Keep the common-calendar and matched-story comparisons adjacent to these results and continue attributing each numerical comparator to the paper version that supplied it. In Appendix E, describe the volatility uncertainty calculation as **10,000 bootstrap samples formed from circular blocks**. The implementation draws multiple blocks for each 49-month sample. [Financial applications](../../../../../src/latex/projects/ccfinance/src/sections/05_results.tex) · [Volatility bootstrap](../../../../../src/python/apps/pipeline/src/pipeline/stages/research/experiments/baker_emv/tracking.py) · [Bank comparisons](../../../replication/tasks/kazinnik-banks/results.md)

**Put historical information availability beside the overnight estimate.** Section 4 explains the 09:00 cutoff and the later release of the encoder. Appendix C adds another material fact. The linker learns alias frequencies from anchors across the entire corpus, including later articles. Dated candidate records and timely captures therefore support a retrospective reconstruction. A point-in-time firm mapping would also require historical alias evidence. In Appendix E report that 16 of 20 fitted baseline body-drift windows produced convergence warnings under the reference procedure's ten-iteration cap. The first fit was in September 2022. Neither diagnostic changes the verified increase from 42 to 110 sessions with both legs after clock recovery. They qualify an inference about forecast performance. [Alias-prior construction](../../../../../src/python/apps/pipeline/src/pipeline/stages/processed/company_links.py) · [Rolling-fit diagnostics](../../../../../data/inputs/lopez-lira-tang/README.md) · [Clock-recovery refit](../../../replication/tasks/lopez-lira-tang/tasks/recovered-events/results.md)

## 08. Refine the writing and its appeal

The strongest prose reasons from something the reader can picture. The Monday publication fetched on Thursday explains the date tolerance. The story that names three banks explains why one article can supply three pairs. The weaker passages change from that voice to an inventory of operations. The introduction's contribution paragraph says “We also audit the additional labels and vector representations” and then refers to “a common annual article requirement.” Put the consequence in the main clause there, and name the firms or dates in place of abstract references to support. The current introduction is 938 words. Preserve its historical order while condensing repeated explanations of direct collection and making room for the question about company focus. At the end, the finance reader should remember what changing a rule costs, and the NLP reader should know which error produced that cost. The 42.1% classifier versus 4.2% judge estimate of the press-release share gives both readers a second example of why choosing a label changes a sample. [Style guide](../../style.md) · [Introduction](../../../../../src/latex/projects/ccfinance/src/sections/01_introduction.tex) · [Evaluation and label example](../../../../../src/latex/projects/ccfinance/src/sections/04_empirical_design_and_data.tex)

## 09. Proof and submission

The anonymous FinFM PDF has 11 pages. Page 5 contains Table 3, the conclusion and the start of the references, so it uses five of seven technical pages. The fonts are embedded and the 242,706-byte PDF fits the form's 50 MB upload limit. The arXiv proof has 17 pages and still carries the placeholder byline “CCFinance contributors.” The shared plain-text abstract has 1,099 characters. The locked exact-span scoring command regenerated the saved results byte for byte, an internal reproduction with the frozen files available. [Layout proof](../step-09-proof/proof.md) · [FinFM requirements](https://finfm.finhorizons.org/#cfp)

The public OpenReview submission invitation confirms the benchmark and long-paper choices. It requires keywords, an OpenReview profile for every author, and acknowledgments about sharing author emails with the chairs, possible post-acceptance publication with an opt-out, and an author presenting in person in Montréal. The CC BY 4.0 selection applies to the submission. The form lists a PDF upload and an optional one-sentence summary. The deadline is **23 November 2026 at 23:59 AoE**, which is **24 November at 13:59 in Johannesburg**. Author profiles and commitments are matters for the submitting authors. [Official submission invitation](https://api2.openreview.net/invitations?id=AAAI.org%2F2027%2FWorkshop%2FFinFM%2F-%2FSubmission) · [Workshop FAQ](https://finfm.finhorizons.org/#faq)
