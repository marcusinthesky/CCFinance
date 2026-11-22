---
title: Paragraph outline for the CCFinance manuscript
description: Planned claims, evidence, reading transitions and shared prose targets.
---

# Paragraph outline for the CCFinance manuscript

**Intended readers and venue.** FinFM's seven-page benchmark track and the shared arXiv preprint address empirical finance and financial NLP researchers who need to reconstruct a news sample. Finance readers know sample selection, trading sessions and returns. NLP readers know extraction and held-out evaluation. Each needs to see how the same captured story becomes distinct usable observations under different financial designs. [Reader brief](../step-01-brief/finfm-audience.md)

**Evidence and budgeting.** Short references below point to the exact outputs, paper versions and terms in the [claim-to-evidence map](../step-02-evidence/enrichment.md). Exhibit numbers follow the [section map](../step-03-sections/section-map.md). The [Step 05 score](../step-05-score/score.md) records revisions and page estimates. Targets count prose only.

## `00_abstract.tex` · 170 words

**Question and answer.** What makes an archived-news sample reconstructible? A record of the observed version, dated issuer and rule that admitted the observation.

- **170 words.** CCFinance makes the construction of a financial news sample traceable from web capture to study observation, and the choice of eligibility rule changes the firms and sessions that support a result.
  - Evidence. Identify the pinned CC-News–Fine News lineage, issuer linkage and validation. Use the 94 usable and 57 focused roster firms under the same coverage rule, then describe what the publisher-month, bank-pair and firm-session applications measure. State that access to frozen artifacts is restricted.
  - Carry forward. The coverage difference raises the question of what must be reconstructed before an estimator can run.
  - Pace. One paragraph. Lead with the research need, foreground the coverage difference and budget for the arXiv metadata character limit.

## `01_introduction.tex` · 430 words

**Question and answer.** What do I need beyond a published estimator? An inspectable input sample and the rules connecting its stories to the financial observation.

- **110 words.** The observation behind a news-based estimate depends on a specific story version, its timing and the rule that admits it.
  - Evidence. Take a firm return observed from the open to the close. For a text signal intended to precede that interval, the researcher needs the issuer and documentary evidence that the version used in the signal was already observable.
  - Carry forward. Which input records can a second team obtain and audit?
  - Pace. Introduce the financial object before the term “capture” and explain the trading cutoff for NLP readers.
- **125 words.** Proprietary data access can leave a published result dependent on story and annotation inputs another researcher needs to acquire separately.
  - Evidence. Heston–Sinha's proprietary Reuters sentiment shows why a published specification alone can leave text measurement vendor-dependent. Publishers and archive operators can also provide bounded research releases. Reserve the details of those alternatives for §02.
  - Carry forward. If an archived source supplies the text, what additional work gives it financial meaning?
- **115 words.** CCFinance contributes a versioned construction from archived text to study-specific eligible units.
  - Evidence. Introduce the recorded source version, date evidence, canonical record, dated issuer and study rules in dependency order. Leave the quantitative coverage preview to the abstract and Table 2.
  - Carry forward. Which parts of the construction matter for an actual estimate?
- **80 words.** Three financial exercises test increasingly specific requirements of the reconstructed corpus.
  - Evidence. Publisher-month volatility tracking uses article counts. Bank networks add dated identities. Overnight drift adds a trading cutoff and enough eligible securities to form portfolios.
  - Carry forward. Start the comparison with earlier sources that can supply different parts of this evidence.
  - Pace. Name each added requirement once and leave estimates for §05.

## `02_literature_review.tex` · 370 words

**Question and answer.** Which prior sources supply reusable text, time and identity fields? Vendor research releases, site-specific collections and shared web archives supply different combinations of those fields.

- **100 words.** Research access to vendor-origin text has been possible in defined releases, where the release period, fields and access agreement determine the usable sample.
  - Evidence. RCV1 and TRC2 from NIST, distinguished from NewsScope measures, and the Rémy–Ding maintainers' documented withdrawal of original downloads on copyright grounds.
  - Carry forward. What does direct collection let a researcher control, and what does its starting source select?
