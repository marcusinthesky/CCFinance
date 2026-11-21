# Overnight article-body return probes

This public-data analogue of López-Lira and Tang's overnight embedding
experiment fits separate rolling models for the close-to-open reaction and
open-to-close drift. It uses existing 768-coordinate EmbeddingGemma vectors
of captured CCFinance bodies. The authors use MiniLM and OpenAI embeddings
of RavenPack-matched headlines and CRSP prices. We verified the protocol
against `Train_Embeddings_UNIFIED.py`, `02_PrepareCRSPDaily.R` and
`make_embedding_longshort_summary.R` in archive version 2. The archive ZIP
has SHA256
`ba382d1ba1d747e6d145ea4637feac21493c6cba76cdfe980a2f23d30b8e2e27`.
[Paper §4 and §7.4](https://arxiv.org/html/2304.07619v6),
[replication archive](https://data.mendeley.com/datasets/f39x226htv/2).

## Event eligibility

- Business Standard and Mint Lounge carry supported first-publication lines
  in Indian Standard Time. We parse those lines in the captured bodies and
  retain the verbatim evidence, timezone, parser revision, UTC publication and
  capture clocks, source text hash and article ID. A last-updated line cannot
  substitute for the first-publication line. The observed body can include
  updates made by capture time.
- Publication must follow the preceding exchange close and precede 09:00 New
  York time. Capture must fall between publication and the cutoff, inclusive.
  [The session calendar](sessions.csv) includes the December 31, 2020
  preceding-close anchor, holidays and 13:00 early closes.
  [NYSE 2021–23 calendar](https://ir.theice.com/press/news-details/2020/NYSE-Group-Announces-2021-2022-and-2023-Holiday-and-Early-Closings-Calendar/default.aspx),
  [NYSE 2022–24 calendar](https://ir.theice.com/press/news-details/2021/NYSE-Group-Announces-2022-2023-and-2024-Holiday-and-Early-Closings-Calendar/default.aspx).
- We start with linked operating issuers and effective ticker records for the
  NYSE, NYSE American and Nasdaq, rejecting concurrent unresolved classes.
  For a mapped ticker with unknown start date, a CCFinance link to at least
  one usable article published in 2017–20 and captured before January 2021
  establishes eligibility for the coverage-based subset. The public registry
  has incomplete class and listing histories. The price join also requires a
  USD equity response for the symbol and respects available first-trade and
  listing dates. This universe approximates published CRSP share codes 10–11.
  Of the 1,104 priced rows, 270 use the coverage fallback.
- The captured article must be canonical, consistently dated, nonempty and have
  a successful extraction status. The issuer must pass the link threshold of
  0.5 and have at least three extracted mentions, with relevance and offset
  fields retained. Completeness and dominant-entity relevance are unverified
  proxies. The title movement screen matches phrases like “shares fall” without
  a causal connector, and flagged ten rows, all excluded earlier in the funnel.
- Novelty requires no prior exact normalized title for the issuer in the 90
  preceding days among usable CCFinance captures available at the event. This
  screen removes eight rows. For same-session stories from an issuer, we remove
  subsequent headlines with normalized Optimal String Alignment similarity
  greater than 0.6, removing four additional rows. This implements the
  within-session similarity rule. The 90-day exact-title proxy misses different
  headlines about the same event and earlier events outside the archive.
  RavenPack's relevance score of 100 and event-similarity measure cannot be
  matched at the article level. [Paper §4](https://arxiv.org/html/2304.07619v6#S4).
- The sensitivity sample also requires a dated issuer name or alias to occur
  in the headline. Its classifiers still use body vectors.

The event stage found 6,196 timely articles, 3,135 from Business Standard and
3,061 from Mint Lounge. Across their 10,925 article–issuer links, 8,829 failed
the focus screen, 505 had ambiguous classes and 385 had an ineligible issuer
type. Twelve more rows were repeats. All 1,194 remaining rows had valid body
vectors. The price join dropped 90 rows with unavailable price histories.
The resulting panel has 1,104 rows, 996 distinct bodies and 171 issuers. In the
October 2021 through May 2024 evaluation period there are 1,100 article–security
rows on 402 of 670 sessions, with at most 11 firms per session. That is about
0.85% of the paper's 129,953 overnight firm–headline observations. This gap
combines publisher, timing, relevance, novelty, security and price coverage.
Across the full panel, 634 bodies had multiple linker issuers and 96 bodies
had multiple retained securities, producing 108 vector reuses.

## Multi-issuer spot checks

These five captured bodies illustrate why repeated mentions may be informative
for several issuers, or may reflect incidental comparisons. The UUIDs are the
repository article IDs with the surrounding `<urn:uuid:…>` syntax removed.
The checks illustrate proxy behavior and provide no error-rate estimate.

| UUID | Included tickers | Reading of the captured account |
| --- | --- | --- |
| `22e24cfe-e57a-4cd4-97c9-bc231b4c8cf0` | INTC, QCOM | The same US export-license action directly concerns both companies. |
| `98aa522d-2a79-40b3-ad77-7891b2476fa8` | GAP, TPR | Gap is the defendant and Coach is the plaintiff brand under Tapestry. |
| `03e04b44-e8e2-4f6c-a634-0e2b3fce0985` | DELL, HPQ, MSFT, QCOM | The launch involves Microsoft and Qualcomm alongside computer makers with different roles. |
| `c8ca77ec-5c44-4fad-8124-89f13c05f204` | NVDA, TSLA | The story mainly concerns Tesla's autonomous-driving plans. Nvidia appears in the discussion of computing hardware. |
| `5dfb3009-d941-465e-bae7-4ebb6840e67b` | NVDA, WMT | The Walton family's fortune is a comparison. The news concerns Nvidia's performance and Huang's wealth. |

## Prices and return definitions

The [fixed request list](price-symbols.csv) contains 350 symbols from price
coverage reconnaissance. The production request manifest has 206 symbols over
1,071 required security/session pairs. The frozen Yahoo chart responses
include HTTP or provider failures where available, split ratios and cash
dividends. Their ledger records URL, per-response retrieval UTC and SHA256.
The archived timestamps were recovered from the original response file
modification times on November 21, 2026. The raw snapshot stage is frozen so
ordinary reproduction reuses its historical responses. The symbol request
list and endpoint permit fresh acquisition at a different vintage:

```bash
just python::run stages raw snapshot-lopez-prices \
  --symbols "$PWD/data/inputs/lopez-lira-tang/price-symbols.csv" \
  --output /tmp/ccfinance-lopez-new-prices
```

Let `P` be previous close, `O` the regular-session open, `C` the close
and `D` the cash dividend on the session. The split-adjusted chart quotes
put `P`, `O` and `C` in comparable units. Drift is `C/O - 1`.
Reaction is `(1 + close-to-close total return) / (1 + drift) - 1`,
where close-to-close total return is `(C + D)/P - 1`. We implement
the formula as `(O-P)/P` for `D=0` and
`[O(C+D)-PC]/(PC)` otherwise to preserve exact zeros where possible.
Splits are recorded as evidence and the bars receive no second split
adjustment. The return proxy covers cash dividends and splits. CRSP captures
additional distributions, historical security actions and delisting returns.
The sample drops absent or invalid bars and refuses to bridge uncertain
ticker boundaries.

- NVIDIA's July 20, 2021 chart records the 4-for-1 split and already reports
  comparable previous close and open of $18.77975 and $18.73 at the snapshot's
  split basis. [NVIDIA split FAQ](https://investor.nvidia.com/files/doc_downloads/doc_faq/08/Investor-NVIDIA-2021-Stock-Split-FAQ-08.9.2021.pdf).
- Apple's February 5, 2021 chart records the $0.205 ex-dividend amount.
  Apple confirms the amount with a February 8 record date.
  [Apple dividend history](https://investor.apple.com/dividend-history/default.aspx).
- Meta's filing confirms the FB-to-META change on June 9, 2022 and the unchanged
  CUSIP. The snapshot has historical bars under META and a failed FB request.
  Conflicting registry rows make the case ambiguous under the production
  screen. The code does not assume that a current ticker's old bars apply
  to a predecessor security. [Meta filing](https://www.sec.gov/Archives/edgar/data/1326801/000132680122000070/may312022-exhibit991.htm).
- Twitter's trading suspension began before the open on October 28, 2022.
  The dated registry ends TWTR on October 27. Yahoo currently returns no
  historical series for the symbol. All nine otherwise eligible Twitter
  rows remain in the price ledger as unavailable.
  [Twitter merger and delisting filing](https://www.sec.gov/Archives/edgar/data/1418091/000119312522272772/d411753d8k.htm).

## Rolling probes and portfolios

Each target uses the sign of its own return, including zero. Scikit-learn
1.7.2 fits logistic regression with LBFGS, ten iterations and seed 42 on
fixed body vectors. The archive floors training at January 1, 2021 and
defines each six-month window relative to the previous month's last day.
We require 100 training rows and two observed classes including the positive
class so its probability can be reported. Labels enter training only after
their session close and before the refit month. Empty test months are
audited and later months can resume. The archive stops when it encounters
its first empty test month. Vector encoding was done with a fixed model
released after the sample, with no release-date filter applied. The time
split covers supervised returns, and potential overlap between archived
articles and encoder pretraining is unmeasured.

For each security and day, the earliest eligible predicted story by
publication time, capture time, then article ID supplies the signal. The
archive retains the first master-table row for each security/day. Each
positive or negative leg needs two securities to contribute its
equal-weighted return. The spread is long return minus the return of the
shorted securities. An evaluated day has at least one valid security
prediction. Zero-leg evaluated days affect the hit rate and mean. Days
without predictions stay in the calendar as unevaluated. Positive
portfolio-return days count as hits. Drift Sharpe uses the sample standard
deviation and an annualizer of `sqrt(252)`.

## Executed results

| Body sample | Target | Fits out of 32 | Evaluated sessions | Both legs | Positive days | Mean return | Drift Sharpe |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| All eligible | Reaction | 20 | 277 | 29 | 23.10% | −0.2610% | |
| All eligible | Drift | 20 | 277 | 42 | 26.71% | −0.1015% | −1.354 |
| Issuer named in title | Reaction | 5 | 88 | 3 | 19.32% | −1.0148% | |
| Issuer named in title | Drift | 5 | 88 | 2 | 26.14% | −0.0833% | −1.078 |

The first planned refit in October 2021 has four training rows. The first
main fit is September 2022 and the first title-named fit is January 2024.
The main cohort has between 100 and 539 rows in fitted windows. The ten-
iteration budget produces 15 reaction and 16 drift convergence warnings,
and five reaction and zero drift warnings in the title-named cohort.

The estimated direction does not support positive reaction or drift
returns on this sample. The means on the paired-leg main-sample days were
also negative, at −0.2340% for reaction and −0.1818% for drift. Sparse legs
and concentrated coverage limit the interpretation. The largest reaction
loss was −41.54% on May 10, 2024 when the probe shorted three stocks
including Novavax, which opened up 124.16% following its Sanofi
announcement. That date contributes about 57% of the summed reaction loss.
Omitting it after inspection still gives a mean around −0.1115%. The gross
daily figures have no trading costs or short-borrow charges. The reaction
measures an overnight move that begins before the strategy observes the
article. [Novavax release](https://ir.novavax.com/press-releases/2024-05-10-Novavax-and-Sanofi-Announce-Co-exclusive-Licensing-Agreement-to-Co-commercialize-COVID-19-Vaccine-and-Develop-Novel-COVID-19-Influenza-Combination-Vaccines).

## Fixed-sample title probes

We encoded the captured titles of all 996 articles in the fixed panel of
1,104 article–security rows. The title projection kept one title per article
with its original ID. Both title encoders returned one valid vector for
every ID. We reused the same 670-session calendar, labels, fit windows,
eligibility rules and portfolio construction. The refit reproduced every
saved body prediction and monthly fit row. Each of the three main
representations produced 20 fits, 846 out-of-sample story predictions,
738 chosen security–session signals and 277 evaluated sessions per target.

Gemma titles used the body encoder's pinned revision, prompt prefix,
2,048-token cap, BF16 GPU build and FP16 storage. The RTX 5060 Ti worker
passed its two startup comparisons with native FP32, with minimum cosine
0.999947. For MiniLM we used the authors' 384-coordinate
`sentence-transformers/all-MiniLM-L6-v2` with an independently pinned
checkpoint. The offline worker reproduces the model's 256-token limit, masked
mean pooling and L2 normalization in FP32. The archive's
`02_MatchPermno.R` removes the literal `Press Release:` and its trailing space, and the pattern
`-[[:digit:]]-` with a leading space before trimming whitespace and passing `clean_headline`
to `03_Generate_MiniLM_Embeddings.py`. Neither pattern appeared in any of
our captured titles and trimming changed none. [Version-two replication archive](https://data.mendeley.com/datasets/f39x226htv/2),
[pinned MiniLM checkpoint](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2/tree/1110a243fdf4706b3f48f1d95db1a4f5529b4d41).

| Representation | Target | Convergence warnings out of 20 | Long-leg days | Short-leg days | Both-leg days | Positive days | Mean return (bp) | Drift Sharpe |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Gemma body | Drift | 16 | 118 | 78 | 42 | 26.71% | −10.15 | −1.35 |
| Gemma title | Drift | 16 | 117 | 67 | 31 | 25.63% | −4.43 | −0.54 |
| MiniLM title | Drift | 17 | 121 | 65 | 34 | 25.27% | −4.69 | −0.66 |
| Gemma body | Reaction | 15 | 58 | 121 | 29 | 23.10% | −26.10 | |
| Gemma title | Reaction | 16 | 58 | 120 | 31 | 22.02% | −22.35 | |
| MiniLM title | Reaction | 16 | 70 | 122 | 40 | 24.91% | −29.01 | |

| Drift contrast | Mean difference (bp) | 95% interval, 21 sessions (bp) | 95% interval, 5 sessions (bp) | Chosen signals reversed out of 738 | Long / short leg availability changed (days) | Daily portfolio sign reversed (days) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Gemma title − Gemma body | +5.72 | [−10.67, +21.39] | [−11.05, +22.82] | 190 | 39 / 49 | 47 |
| MiniLM title − Gemma body | +5.46 | [−9.82, +19.90] | [−9.43, +20.58] | 244 | 37 / 53 | 47 |
| MiniLM title − Gemma title | −0.26 | [−18.32, +17.47] | [−17.29, +16.83] | 206 | 32 / 54 | 41 |

Intervals use 10,000 paired circular block draws with seed 42 over the 438
exchange sessions spanning September 2, 2022 through May 31, 2024. Each draw
preserves zero-leg days as zeros, leaves unevaluated sessions missing, and
averages observed daily differences. The intervals describe this fixed
sample conditional on the fitted models. All three drift means are negative
and every paired interval spans zero. Changing the text or encoder often
changed signals and leg coverage, with limited precision on the mean return
differences. For reaction, Gemma titles changed the mean by +3.76 bp
and reversed 199 of 738 chosen signals versus bodies. MiniLM titles
changed it by −2.91 bp and reversed 263 signals versus bodies. The two
title encoders differed by −6.66 bp (MiniLM minus Gemma) and reversed
226 signals. The published MiniLM strategy reports an overnight reaction mean of +112 bp and hit rate
of 80.15%, and a drift mean of +11 bp, hit rate of 56.57% and Sharpe of 1.42,
on its broader RavenPack/CRSP universe. [Paper Table 8](https://arxiv.org/html/2304.07619v6#S7.T8).

Restore the pinned EmbeddingGemma snapshot described in the
[inference README](../../../infra/inference/README.md). From the repository
root in the pinned environment, download the MiniLM snapshot and run the
report. The launcher checks every listed model file against a committed
SHA-256 manifest before GPU inference.

```bash
HF_HUB_DISABLE_IMPLICIT_TOKEN=1 uvx --from huggingface-hub==1.30.0 hf download \
  sentence-transformers/all-MiniLM-L6-v2 \
  config.json model.safetensors tokenizer.json tokenizer_config.json \
  special_tokens_map.json vocab.txt 1_Pooling/config.json modules.json \
  sentence_bert_config.json \
  --revision 1110a243fdf4706b3f48f1d95db1a4f5529b4d41 \
  --local-dir .runtime/all-MiniLM-L6-v2
just dvc repro report_lopez_title_probes
```

The study report at `data/research/experiments/lopez-lira-tang-title-probes/`
writes model fits, predictions, the paired story and session ledgers, the
summary tables and drift intervals. Changes in long and short legs are
recorded separately. A daily sign reversal requires two nonzero returns of
opposite signs. The portfolio spread subtracts the shorted securities'
return. CSV return units are decimals.

## Reproduction and artifacts

After restoring the frozen sources and body vectors with DVC, run
`just dvc repro report_lopez_portfolios`. Study outputs are under
`data/processed/experiments/lopez-lira-tang-events/`,
`data/processed/experiments/lopez-lira-tang-sample/` and
`data/research/experiments/lopez-lira-tang*/`.

| Artifact | Contents |
| --- | --- |
| `timestamps.parquet`, `ticker_history.parquet`, `events.parquet` | Captured publication evidence and event eligibility |
| `price_requests.csv`, `price_ledger.csv` | Required price keys and provider availability |
| `eligibility.parquet`, `sample.parquet`, `attrition.csv`, `daily_support.csv` | Price/vector joins, filter counts and session support |
| `predictions.csv`, `windows.csv` | Story predictions and every planned monthly fit |
| `reaction.csv`, `drift.csv`, `metrics.json` | Separate economic results, model support and vector reuse |
| `daily_portfolios.csv`, `story_positions.parquet`, `monthly_support.csv` | Daily returns, exposures, story ranks and refit support |
| `portfolio_figure.pdf`, `portfolio_figure.tex`, `portfolio_figure_data.csv` | Cumulative arithmetic return figure with data and plotting source |
