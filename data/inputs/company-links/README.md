# Company links

`link_company_mentions` ties GLiNER company mentions to US-listed issuers from [issuers](../issuers/README.md). Each mention gets a CIK, a score and its evidence. The dated ticker comes from the issuer tables.

## Method

1. **Anchors.** An explicit US listing within or just after a mention links it with score 1. That means an exchange ticker such as "(NASDAQ: AAPL)" or a Reuters code such as "WMT.N".
2. **Propagation.** Later mentions in the same article inherit the anchored link if they have the same key, or a key the anchored one begins with.
3. **Learned aliases.** Anchor counts across the corpus teach aliases the issuer tables lack. A key needs:
   - at least three anchors;
   - at least 90% of them to one issuer;
   - either to begin one of that issuer's names ("Ford") or to be anchored in at least 0.5% of its mentions.
4. **Candidates.** Aliases are matched after removing a trailing "(TICKER)". They count only if both the alias and the listing were valid on the article date, which is the publication date or else the capture date.
   - **One security, one candidate:** filers that share a ticker on that date are a single candidate.
5. **Scoring.** Each candidate scores `weight × share`.
   - **Weight** reflects how specifically the alias names the issuer:
     - names and learned aliases 1;
     - other aliases and subsidiaries 0.5;
     - bare tickers 0.2.
   - **Same-article boost:** a weaker candidate counts as a name when the same article names or anchors that issuer, so "TSLA" beside "Tesla" scores like the name.
   - **Share** is the candidate's anchor count plus `smoothing × weight`, as a fraction of all candidates' totals.
6. **Ambiguity.** A mention links only if its best candidate holds at least 75% of that evidence. Otherwise it is `ambiguous` and keeps its candidates for audit.
7. **Unresolved.** Mentions without candidates are kept with their key in `unresolved/`.
8. **Self-mentions.** A mention naming the article's own publisher (its domain, or [publishers.csv](publishers.csv)) is flagged `self_publisher`.

`articles/` has one row per article and issuer, with:

- the ticker on that date, the mention count and the maximum link score;
- the maximum GLiNER substantive relevance;
- the link-weighted sentiment vector;
- the first mention's position and the evidence offsets.

## Evaluation

The [paired linker comparison](comparison/README.md) evaluates dated names, Stanford WikiDict with a financial crosswalk, prior-year aliases and the production linker on the same held-out mentions.

The evaluation runs three stages:

1. **`sample_company_links`** draws GLiNER company mentions by seeded hash priority within strata, plus a uniform article sample.
   - **Strata:** key frequency (head, torso, tail) crossed with the number of issuers sharing the alias (none, one, several).
   - **Independent of the linker:** the sample never reads linker output, so one labelled set evaluates every linker version.
   - **Split:** articles fall into a development or a test split by hash. Rules are tuned on development labels and reported on test labels only.
2. **`adjudicate_company_links`** labels the sample through PydanticAI (`codex login` first).
   - **Judges:** the primary model labels every item. The same model is asked again about a share of mentions, and an independent audit model judges another share.
   - **What judges see:** the excerpt and neutral issuer search results for the marked text, never the linker's choice.
   - **Universe:** NYSE, Nasdaq, NYSE American and Cboe listings on the article date. OTC-only and foreign-only issuers count as not listed.
   - **Caching:** every judgement is cached, and failures are recorded rather than retried forever.
3. **`report_company_links`** writes the results.
   - **Correctness:** a link is correct if it names the judged issuer, or the same listed security on that date.
   - **Estimates:** weighted mention and article precision and recall at the operating threshold, with linearized 95% intervals. Article recall is gated on issuers the article is about, and also reported for every issuer it mentions.
   - **Breakdowns:** domain estimates by year and link method, and reliability by score.
   - **Judge reliability:** agreement with explicit tickers, plus repeat and audit-model Cohen's kappa.
   - **Outputs:** gates, a development error table, diagnostics and `summary.tex`.