- **135 words.** Site-specific collection gives researchers control over extracted bodies while the pages and symbols available shape the study population.
  - Evidence. FNSPID §§3–4 records the Nasdaq headline/URL and body collection steps and supplementary sources. Pricing Perspective Appendix A uses a public per-symbol archive, ticker assignment and 47 raw articles in each of five years to form its 100-firm sample.
  - Carry forward. A shared archive can supply observed versions after the originating page changes. Which improvements make that archive tractable?
  - Pace. Distinguish a site's ticker assignment from a resolved issuer link for both audiences.
- **135 words.** Shared crawl archives and text processing make observed news versions easier to reuse, leaving study eligibility to be constructed from those versions.
  - Evidence. CC-News launched in 2016 and supplies WARC records. Infini-News extracts and indexes them, and Fine News adds quality filtering and deduplication. RefinedWeb establishes large-scale filtering as a separate precedent. Link the release terms where archival availability is introduced.
  - Carry forward. Follow a single record through the pinned selection, dates and identity rules.
  - Pace. Use chronology for releases and dependency language for data lineage.

## `03_methodology.tex` · 690 words

**Question and answer.** How does a capture become a candidate observation? Selection defines which records enter, provenance preserves a version, and timing and entity evidence allow design-specific rules to operate.

- **120 words.** The pinned English Fine News input and historical hostname list define which captured news records can enter CCFinance.
  - Evidence. The historical registry lists 115 entries. A normalized hostname qualifies by exact match or as a dot-delimited subdomain of an entry. State the upstream revision and separate restored staging revision, with 14,807,287 distinct staged IDs across 168 monthly shards and checksums.
  - Carry forward. How selective is the same hostname rule when applied retrospectively to other source frames?
  - Pace. Explain record/ID and archived version before using “article” for the canonical unit.
- **115 words.** The same hostname rule yields different fractions of physical English records across four pinned source frames.
  - Evidence. Table 1 reports design-weighted yields of 4.50%, 6.84%, 0.50% and 0.69% for Fine News, Infini-News, RefinedWeb and FineWeb-HQ with exploratory intervals. Explain the four independent file–row-group draws and each native English definition.
  - Carry forward. Once the staging frame is fixed, which repeated or late records can contribute usable articles?
  - Pace. Let the exhibit carry individual intervals. Explain why a row group is one sampling draw and why the unit is a physical record.
- **125 words.** A usable article is a canonical copy with evidence of a consistent publication date.
  - Evidence. Explain the seven-day lag and one-day forward tolerance, the earliest canonical capture rule for exact-text and normalized-URL repeats, and the inherited upstream deduplication. Distinguish publisher-reported publication from crawler-observed retrieval.
  - Carry forward. With the version chosen, which text span might identify a firm?
  - Pace. Walk one date example slowly. A later capture records a later observable version even if the stated publication date is earlier.
- **150 words.** Company extraction supplies candidate text spans and dated identity resolution turns some spans into issuer links.
  - Evidence. Identify GLiNER2.5 Small and the span/evidence fields. Explain explicit listing anchors, SEC and Wikidata records, dated ticker/alias checks, ambiguity and abstention. Use a dated ticker example to show why surface recognition alone leaves issuer identity unresolved.
  - Carry forward. An article can name several issuers, so which are the subject of the story?
  - Pace. Explain the mention-to-issuer change of unit before summarizing score detail. Put confidence thresholds and corner cases in Appendix C.
- **105 words.** An article–issuer bridge records multiple links and enables a separate rule for company focus.
  - Evidence. Each accepted pair retains evidence and mention count. The configured focus rule requires at least three extracted mentions for that issuer and has no binding relevance filter. An article can count once overall and once for each issuer in a separate issuer panel.
  - Carry forward. What other fields are available for constructing alternative observations?
  - Pace. Distinguish repeating names from validated prominence using one sentence.
