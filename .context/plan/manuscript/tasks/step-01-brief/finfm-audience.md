---
title: FinFM readership and review brief
description: FinFM submission decision, reader needs and the contribution of the CCFinance benchmark paper.
---

# FinFM readership and review brief

Checked 22 November 2026. Step 01 owns this brief. Update it when the venue publishes new instructions or when a cold read reveals a mistaken assumption.

## Public evidence

FinFM brings together AI researchers, finance academics, practitioners and regulators. Its topics give particular weight to evaluation under realistic information and cost constraints, uncertainty, and model risk. The tentative industry session and production-validation panel give the practical audience a place in the program. The organizing team describes a mix of ML, quantitative finance, data science and responsible AI expertise. [Overview and topics](https://finfm.finhorizons.org/#topics) · [Program](https://finfm.finhorizons.org/#program) · [Organizers](https://finfm.finhorizons.org/#organizers)

The benchmark track accepts datasets and evaluation protocols. The venue plans at least two double-blind reviews and an organizer meta-review in the anonymous AAAI-27 format. Its program committee recruitment targets researchers and practitioners in ML, computational finance and financial NLP. The FAQ describes private submissions and reviews and a non-archival workshop. The official CFP lists an extended deadline of 23 November 2026 at 23:59 Anywhere on Earth. The public OpenReview link returned a loading shell during this check, so the CFP supplies the verified submission requirements. [CFP](https://finfm.finhorizons.org/#cfp) · [Committee](https://finfm.finhorizons.org/#committee) · [FAQ](https://finfm.finhorizons.org/#faq) · [OpenReview](https://openreview.net/group?id=AAAI.org/2027/Workshop/FinFM)

## Editorial implications for CCFinance

Use Track 02, Benchmark papers, with a long paper of up to seven technical pages, excluding references and appendices. The contribution, audited sample and strongest evidence from the three applications need room in the technical pages because reviewers may skip supplementary material. Use the same argument in the arXiv layout. [CFP](https://finfm.finhorizons.org/#cfp) · [Manuscript build](../../../../../src/latex/README.md)

The primary reader is an empirical finance or financial NLP researcher deciding whether to construct a study sample from archived news. The finance reader brings trading and sampling conventions. The NLP reader brings extraction and evaluation practice. They meet where a dated article and an issuer link jointly determine what enters a financial observation. Treat the following assumptions as hypotheses about the audience and test them during review.

| Reader | Assumed concept | Premise to supply | Decision the paper should enable |
| --- | --- | --- | --- |
| ML and financial NLP researcher | Held-out model evaluation | Market cutoffs determine which article versions can enter an observation | Choose an eligibility rule and reproduce its evaluation sample |
| Empirical finance researcher | Trading sessions and sample selection | A company mention becomes a firm-level observation only after dated identity resolution and a study-specific relevance rule | Decide which issuers and dates support the design and how a stricter rule changes support |
| Practitioner or risk validator | Audit trails | An article–issuer link can be traced to a corpus revision, supporting mention and dated issuer record | Decide whether link and timing evidence suffice for a specified use |
| Policy or regulatory reader | Accountability for evidence and access | The evaluated population is selected by capture, publisher and issuer rules, and article text has source-specific terms | Identify the population and uses to which the evidence can reasonably speak |

## Research question and contribution

**Question.** Under what conditions can a researcher reconstruct a financial news sample from archived web captures, and how do coverage, issuer identity and timestamp evidence affect the financial measurements that sample supports?

**Contribution.** CCFinance builds a versioned financial news dataset from Common Crawl News by preserving available source and timing evidence, linking extracted mentions to dated issuer records and evaluating which linked stories satisfy explicit research eligibility rules.

**Answer the evidence supports.** Archived news supports traceable samples under explicit coverage, identity and timing rules. The number of available story records alone gives little guidance about the number of eligible observations for a particular design. The coverage audit and the three studies show the consequences of changing the unit or eligibility rule. [Dataset requirements and coverage targets](../../../dataset-research/tasks/dataset-requirements/README.md) · [Replication estimates and inference](../../../replication/comparison.md)

## Argument and closest comparisons

1. A paper can publish its estimator while subsequent researchers still need the same story versions, text fields and annotations to reconstruct the sample. Heston and Sinha illustrate the value of a vendor's machine-coded sentiment and the dependence on its proprietary construction. Reuters also issued bounded research collections such as RCV1 and TRC2 under access agreements. The research releases and the proprietary NewsScope measures are distinct inputs. [Heston and Sinha](https://www.federalreserve.gov/econresdata/feds/2016/files/2016048pap.pdf) · [Reuters Corpora at NIST](https://trec.nist.gov/data/reuters/reuters.html)
2. Site-specific collection gives researchers more control over article text. The Pricing Perspective appendix shows how a Nasdaq per-symbol archive leads to a coverage-conditioned firm frame and supplies ticker-level assignment. FNSPID is the closest direct comparison for large stock-aligned news and demonstrates how to document the acquisition route and count records with stock symbols and available text. CCFinance should apply that reporting practice to distinct captures, dated issuer links and study-eligible units. A historical Reuters/Bloomberg collection also shows why durability matters. Its maintainers withdrew the original downloads, citing publisher rights. [Pricing Perspective, Appendix A](https://arxiv.org/html/2410.23447v3#Sx1) · [FNSPID, Sections 3–4](https://arxiv.org/html/2402.06698v1) · [Rémy and Ding release record](https://github.com/philipperemy/financial-news-dataset)
3. Public Common Crawl archives, including the CC-News collection launched in 2016, make captured pages available without depending on the continued operation of the original publisher page. RefinedWeb demonstrated web filtering and deduplication at pretraining scale. Infini-News extracts and indexes CC-News with capture provenance and derived metadata, while Fine News applies further quality filtering and duplicate removal. CCFinance uses a frozen Fine News selection, so its sampling frame follows the recorded revision and selection rules. Access to an archive and downstream rights to its text are separate questions. [CC-News announcement](https://commoncrawl.org/blog/news-dataset-available) · [RefinedWeb](https://arxiv.org/abs/2306.01116) · [Infini-News data card](https://huggingface.co/datasets/ruggsea/infini-news-corpus) · [Fine News data card](https://huggingface.co/datasets/ksolovev/fine-news) · [Frozen acquisition](../../../../../data/inputs/fine-news/README.md) · [Common Crawl terms](https://www.commoncrawl.org/terms-of-use)
4. A trading or network study needs a defined issuer, an observed text version and enough timing evidence for its observation rule. A capture timestamp records retrieval and a publisher timestamp is evidence of reported publication. For ambiguous dates and repeated or updated stories, the distinction matters to the set of articles a researcher can use. Describe what the implemented date recovery, issuer linking and firm-focus assessments establish, along with their validation populations. A main-text exhibit should show how the same coverage threshold changes the eligible roster as these rules are applied. Claims about corpus rank, available research artifacts or further enrichments require their own evidence. [Coverage audit](../../../dataset-research/tasks/coverage-audit/README.md) · [Dataset requirements](../../../dataset-research/tasks/dataset-requirements/README.md)

## Role of the replications

The studies change what constitutes an observation and therefore the capability tested. Each reconstructs a selected financial measurement using the available corpus and documents where its inputs and estimates differ from the reference design. [Replication plan and protocols](../../../replication/README.md) · [Comparisons and uncertainty](../../../replication/comparison.md)

| Exercise | Observation | What the exercise establishes |
| --- | --- | --- |
| Baker, Bloom, Davis and Kost | Publisher-month coverage used to construct an equity market volatility index | Whether article counts support a common-calendar tracking comparison and how much uncertainty surrounds the difference |
| Kazinnik, Killen, Scidá and Wu | Bank co-mentions during earnings weeks | Whether dated issuer links recover reference network features and how changes in publisher composition affect the comparison |
| López-Lira and Tang | Issuer-session observation with news eligible at a market cutoff | Whether time and issuer evidence support a forward drift test and how limited portfolio support affects its interpretation |

In the return study, establish the timing rule and the retrospective encoder's role before presenting drift. Report estimates alongside their support and uncertainty in all three studies. [Comparison and inference](../../../replication/comparison.md)

## How to research and revisit the brief

Read the current call and public submission instructions for requirements, then the topics, program and committee remit for audience signals. Record the date, source and editorial implication of each material change. Use a relevant publicly available benchmark paper to inspect how it defines a reusable unit or presents uncertainty; describe the specific practice and whether it fits CCFinance. Organizer biographies and public research can clarify terminology. Reviewer assignments, personal tastes and private review criteria are unknown. Record assumptions as such and revise them when a reader cannot follow an inference.
