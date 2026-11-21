# Bank co-mention networks in January and April 2020

This CCFinance replication uses the 34-bank, five-group roster in Table 1 of
the authors’ July 2023 manuscript. Table 2 and Figures 2–4 specify the
inclusive January 13–19 and April 13–19 earnings weeks. Section 8 uses both
full calendar months and a Reuters-only source check. The 2022 AEA poster
confirms the earnings-week design and group definitions, but reports
different edge counts. The final journal preview confirms the weekly
co-mention method and the monthly and Reuters robustness checks. The full final tables,
appendix and Factiva tags were unavailable, so the roster and exact windows
are verified against the 2023 manuscript. [2023 manuscript](https://congress-files.s3.amazonaws.com/2023-07/Scida_News_and_Networks_CEBRA2023.pdf),
[AEA poster](https://www.aeaweb.org/conference/2022/preliminary/paper/NfzTsayK),
[journal article](https://doi.org/10.1016/j.jbankfin.2026.107694).

## Historical issuer mapping

[roster.csv](roster.csv) gives each manuscript node and its group in Table 1
order. [crosswalk.csv](crosswalk.csv) records eligible issuer CIKs, the study
dates for each mapping and the relationship to the node. Issuer names and
ticker histories come from the frozen [CCFinance issuer registry](../issuers/README.md).
Join on CIK so historical tickers and ambiguous abbreviations do not determine
identity.

- The baseline maps the 22 domestic holding companies and 11 of 12 foreign
  banking groups. Most foreign groups map through their listed global parent.
  A parent link can refer to activity outside the US intermediate holding
  company (IHC). Santander also has a direct CIK for its US IHC, which is a
  listed preferred-stock issuer in the registry. BNP Paribas has no supported
  issuer or parent CIK in the frozen registry. It stays in the reference
  roster as unresolved.
- Retain BBVA Compass as the manuscript’s node although the Fed removed it
  from the corrected February 2020 stress-test roster and added DWS USA as a
  separate Deutsche Bank IHC. DWS is outside the manuscript roster. In early
  2020 BBVA was still under its Spanish parent. PNC acquired BBVA’s US holding
  company in June 2021. [Fed roster](https://www.federalreserve.gov/newsevents/pressreleases/bcreg20200206a.htm),
  [PNC 8-K](https://investor.pnc.com/sec-filings/all-sec-filings/content/0000713676-21-000071/0000713676-21-000071.pdf).
- Truist uses the surviving BB&T CIK. The SunTrust merger took effect in
  December 2019 before the study windows, so the expired SunTrust issuer is
  excluded. Discover and Credit Suisse Group retain their historical CIKs
  because the Capital One and UBS acquisitions came after the study windows.
  Credit Suisse Group’s historical equity CIK is used for the CS node. The
  separate Credit Suisse AG exchange-traded-note issuer and the alternate
  inactive CS entry are outside the crosswalk. [Truist merger](https://media.truist.com/2019-12-09-BB-T-and-SunTrust-complete-merger-of-equals-to-become-Truist),
  [Capital One acquisition](https://www.capitalone.com/about/newsroom/capital-one-completes-acquisition-of-discover/),
  [UBS acquisition](https://www.ubs.com/global/en/media/display-page-ndp/en-20230612-ubs-credit-suisse-acquisition.html).

## Article and network rules

Use [windows.csv](windows.csv) and the CCFinance publication date on
canonical, consistently dated articles. Find the raw and linker shards by
observed capture month, so an April article captured in May remains eligible.
The upstream staging sample already collapses many MinHash clusters, and the
canonical table removes exact-text and normalized-URL copies. Each remaining
article counts once. Keep all resolved body mentions that map to a study bank
regardless of the company's prominence or article form. Factiva uses
proprietary relevance tags and a corporate family tree, so the CCFinance
approach can include incidental mentions and miss affiliate mentions.

For each article, collapse repeated mentions and multiple mapped CIKs to one
row per bank. The per-window article count for a bank includes singleton
articles and is available in `bank-activity.csv`. Each article mentioning
`k` distinct banks contributes `k(k-1)/2` unordered pair observations.
Sum those observations for edge weights. Report connected-pair counts and
weights separately, against both reference and mapped denominators. Keep
mapped banks with zero articles or zero neighbors in the matrix and show
unresolved banks as blank cells. The off-diagonal counts are symmetric with a
zero adjacency diagonal. Heatmaps use one common linear color scale per
January–April comparison and retain the same roster order.

Following equation (2) of the working paper, descriptive eigenvector
centrality uses the leading unit-length eigenvector of the symmetric weighted
matrix after setting the diagonal to zero. Scores are blank when the largest
eigenvalue is zero or tied, and for unresolved banks. These scores summarize
the observed co-mention network. The paper’s separate negative-sentiment
systemic-risk analysis falls outside this comparison.

## Sensitivities

All variants reuse the four windows. The normalized-headline and
high-bank-count sensitivities were explored during the
[12-bank pilot](../../../.context/plan/replication/feasibility.md).

| Variant | Rule |
| --- | --- |
| `baseline` | Count one pair observation per eligible article. |
| `unique_headline` | Keep one article per nonempty normalized headline per window. Lowercase and collapse non-letter and non-digit runs to spaces. Keep the article with most mapped banks, then earliest publication date and lowest ID. |
| `under_six_banks` | Drop articles with six or more mapped banks as a broad-roundup proxy. |
| `exclude_roundups` | Drop upstream article form `roundup`. |
| `reporting` | Keep upstream article form `reporting`. |
| `reuters_host` | Keep Reuters.com and its subdomains. Republishing on other domains is outside this variant. |
| `direct_only` | Keep domestic holding-company and US IHC links, excluding foreign-parent proxies. |

A normalized-headline match can merge distinct editions or recurring generic
headlines. Treat it as a sensitivity and use the publisher, byline and body
to assess individual cases. Upstream article forms are model labels.

## Reproduction

Run `just dvc repro report_kazinnik_banks` with the upstream artifacts
materialized. The processed stage writes the article-to-bank Parquet bridge
with issuer and mention-span evidence and a publication/capture coverage table.
The research stage writes group comparisons, bank activity and centrality,
pair counts and matrices, two paired SVG heatmaps, coverage by publisher and
bank count, and article IDs for the largest edges and repeated headlines.
See the [results record](../../../.context/plan/replication/tasks/kazinnik-banks/results.md).

## Matched earnings weeks

[matched-weeks.csv](matched-weeks.csv) fixes six Monday–Sunday windows around
JPMorgan Chase earnings releases. It preserves the manuscript's January and
April 2020 dates and pairs the next four releases as July to October 2020 and
January to April 2021. The latter repeats the quarter-of-year comparison.
The dated investor records identify the release in every week.
[JPMorgan Chase 2019–2020 events][jpm-2020] ·
[January 2021][jpm-jan-2021] · [April 2021][jpm-apr-2021]

The follow-up retains all 34 nodes and the same dated links for the 33 covered
nodes. It extends crosswalk entries with an April 30, 2020 end date through
April 30, 2021, only in the follow-up. This treats the issuer-to-node identities,
including foreign-parent proxies, as fixed for these six windows. PNC and BBVA
announced their agreement in November 2020 and closed on June 1, 2021, after
the last window. HSBC announced its US retail divestitures in May 2021, and US
Bancorp completed its Union Bank acquisition in December 2022. Morgan Stanley
closed its E*TRADE and Eaton Vance deals during the follow-up, changing the
business covered by the same listed issuer. The fixed mapping continues to use
the original roster CIKs, without adding those acquired names as aliases. Merger
news can still contribute to co-mentions.
[PNC agreement][pnc-agreement] · [BBVA disposition][bbva-close] ·
[HSBC US announcement][hsbc-retail] · [US Bancorp annual report][mufg-close] ·
[Morgan Stanley strategic update][ms-acquisitions]

Within each week, connect bank articles that share an upstream MinHash cluster,
an exact text hash, or a nonempty normalized headline. Take the earliest
published copy, breaking same-date ties by article ID, as each connected
component's representative. Use its publisher and bank mentions. Within each
publisher host, retain its minimum count of representative stories over all six
weeks. Sample that many stories uniformly without replacement in every week
for 1,000 draws with seed 42. Compare after-minus-before changes in connected
pairs and total pair weight. The sampling ranges describe sensitivity to
subsampling the observed stories. The two non-overlapping placebo changes
provide an empirical rank with limited resolution.

Run `just dvc repro report_kazinnik_matched_weeks`. The report includes
weekly support and network measures, publisher quotas, change distributions
summarized by their means and percentiles, and placebo ranks.

[jpm-2020]: https://www.jpmorganchase.com/ir/events
[jpm-jan-2021]: https://www.jpmorganchase.com/ir/news/2021/jpmc-to-host-fourth-quarter-and-full-year-2020-earnings-call
[jpm-apr-2021]: https://www.jpmorganchase.com/ir/news/2021/jpmorgan-chase-to-host-first-quarter-2021-earnings-call
[pnc-agreement]: https://investor.pnc.com/sec-filings/all-sec-filings/content/0000713676-20-000142/a20201116rlspncbbvausafi.htm
[bbva-close]: https://www.sec.gov/Archives/edgar/data/842180/000084218024000007/R12.htm
[hsbc-retail]: https://www.about.us.hsbc.com/newsroom/press-releases/hsbc-exits-us-mass-market-retail-banking
[mufg-close]: https://www.usbank.com/dam/usbank-2024/en/documents/pdfs/common/2023-USB_Annual_Report.pdf
[ms-acquisitions]: https://www.morganstanley.com/content/dam/msdotcom/en/about-us-ir/shareholder/4q2021-strategic-update.pdf