- **75 words.** The construction retains model-produced attributes and body representations for evaluations tied to their own assumptions.
  - Evidence. Identify article form, local sentiment or relevance, event windows and fixed EmbeddingGemma body vectors. Use the census for body-vector alignment and refer to the issuer-conditioning pilot separately.
  - Carry forward. Multiple outputs make different samples possible. The next section measures their support and audits their labels.

## `04_empirical_design_and_data.tex` · 670 words

**Question and answer.** Which observations survive, and what is known about their quality? The staged funnel measures support, and audits with separately specified reference units show where measurement errors enter.

- **145 words.** The same coverage threshold admits fewer firms when an article has to be about the linked issuer.
  - Evidence. Read Panel A by distinct capture-cohort ID, then Panel B by issuer and publication year. Explain that the raw issuer count already requires an accepted link, that usable adds the date and canonical-copy rules, and that focused adds the subject proxy. Explain 47 articles in every year 2018–2022 before reporting 94 usable and 57 focused of the same 100 reference firms. Use the broader 6,591-issuer screen to show scope under dated listing and float evidence. Let the panels carry the rest of the counts.
  - Carry forward. Fewer qualifying firms can reflect a useful exclusion or missed subject stories. The independent focus audit separates those possibilities at the article–issuer level.
  - Pace. Pause at the switch in denominators. The two panels answer different questions and cannot be read as one percentage funnel.
- **170 words.** Link validation shows high precision on accepted extracted mentions, while the focus screen trades subject recall for higher precision.
  - Evidence. The seed-43 sample is independent of linker decisions and its blinded model judges see candidate text and neutral lookup. Define precision over accepted extracted-span links and recall over judged linkable extracted spans. Report 96.8% precision and 70.8% recall with intervals. Separately, on 183 articles with 65 reference-positive issuer pairs, show end-to-end precision from 31.9% to 66.1% and subject recall from 92.3% to 56.9%. Treat false negatives as foregone study support and distinguish membership counts from reference performance.
  - Carry forward. The sampling unit matters just as much when validating other model fields.
  - Pace. Define an extracted-span verdict and a subject-issuer verdict separately before giving the numbers.
- **100 words.** The metadata audits identify when form and event labels need corroboration before they can define a sample.
  - Evidence. Seed-46 blinds predictions from judges on three frames of 400 sampled units each. Use the gap in press-release prevalence to explain why uncorrected form labels would distort a publisher-level composition estimate. Use 23.6% transaction recall to explain why an event-label gate would miss judged events. Put detailed denominators, class breakdowns and judge agreement in Appendix B.
  - Carry forward. Financial applications can choose validated or direct evidence according to their own unit.
- **110 words.** Monthly article shares and bank-pair counts exercise different levels of the observed text.
  - Evidence. Define a publisher-month as an eligible-article denominator and a bank-pair observation as two mapped banks appearing in the same article in a declared week. Table 3 supplies analysis-specific sample sizes.
  - Carry forward. A return study goes from entities observed during a week to a signal that must exist before part of one session.
  - Pace. Explicitly count a multi-bank article once per unordered pair and explain why it can contribute several pairs.
- **145 words.** The firm-session design requires both a timely captured body and enough issuer signals to form an active portfolio leg.
  - Evidence. Establish the previous-close to 09:00 New York publication window, capture between publication and the cutoff inclusive, and distinction between close-to-open reaction and open-to-close drift. Give a late capture example for NLP readers, then define earliest eligible prediction per issuer-session, two securities per active leg and zero-leg evaluated sessions. Explain that the encoder is fixed and retrospective and that its pretraining overlap is unknown even when fitted labels precede evaluation.
  - Carry forward. With each denominator and its timing established, compare the financial measurements in order of evidence requirements.
  - Pace. Slow down at the event-time and trade-time join before exposing the reader to portfolio returns.

## `05_results.tex` · 860 words

**Question and answer.** What do the reconstructed samples support? Contemporary tracking can be compared on a common calendar, pair counts depend on observed publisher coverage, and recovering clocks expands the portfolio sample available for a drift test.

