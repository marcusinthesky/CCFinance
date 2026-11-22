---
title: Substantive review of the CCFinance benchmark paper
description: Cold-read assessments, reverse outline, claim audit and revisions to the shared draft.
---

# Substantive review of the CCFinance benchmark paper

The review began with the five FinFM technical pages from draft `055937b`,
read in PDF order before the scored outline. The evidence check then used the
appendix, arXiv build, [Step 02 evidence map](../step-02-evidence/enrichment.md),
and frozen artifacts. The perspectives below are simulations of the public
Track 02 remit. [FinFM call for papers](https://finfm.finhorizons.org/#cfp)

## Reviewer assessments

**ML reviewer.** The benchmark defines a traceable path from captured text to
eligible financial observations. The main text distinguishes the precision of
an issuer assignment conditional on extracted spans from subject recovery at the
article–issuer level. That distinction matters because the 40-lead extractor
audit leaves 49 of 118 reference company mentions unmatched at exact
boundaries by each system.
The 96.8% link precision concerns accepted links within extracted spans. The
primary audit references are model judgments. Independent repeat agreement on
26 spans establishes agreement within that double-labelled subset. Grounding
the benchmarks in human annotations remains a separate empirical question. The
metadata errors are worth retaining because the press-release and transaction
labels could otherwise define large parts of an evaluation sample. The source
pilot measures weighted hostname yield with four draws per frame. [Identity
and metadata evidence](../step-02-evidence/enrichment.md) · [Company-span
benchmark](../../../../../data/inputs/stanza-microbench/README.md)

**Empirical finance reviewer.** The most direct comparison holds an annual
requirement and the reference roster fixed while changing which articles count.
The 94-to-57 change in qualifying firms is accompanied by a precision–recall
trade-off measured on a separate held-out article sample. The monthly tracker
comparison identifies contemporaneous fit on 49 common months. The bank result
is sensitive to a Reuters restriction that changes source mix and story volume.
Matched quotas ask whether the contrast appears within a fixed common frame
and the extended range crosses zero. The clock parser provides evidence that
coverage changes when previously unreadable timestamps are recovered. The
portfolio mean includes one-leg and zero-leg sessions. Retrospective encoding
and unmeasured pretraining overlap constrain the historical interpretation.
[Paired EMV](../../../replication/tasks/baker-emv/tasks/paired-tracking/results.md)
· [Matched-bank result](../../../replication/tasks/kazinnik-banks/tasks/matched-weeks/results.md)
· [Clock recovery](../../../replication/tasks/lopez-lira-tang/tasks/recovered-events/results.md)

**Organizer synthesis.** The contribution is an evaluation protocol with
frozen records and explicit rules for rebuilding samples at three financial
units. The strongest evidence is the fixed-roster eligibility comparison
together with the held-out focus audit in Table 2 and Section 4. The 42-to-110
increase in sessions with two legs gives the clearest downstream demonstration
that recovering information can change what is measurable while retaining a
negative performance result. The remaining concern is independent reuse.
Upstream archives provide part of the input and authorized access is still
required for the exact project and derived artifacts. Conclusion and Appendix F
state that limit.

## Reverse outline from the technical PDF

| Passage | What the reader learns at the handoff | Evidence presented there |
| --- | --- | --- |
| Abstract | Eligibility changes firm and date support and consequently the estimate that can be evaluated. | The frozen corpus, roster screen and three applications. |
| Introduction ¶1 | Replicating a before-open signal requires the observed article version and a security identifier. | A hypothetical signal and publisher updates. |
| Introduction ¶2 | An archive can retain an observed version after the live page changes. | Proprietary sentiment as a contrasting input requirement. |
| Introduction ¶3 | CCFinance records version, timing, issuer identity and the decision about subject focus. | Construction steps and the link/focus distinction. |
| Introduction ¶4 | Each application adds requirements to a different financial observation. | Publisher-month, bank pair-week and issuer-session support. |
| Related corpora ¶1 | A known text release may still require an agreement or become unavailable. | RCV1, TRC2 and the withdrawn Rémy–Ding downloads. |
| Related corpora ¶2 | A publisher-assigned ticker is an input convenience that archive pages do not supply. | FNSPID and the fixed Nasdaq roster. |
| Related corpora ¶3 | Web archives preserve capture evidence and processing improves text recovery. | CC-News, RefinedWeb, Infini-News and Fine News. |
| Construction ¶1 | Hostname inclusion pins the population and source lineage. | 115 hosts in the rule, 168 staged shards and 14,807,287 IDs. |
| Construction ¶2 | A source pilot estimates yield under this rule on source-specific physical-row populations. | Four paired file–group draws per source and Table 1. |
| Construction ¶3 | Day-level usability accounts for publication/capture lag and recurring copies. | The date rule and canonical exact-text and URL repeats. |
| Construction ¶4 | Company spans require separate resolution against dated listing and alias evidence. | GLiNER, listing anchors, abstention and the appendix extractor comparison. |
| Construction ¶5 | One article can enter several issuer counts and focus is a three-mention rule. | Article–issuer pairs and two examples of subject roles. |
| Construction ¶6 | Metadata and embeddings support further analysis at their own units. | The whole-body artifact and the 16-story issuer pilot. |
| Evaluation ¶1 | Tightening article eligibility changes the firms that clear the same annual count. | The article funnel and the 100-firm and 6,591-issuer screens. |
| Evaluation ¶2 | Identity validity and subject focus use different references. | Extracted-span link estimates and held-out whole-article precision and recall. |
| Evaluation ¶3 | Metadata field validity varies by class and unit. | Press-release shares and transaction recall. |
| Evaluation ¶4 | A volatility index needs article denominators and a co-mention network needs linked pairs. | Publisher–month shares and weighted bank pairs. |
| Evaluation ¶5 | Intraday eligibility adds capture ordering, retrospective encoding and support for portfolio legs. | The New York cutoff, rolling labels and session inclusion rule. |
| Applications opening | The reported benchmarks respond to calendar, publisher and clock choices. | Table 3. |
| Volatility ¶1 | Archived source substitution changes historical fit on the same outcomes. | Six author-data fits, 49 common months and the paired interval. |
| Volatility ¶2 | A shorter crisis-excluded calendar and publisher omissions move the difference. | The March–April and Forbes comparisons. |
| Banks ¶1 | Reference and archived networks exhibit different changes in pair counts. | 33 mapped banks, the complete core and the Reuters subset. |
| Banks ¶2 | Equal quotas and a longer common calendar change the available stories and nodes. | Six- and fourteen-week ranges and descriptive historical comparisons. |
| Drift ¶1 | The timed sample supports relatively few sessions with active legs. | 996 bodies, 171 issuers, 277 evaluated sessions and the negative gross mean. |
| Drift ¶2 | Added clock evidence expands support while the refitted gross mean stays negative. | 667 firm-sessions, arXiv v6 MiniLM, representation and cost checks. |
| Conclusion ¶1 | Eligibility must be reported at the financial unit used by the estimate. | The three study units and their different requirements. |
| Conclusion ¶2 | Conditional reproducibility rests on authorization and frozen inputs. | The artifact-access and reconstruction appendix. |

## Substantive revisions and retained limits

| Passage | Reader difficulty | Revision or reason to retain |
| --- | --- | --- |
| Abstract and Section 5 opening | Readers first encountered a reconstruction condition and generic applications without the outcomes needed to judge the contribution. | Lead with the eligibility question and observed results. Preserve the VIX interval, reversal in the distinct bank-pair change, negative drift and exact-access constraint. |
| Section 3 and Appendix A | The local extractor sample could be read as hand-screened finance stories. The reference to Table A1 also conflated the row comparison with prose identifying its releases. | Name the publisher-filtered lead frame, distinguish the table from the lineage prose and give the exact upstream revisions. |
| Section 5.2 | The Reuters comparison was easy to read as identifying source composition independently of volume. | State that the restriction changes the number of available stories as well as publisher mix. Give the fixed-quota design its own question. Retain foreign-parent proxies and the wide longer-calendar range. |
| Section 5.3 and Appendix E | The spread description hid the contribution of inactive legs and the return normalization. | State the signed active-leg arithmetic and identify the unit notional and zero-leg inclusion in the cost exhibit. Point to the appendix prose for representation intervals and Table A9 for costs. |
| Appendix F | The microbenchmark runner was listed among DVC stages with its repository path alone. | Give the locked Python invocation explicitly. Retain requirements for current artifact authorization, frozen inputs and redistribution rights. |
| Section 4 and Appendix B | An extraction baseline could be generalized to issuer identity or model agreement treated as human validation. | Keep the three estimands separate. The bounds and model-adjudicated references already state the evidential limits. |

## Evidence trace

| Claim or exhibit | Frozen source checked | Interpretation |
| --- | --- | --- |
| Table 1 and Appendix A1 | Source comparison `comparison.csv` and `methods.json`, frozen staging `provenance.json` | Revisions, physical rows, samples, weighted yields and three-degree-of-freedom intervals track the pinned frames. The staging and source-pilot populations differ. |
| Table 2 and Appendix C | Coverage `metrics.json`, report tables, linker `summary.tex` and focus `metrics.json` | Funnel and roster rows agree. The annual threshold applies in each publication year. Capture cohorts apply to the article funnel. Mention precision uses 475 accepted links, recall 578 reference-linkable spans, and the focus test uses 183 articles and 65 positive pairs. |
| Appendix B and Section 4 | Metadata `validation.json`, `validation.tex` and extraction `metrics.json`, Stanza `scores.json` and offsets | Verified separate 400-unit frames, weighted press-release and transaction results, hardware benchmark, 40 leads, eight empty leads and 26 repeat spans. Stanza and GLiNER each recover 69 exact spans. F1 is 43.26% versus 51.69%, with the paired interval spanning zero. Published Stanford all-class numbers have separate denominators. |
| Appendix C–D | Link and [coverage protocols](../../../../../data/inputs/coverage/README.md), [vector census](../../../replication/tasks/lopez-lira-tang/tasks/vectors/README.md) and [issuer-embedding pilot](../../../../../data/inputs/entity-embeddings/README.md) | The added links audit measures identity. The production vectors are body representations. The paired pilot uses 16 common-fit stories and both model-judge eligibility denominators fall below plan. |
| EMV and Appendix E | Paired-tracking `fits.csv`, `intervals.csv`, `shared_months.csv`, and `publisher_influence.csv` | The July 2025 manuscript and Mendeley v1 archive define the reference. The 2026 publication is context. Verified the shared calendar, $R^2$ gap and interval, realized volatility and omission checks. [Author archive v1](https://data.mendeley.com/datasets/rmhtcwnvrk/1) |
| Banks and Appendix E | `comparisons.csv`, six- and fourteen-week `changes.csv` and `placebo-ranks.csv`, and the [reference comparison record](../../../replication/tasks/kazinnik-banks/results.md) | Indexed Table 2 of the July 2023 manuscript corroborates the 13–19 January and 13–19 April windows, the decline from 210 to 172 links and the increase from 1,057 to 1,075 co-mentions. Direct PDF retrieval returned HTTP 403. The detailed final-paper tables and Factiva tags remain unavailable. [CEBRA manuscript](https://congress-files.s3.amazonaws.com/2023-07/Scida_News_and_Networks_CEBRA2023.pdf) |
| Drift and Appendix E | `drift.csv`, recovered panel/refit and dispositions, `paired_drift_intervals.csv`, and `scenarios.csv` | Verified scheduled and evaluated days, both-leg support, conditional interval and negative gross means. The reported +11 bp is the 0.11% overnight MiniLM drift in arXiv v6 Table 8. The Mendeley v2 estimator and recovered refit use different underlying samples. [Table 8](https://arxiv.org/html/2304.07619v6#Sx7.T8) · [Archive v2](https://data.mendeley.com/datasets/f39x226htv/2) |
| Access and Appendix F | Evidence map, terms and repository license | Code and derived artifacts require permission. Anonymous staging retrieval and a reusable public processed package remain unverified. Upstream publisher rights and proprietary comparator input rights remain distinct from the code license. [Common Crawl terms](https://www.commoncrawl.org/terms-of-use) · [Code license](../../../../../LICENSE) |