Rules were chosen on a development sample (seed 42), including after one look at its test split. Reported figures come from a fresh confirmation sample (seed 43, `company_links.seed`). It was drawn and labelled only after the rules were fixed.

These are model-adjudicated labels, not human ones. The report gives the judge-reliability evidence that reviewers need to assess them.

## Known limitations

- **Delisting dates.** SEC listings are current, so delisted issuers rely on Wikidata, which can lack end dates or carry reused tickers.
- **Brand coverage.** Product and brand mentions ("Shark Tank", "Snapdragon") resolve only through Wikidata subsidiaries with at least ten Wikipedia editions.
- **Note-issuing filers.** Filers that list only notes (Credit Suisse AG) can compete with their group's equity. These mentions are usually left `ambiguous`.
- **Context homonyms.** Head keys with a non-company sense, such as KKR the cricket team or Vulcan the rocket, link on name alone. They account for most of the remaining precision loss.

## Explicit-ticker confirmation audit

On the production links at commit `a1b4b9a`, draw 300 mentions whose method is
`anchor`, excluding all article IDs in either seed-43 sample table. Order by
`sha256('44:' || id || ':' || start), id, start` and take the first 300.
The draw covers 300 articles, 215 proposed issuer CIKs and 21 publisher domains.
The primary judge used the existing mention prompt, 750-character context on
each side, neutral issuer search and the configured low-effort GPT-6 Luna model.
Every judgment returned a decision. The operating threshold and dated-security
equivalence rule match the production report.

Agreement was 294/300 (98.0%, exact two-sided 95% interval 95.70%–99.26%).
The fresh sample meets the 98% point-estimate target. The interval includes
agreement below 98%. The earlier 19/20 remains the result for the general
seed-43 sample's anchor subset. These estimates apply to anchor mentions.

Review of the six disagreements found:

- Three links to SentinelOne (S) for mentions of Sprint Nextel, China Bird
  Centro America S.A. and Play Finance 2 S.A. The Sprint excerpt explicitly
  uses the historical ticker S.N for Sprint.
- Two judge lookup misses. The text and reference agree on BJRI for BJ's
  Restaurants and KSS for Kohl's; the judge returned no CIK for either.
- One historical identity disagreement. A 2012 Apache Corp article gives
  APA.N. The linker selected APA Corp, and the judge identified Apache but
  returned no historical CIK.

The [scored mentions](../../../.context/plan/dataset-research/tasks/dataset-requirements/ticker-agreement-seed44.csv)
record the two CIKs and original judgments. All six count as disagreements.

## Recovery of decorated SEC names

Run `link-companies --recover-names --output <fresh-directory>` to evaluate the
candidate on the existing extraction. The fallback checks unresolved spans for a
trailing uppercase ticker, a trailing word “stock”, or a leading “NASDAQ-traded”.
The remaining name must identify a single listed issuer through a current or
former SEC name on the article date. An exchange or ticker in the decoration
must corroborate the match. Recovered evidence carries method `normalized_name`
and full-name weight. The original text and offsets remain available for review.

Evaluate newly accepted article–issuer pairs separately from extra mentions on
an existing link. Confirm precision on a fresh blinded sample before enabling
the option in the production stage.

To reproduce the audit, set DuckDB's `baseline_dir` to the previous DVC output
(`86731bd2364592ce1677d52f0a25723b.dir`) and `candidate_dir`
to the candidate output and run [the audit query](normalized-name-audit.sql)
from the repository root. The blinded judge receives the original marked span,
excerpt, title, publication context and neutral issuer lookup results. The
candidate CIK is reserved for scoring after adjudication.

In the [blinded confirmation sample](normalized-name-confirmation.csv), the
primary judge confirmed 300 of 300 newly accepted pairs (95% Wilson interval
98.74%–100%), including 281 pairs on usable articles. The second judge agreed on all 62 independently assessed pairs.
Trailing tickers accounted for 297 sample pairs and “stock” for three. The
sample contained no exchange-prefix cases; precision for that form is
unmeasured. Judgments measure issuer identity and do not establish company focus.