- **140 words.** On a common calendar, the captured-article EMV tracker supports a direct comparison of contemporaneous VIX fit.
  - Evidence. Table 3 uses 675,234 eligible articles across four hosts and 49 months. Give R² 0.515 versus 0.647 and paired six-month block difference interval [−0.215, +0.110]. Cite the July 2025 benchmark and distinguish the original archive rerun from the CCFinance comparison on common outcomes.
  - Carry forward. How much does this gap depend on the same calendar's large volatility episodes and which publishers cover them?
- **115 words.** Early-pandemic months and the publisher basket affect how broadly the observed fit difference can be read.
  - Evidence. Removing March–April 2020 narrows the VIX gap from −0.132 to −0.041. Name the publisher sensitivity and leave omission values to Appendix E. The paired interval spanning zero supports a comparison on this calendar with uncertain ordering.
  - Carry forward. When the publisher mix changes, the coverage question extends from counts per publisher to which relationships are observed between entities.
  - Pace. Explain that both trackers face the same omitted months and that historical fit is descriptive.
- **150 words.** The direction of the connected-pair change depends on which sources supply the bank co-mentions.
  - Evidence. The July 2023 CEBRA manuscript reports 210 to 172 pairs. The mapped CCFinance sample gives 177 to 242 and the Reuters-only case 50 to 35, with 33 of 34 nodes mapped in the comparison. Establish bank-pair count before edge weight and state that a co-mention is a measure of news association.
  - Carry forward. Does the increase persist after holding publisher quotas and volume fixed?
- **145 words.** The bank-pair increase is smaller under the narrower common support required for fourteen weeks, and the extended draw range includes zero.
  - Evidence. Six-week matched result +56.3 connected pairs [5, 83] with 682 stories per week. The 14-week extension fixes 32 mapped nodes and 158 stories per week and estimates +19.1 [−25, 59]. Explain that calendar, roster and publisher quotas change together. Table A8 carries pair weight, Nasdaq support, quotas and placebo ranks.
  - Carry forward. Matching bank stories tests how publisher support shapes observed relationships during a week. The return exercise asks a separate question about whether timely issuer signals can form legs before a session opens.
  - Pace. Put each range beside its design and identify it as variation across story draws. Treat the result as evidence for reporting support and sensitivity to the chosen week and roster.
- **155 words.** The fixed overnight sample supports a retrospective drift test with sparse portfolio legs.
  - Evidence. Two publisher feeds, 996 bodies and 171 issuers, fixed body vectors, Yahoo bars and rolling past-label fits reproduce a selected Table 8 design of arXiv v6 using a different sample. Of 277 evaluated days, 42 have both legs and 123 have neither. Mean gross drift −10.15 bp per evaluated day has a 21-session block interval [−25.2, +4.2] conditional on saved predictions.
  - Carry forward. Does recovering earlier publication markers increase the number of usable days?
  - Pace. Use the leg definitions from §04. Report evaluated days and leg support before interpreting the mean or discussing the clock refit.
- **155 words.** Recovering explicit first-publication clocks expands two-leg coverage, with a negative drift point estimate after refitting.
  - Evidence. Lead with 42 to 110 both-leg days and 277 to 340 evaluated days, then report −7.73 bp after refitting. Keep the versioned +11 bp MiniLM headline reference beside the different sample and input design. Appendix E carries parser counts, title/body probes and execution costs.
  - Carry forward. The applications establish which eligibility decisions to record when reusing the pipeline.
  - Pace. Give the improved support before its new estimate. Note that refitting changes training and evaluation panels where the difference is interpreted.

## `06_conclusion.tex` · 230 words

**Question and answer.** What does a prospective user take away? Choose the observation whose construction the available capture, identity and timing evidence can sustain.

- **115 words.** An eligibility report is part of a financial news result because it shows which claims the observed sample can support.
  - Evidence. Synthesize the progression from monthly denominators to joint entity coverage and timely firm-session exposures. Use the coverage screen as guidance on what to report alongside a new analysis. Relate each restriction to the choice of observation.
  - Carry forward. Once the intended sample is specified, what inputs does its reconstruction require?
