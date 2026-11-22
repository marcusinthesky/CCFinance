# Paired issuer-linking comparison

The frozen seed-43 confirmation test provides 886 determinate company-mention judgments across 873 articles. Judges marked 578 mentions as referring to eligible listed issuers and 308 as having no eligible issuer. Every system receives the same extracted spans. The reference is model-adjudicated, with dated-security equivalence as in the [existing audit](../README.md). Recall conditions on the extraction step.

| Issuer assignment | Assigned mentions | Correct | Weighted precision | Weighted recall | Weighted F1 | Weighted share assigned |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Unique dated normalized name | 173 | 163 | 99.12% | 42.47% | 59.46% | 16.55% |
| Stanford WikiDict + issuer crosswalk | 49 | 47 | 99.78% | 20.42% | 33.91% | 7.91% |
| CCFinance, prior calendar years | 465 | 435 | 96.66% | 66.18% | 78.57% | 26.45% |
| CCFinance, production | 475 | 444 | 96.81% | 70.83% | 81.81% | 28.26% |

Counts describe the sample. Each determinate test mention receives its stratum's population divided by its labeled test count. Precision divides weighted correct assignments by assignments, recall divides by linkable mentions, and F1 is their harmonic mean. An incorrect issuer for a linkable mention therefore costs both precision and recall. Paired 95% percentile intervals use 2,000 exponential-multiplier draws (NumPy seed 43), sharing article weights across systems and recalibrating totals within each original stratum. The intervals condition on the model reference and registry.

Production minus comparator F1 differences in percentage points are +22.35 [17.10, 28.38] for dated names, +47.90 [40.13, 56.12] for WikiDict plus crosswalk, and +3.24 [1.22, 6.23] for prior years. Full and prior-year production both achieved 99.23% recall among the 173 unique-name cases. Among the 692 mentions with no dated name candidate, weighted recall reached 49.46% for production and 41.24% for prior years. There were 21 mentions with multiple dated name candidates. On the 308 judged ineligible mentions production assigned an issuer to a weighted 0.94%. The candidate groups and eligibility group overlap. [Full subgroup results](metrics.json) · [Paired decisions](predictions.csv)

## Methods and reproduction

- The name baseline takes an exact normalized SEC current name, former name or Wikidata label, requires an eligible listing and valid name on the article date, and abstains unless one CIK qualifies. It is an open finance baseline inspired by Schwenkler and Zheng. Their study used CoreNLP organization spans and a separate CRSP/Compustat matching procedure. [Authors' method](https://wrds-www.wharton.upenn.edu/documents/1125/news.pdf)
- The WikiDict baseline implements CoreNLP 4.5.10's default case-sensitive dictionary branch for supplied organization spans. It takes the last matching dictionary entry in file order and joins its English page title (space/underscore normalized) to the canonical sitelink of a CIK-bearing Wikidata item, then to a unique registry CIK listed on the article date. The 464 mentions with a dictionary title yielded 97 matches to the frozen CIK-bearing sitelink list and 49 dated issuer assignments. Old titles, redirects, missing CIK statements, subsidiaries and registry gaps can suppress matches. We evaluated the dictionary-plus-crosswalk design. The baseline does not run Stanford NER. [Stanford documentation](https://stanfordnlp.github.io/CoreNLP/entitylink.html) · [Pinned implementation](https://github.com/stanfordnlp/CoreNLP/blob/v4.5.10/src/edu/stanford/nlp/pipeline/WikidictAnnotator.java)
- The prior-year replay applies the same production resolution code, same-article context, registry, score threshold (0.5) and direct ticker anchors. It relearns alias eligibility and frequency priors from mentions whose capture and known publication years precede the earlier of the query article's publication and capture years. This conservative cutoff also excludes earlier evidence in the current year. The issuer registry is a frozen retrospective snapshot. The difference therefore measures the choice of prior window and does not isolate look-ahead alone.

Run from the repository root with the frozen coverage, issuer, link and seed-43 inputs restored, using the pinned shell. The main comparison uses the frozen [WikiDict surface results](wiki-pages.csv). The final replay also checks held-out assignments against saved production decisions using the original priors.

```sh
devenv shell -- uv run --project src/python --offline --frozen python src/python/scripts/link_comparison/compare.py
```

To regenerate the WikiDict surface results, extract `edu/stanford/nlp/models/kbp/english/wikidict.tab.gz` from [Stanford's 4.5.10 English KBP model jar](https://repo.maven.apache.org/maven2/edu/stanford/nlp/stanford-corenlp/4.5.10/stanford-corenlp-4.5.10-models-english-kbp.jar). The script checks its SHA256. The [public sitelink snapshot](public-sitelinks.csv) contains 3,127 English Wikipedia page–item pairs retrieved on 22 November 2026 using the following generic Wikidata query. All article mention lookups are local.

```sparql
SELECT DISTINCT ?page ?item WHERE {
  ?item wdt:P5531 ?identifier .
  ?page schema:about ?item ; schema:isPartOf <https://en.wikipedia.org/> .
}
```

```sh
devenv shell -- uv run --project src/python --offline --frozen python src/python/scripts/link_comparison/wiki.py .runtime/link-comparison/wikidict.tab.gz
```
