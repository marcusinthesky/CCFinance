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