- **115 words.** Reuse starts from the archived inputs and a pinned recipe, with access to frozen dependencies recorded separately.
  - Evidence. Public upstream archive paths and terms, private code and processed artifacts, unverified anonymous access to the staging revision and external data requirements. Identify the appendix manifest and scoped reproduction commands. Keep author-identifying paths out of the anonymous build.
  - Carry forward. The appendices begin with source lineage so an auditor can inspect the pipeline in the order its evidence is produced.

## `07_appendices.tex` · 2,700 words

**Question and answer.** What does an auditor need to inspect each decision and rerun the reported work? Use the frozen sources, evaluation populations, outputs and permissions recorded with each stage.

### A. Corpus lineage and source pilot · 300 words

- **150 words.** The corpus manifest connects each staged article ID to a frozen upstream selection and checksum-verified files.
  - Evidence. Table A1 acquisition portion, exact upstream and staging revisions, hostname manifest, 168 shards, 984 row groups and restored counts. Explain how the frozen stage verifies the restored content and how a fresh query changes physical layout.
  - Carry forward. The separate source-sampling draw lists show how the historical filter behaves beyond that one staging snapshot.
- **150 words.** The source pilot can be reconstructed from manifests specifying frames, draws, probabilities and records counted.
  - Evidence. Table A1 source portion, native language definitions, estimated English and matched totals, observed counts and weighted yield, Hansen–Hurwitz weighting and t intervals with three degrees of freedom.
  - Carry forward. After selection, what error arises when a text model reads the observed record?
  - Pace. Explain file probability and conditional row-group probability before the expansion estimator.

### B. Extractor and metadata audits · 500 words

- **135 words.** The paired Stanza–GLiNER experiment isolates organization extraction on selected financial leads under a shared exact-company-span definition.
  - Evidence. Table A2, 40 leads equally sampled by publication year 2019–2023, 118 reference spans, eight empty leads, ten independently repeated leads with exact agreement on 26 spans. Identify Codex references, OntoNotes ORG mapping and the pinned extractors. Explain why a missed company can remove a network co-mention.
  - Carry forward. With reference and matching defined, compare exact-span errors.
- **120 words.** GLiNER has higher observed micro-F1 in the micro-benchmark, with a paired interval compatible with either ordering.
  - Evidence. Stanza 34.3% precision, 58.5% recall and 43.3% F1 versus GLiNER 46.3%, 58.5% and 51.7%. Paired difference +8.43 F1 points [−1.76, +18.76]. Use the verified runner's year-stratified bootstrap and representative boundary/organization errors. Compare to Stanford's published all-class context using its stated task.
  - Carry forward. Once candidate spans exist, how are other article, mention and window fields checked?
  - Pace. Separate selected-corpus company span accuracy from published benchmark scores before interpreting the gap.
- **125 words.** The metadata confirmation design measures different target properties at article, mention and window levels.
  - Evidence. Table A3 and `validation.json` stratification, seed-45 development exclusions, seed-46 frames of 400, Luna reference, and 100 repeated or independently audited units per frame. State inverse-inclusion weights and article-cluster multiplier intervals.
  - Carry forward. A shared metadata label threshold has different empirical consequences by use.
- **120 words.** The audit identifies which model fields most need corroboration in a research design.
  - Evidence. Table A3 reference-positive counts, press-release precision and recall, weighted prevalence under each labeler, local relevance and sentiment disagreements, and windows with missed event families. Record relevant throughput and distinction between synthetic diagnostics and confirmation samples.
  - Carry forward. Do dated issuer links and focus criteria preserve enough of the validated study population?

### C. Identity, focus and coverage · 450 words

- **140 words.** The linker evaluation separates accepted mention identity from whole-article subject recovery.
  - Evidence. Table A4, sampling by alias structure rather than predicted identity, neutral lookup, seed-43 held-out sample, weighted intervals and distinct denominators for mention and article-pair estimates. Give agreement between repeat and audit judges.
  - Carry forward. Targeted confirmation measures recovery and anchor behavior where the broad sample has little support.