The full candidate build covered 984 shards and recovered 287,893 mentions.
It added 49,852 accepted article–issuer pairs across 30,916 articles and 3,367
issuers, including 47,808 usable pairs. During 2018–2022 the corresponding
counts were 30,706 pairs, 19,026 articles, 2,695 issuers and 29,131 usable
pairs. The Pricing Perspective roster gained 3,972 pairs within those years.
Its annual raw minimum rose from 25 to 28 and its usable minimum from 24 to 27.
The 47-per-year screen still retained 95 raw and 94 usable firms. The three
Cadence, one Enphase and one IDEXX development cases were recovered.
Across all issuers, 43,087 existing usable pairs crossed the three-mention
cutoff, including 18,792 during the five study years.

Seed-43 held-out mention recall rose from 70.13% to 70.83% and precision from
96.78% to 96.81%. Subject-level article recall stayed at 92.31%. All previously
passing evaluation gates passed again, and explicit-anchor judge agreement
remained 95%. A separate overlap check found no seed-42 development articles
in the confirmation sample.

**Production decision: hold under the predeclared exact-output gate.** Comparison
of every mention found identical span identities, anchor priors, prior issuer
assignments and top-level link scores. No accepted pair was lost. On 151
existing mentions the scores in the stored candidate list differed by at most
6.94e-18. Candidate identifiers and order agreed throughout. Those
floating-point differences fail exact row equality despite having no effect on
the threshold or chosen issuer. This was the initial hold decision.

**Release decision.** The production stage enables decorated-name recovery.
Rebuilding the 54 affected shards with recovery disabled produced 140
alternative-score differences against the historical baseline and 149 against
the candidate on existing mentions. Both comparisons had a maximum absolute
difference of 6.94e-18. Issuer assignments, candidate IDs and ordering,
top-level scores, and threshold decisions matched exactly. The release check
requires those exact matches and permits an absolute difference of at most
1e-16 only in scores within the stored candidate list.

Context review confirmed all six newly linked Nasdaq-prefix pairs: IDEXX
Laboratories, Apple, Baidu, NICE, and two Freedom Holding records carrying the
same headline. This checks identity across six records and five issuers.

Run [the release comparison](check-name-recovery.sql) for each corresponding
pair of mention shards using the DuckDB variables `baseline_shard` and
`candidate_shard`. Each comparison must report zero violations.

## Remaining link candidates

An exploratory scan of unresolved GLiNER keys after decorated-name recovery
found two further sources of coverage. Counts below exclude article–issuer
pairs that already have an accepted link (score at least 0.5).

| Candidate evidence | All years | Pricing Perspective roster, 2018–2022 |
| --- | ---: | ---: |
| Share-class suffix and a unique matching SEC issuer name | 802 | 13 |
| Google Pay mention without an Alphabet link | 2,813 | 1,692 |
| Instagram mention without a Meta link | 43,777 | 20,637 |

The share-class scan stripped terminal “class A/B/C”, “cl A/B/C” or
“A/B/C shares”, then a trailing legal form, and checked the date bounds of
current and former SEC names. It found 123 issuers across 791 articles.
A production rule should also corroborate the security class against a dated
listing. The 396 articles saying “Berkshire Hathaway B shares” without an
accepted Berkshire link are a concrete validation set.

The brand counts are candidates for an issuer link, not estimates of article
focus. Among six usable 2018–2022 examples per brand, chosen by ordering
article IDs by SHA256 of “50:” followed by the ID, Google Pay appeared in
a Mastercard partnership as well as lists of payment services. Instagram
appeared in product coverage and in accounts of celebrities posting online.
Evaluate brand ownership on the article date and score issuer identity and
subject role separately before using those links in the coverage panel.