- **150 words.** The anchor and decorated-name audits test specific linkage evidence and reveal the remaining historical ambiguity.
  - Evidence. Table A4 continued, 294/300 anchor agreement and 300/300 new pairs in their respective samples. Give form mix and the six separately checked Nasdaq-prefix records, name normalization, unresolved or ambiguous examples and full-corpus alias-prior limit.
  - Carry forward. With identity and focus rules distinguished, examine the resulting coverage by year and issuer.
- **160 words.** Yearly support changes as recorded articles must be consistently dated, canonical, issuer-linked and focused.
  - Evidence. Table A5 capture-year funnel, publication-year issuer profile, evidence from dated listing and float records, retained zero-count members, fixed roster and focus threshold. Use the three-mention and relevance-only checks to show the trade-off.
  - Carry forward. Coverage tells us which bodies are available. The next audit asks whether their vectors preserve the information needed to distinguish issuers.
  - Pace. Mark the switch from distinct ID totals to issuer-specific article counts again where the appendix table changes panels.

### D. Vectors and issuer conditioning · 350 words

- **110 words.** The production body-vector census checks that every frozen article ID can be joined to a valid vector.
  - Evidence. Table A6 provenance row, pinned model and image, 2,048-token limit, 768 FP16 coordinates, norms, nonblank texts and a cache restore verifying 985 files.
  - Carry forward. A valid body vector can be reused for multiple issuers. Can it distinguish their accounts within the same body?
- **130 words.** The paired pilot suggests issuer-specific sentences can preserve directional information for selected stories.
  - Evidence. Table A6 eligibility funnel 150 to 18 primary-judge eligible to 16 fit across encoders, eight audit-eligible stories, paired masking rule and arm counts by encoder. Explain that the primary and audit denominators fall below their prespecified minima.
  - Carry forward. Do the same features survive a new deal story or a controlled swap of roles?
- **110 words.** Cross-story retrieval and role swaps identify limitations of firm conditioning on the tested samples.
  - Evidence. Acquisition pilot 38 directional stories from 80 sampled, 19 independent deal pairs and −6.6 percentage-point primary gain with paired interval. Give the shared-sentence role-swap evidence and scope of the 25-story pooling pilot.
  - Carry forward. A financial test can use validated article vectors and explicit article or session selection, with the study-specific assumptions inspectable below.

### E. Study details and sensitivities · 800 words

- **140 words.** The EMV archive rerun and common-calendar comparison answer different replication questions.
  - Evidence. Table A7, archived six monthly specifications, exact Mendeley v1 archive, original and substituted dictionary/populations, 196 observed publisher-month cells, calibration through December 2022 and shared FRED outcomes.
  - Carry forward. Quantify how common-calendar fit changes with publisher and month support.
- **125 words.** EMV fit depends on the publisher basket and the influence of the early-pandemic months.
  - Evidence. Table A7 paired VIX and realized-volatility intervals, 49 versus 47 months, leave-one-host variants and fixed 40-month calibration including the omission of Forbes. Explain shared calendar block resampling.
  - Carry forward. A bank-network comparison uses the same idea of common publisher support, but the quantity of interest is observed co-mentions.
- **140 words.** The bank bridge converts dated issuer links into connected bank pairs under a declared roster and syndication rule.
  - Evidence. Table A8 CEBRA mapping and reference windows, foreign-parent proxies and missing node, story grouping, original sample and 682-story matched design. Use the appendix prose to explain the matching rule and show pair-weight results rather than restate the main connected-pair values.
  - Carry forward. Can identical quotas be preserved over more comparison weeks?
- **135 words.** The fourteen-week bank extension buys more historical comparisons by restricting the fixed bank roster and common publisher quotas.
  - Evidence. Table A8 extended portion, 32 mapped nodes, 158 stories per week, 14 hosts, seven comparisons, both January–April draw ranges crossing zero and descriptive historical ranks. Explain the influence of losing Nasdaq and why draw ranges describe matched-story variation.
  - Carry forward. Overnight research imposes an additional requirement within each session.
- **135 words.** The overnight eligibility ledger shows why time evidence, security joins and portfolio support must be checked separately.
  - Evidence. Table A9 reference versions, capture and first-publication values, article and issuer-session counts lost at each gate, focus/novelty and price screens, 996 baseline versus 1,939 expanded bodies, rolling fits and leg counts. Document the archived Yahoo inputs and CRSP substitution. Keep the principal drift estimates and encoder caveat in the main discussion.
  - Carry forward. With the baseline sample fixed, which changes can be attributed to representation or imposed cost assumptions?
- **125 words.** Paired title/body probes and imposed cost scenarios test sensitivity on the same eligible calendar.
  - Evidence. Table A9 paired MiniLM and Gemma titles and same Gemma body inputs on 996 articles, paired 21-session block contrasts and 277 evaluated days. Show how assumed entry and exit costs depend on active legs and retain zero-leg days.
  - Carry forward. The study ledgers identify exactly which artifacts and inputs an auditor must obtain.

### F. Access and reproduction ledger · 300 words

- **150 words.** Access to an upstream archive and rights to its constituent documents are recorded per artifact.
  - Evidence. Table A10, CC-News terms, Infini-News derived metadata and bulk text terms, Fine News code terms and publisher body rights, both public author archives and separate proprietary data dependencies. Distinguish the Apache-2.0 project code license from upstream rights.
  - Carry forward. With access established, which exact inputs and commands reproduce the displayed evidence?
- **150 words.** The reproduction ledger identifies the revision, required permissions and command for each reported stage.
  - Evidence. Table A10, revision and hash checks, pinned environment, frozen acquisition, local/private DVC dependencies and research outputs. Include the documented `just dvc repro` routes at the level reproducible with restored inputs. Identify exact staging access as unverified externally and preserve anonymous artifact references in FinFM.
  - Carry forward. End with the practical reconstruction sequence from authorized inputs to the paper's tables.

## Budget reconciliation

| File or appendix subsection | Paragraph targets | Total prose words | Estimated pages, FinFM / arXiv |
| --- | --- | ---: | ---: |
| Abstract | 170 | 170 | 0.30 / 0.38 |
| Introduction | 110 + 125 + 115 + 80 | 430 | 0.63 / 1.00 |
| Literature review | 100 + 135 + 135 | 370 | 0.50 / 0.83 |
| Methodology | 120 + 115 + 125 + 150 + 105 + 75 | 690 | 1.20 / 1.95 |
| Empirical design and data | 145 + 170 + 100 + 110 + 145 | 670 | 1.33 / 2.13 |
| Results | 140 + 115 + 150 + 145 + 155 + 155 | 860 | 1.66 / 2.51 |
| Conclusion | 115 + 115 | 230 | 0.34 / 0.52 |
| **Technical content, including front matter** | | **3,420** | **6.24 / 10.00** |
| A. Corpus lineage and source pilot | 150 + 150 | 300 | 0.85 / 1.25 |
| B. Extractor and metadata audits | 135 + 120 + 125 + 120 | 500 | 1.45 / 2.15 |
| C. Identity, focus and coverage | 140 + 150 + 160 | 450 | 1.25 / 1.85 |
| D. Vectors and issuer conditioning | 110 + 130 + 110 | 350 | 1.05 / 1.55 |
| E. Study details and sensitivities | 140 + 125 + 140 + 135 + 135 + 125 | 800 | 2.10 / 3.20 |
| F. Access and reproduction ledger | 150 + 150 | 300 | 0.80 / 1.20 |
| **Appendix content** | | **2,700** | **7.50 / 11.20** |

Step 05 moves 60 prose words from results to empirical design and data. The technical reserve is 0.76 page in FinFM and 1.00 in arXiv. The references and back-matter reserves retain the Step 03 estimates.
