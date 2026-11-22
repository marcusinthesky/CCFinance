# Sentence sentiment and issuer coreference

The comparisons use the Stanford CoreNLP 4.5.10 English distribution and keep the production GLiNER extraction, company links and thresholds fixed. Both sets of reference labels come from language models. The two exercises use different units and independent archived samples.

## Sentiment

| Weighted measure on 358 positive, negative or neutral references | GLiNER mention | Stanford sentence |
| --- | ---: | ---: |
| Positive precision / recall | 46.09 / 72.68% | 49.39 / 40.33% |
| Negative precision / recall | 56.41 / 56.04% | 32.75 / 49.54% |
| Neutral precision / recall | 52.38 / 18.86% | 42.14 / 35.78% |
| Three-class macro-F1 | 46.79% | 40.84% |
| Opposite polarity | 8.38% | 10.73% |

The GLiNER-minus-Stanford differences are +5.95 percentage points for macro-F1 (95% interval −1.33 to +13.98) and −2.35 for reversals (−6.97 to +2.02). Stanford returned a sentence score for 399 cases and abstained on one long sentence. The directional subset covers a weighted 88.77% of the sample. Mixed (5.89%), unassessable (3.84%) and invalid targets (1.50%) account for the rest under the original judge.

On the archived GPT-6.1 Terra audit, 66 of 100 references were directional; GLiNER and Stanford scored 50.06% and 28.02% weighted macro-F1. The fresh GPT-6.1 Terra check agreed exactly with the original judge on 10/40 labels and marked 23 spans invalid. On the 14 fresh Terra directional cases GLiNER matched 8 and Stanford matched 5. The small subset and differences in target validity limit interpretation. All figures concern local extracted mentions. The frame contains one sampled mention per article, so it cannot directly measure within-sentence discrimination between two adjudicated companies.

The seed-46 confirmation frame supplies 400 original company-mention offsets. Stanford's default English tokenizer and sentence splitter first locate the sentence containing the entire marked span. The English constituency parser and sentiment model label its root. Positive intensities collapse to positive, negative intensities to negative, and neutral is retained. Every company in the same sentence receives the same Stanford score. A missing containing sentence or one longer than 200 tokens is scored as an abstention. Java UTF-16 offsets are converted from the frozen Unicode offsets before matching.

The shared directional comparison conditions on primary judgments of positive, negative or neutral. An abstention, mixed or unassessable prediction misses the reference class. Reversals count positive-to-negative and negative-to-positive errors among all directionally judged units, including neutral. Class metrics use the original population-to-draw weights. Paired 95% percentile intervals use 2,000 article-level exponential multiplier draws with seed 46 and fixed stratum totals. The full reference distribution describes cases outside the three-label task.

A separate GPT-6.1 Terra pass labels 40 units selected by the 40 lowest hashes of the sorted-frame case tag with prefix `human-71:`. The prefix predates the decision to use a model reviewer. Terra saw only the marked name and up to 750 characters on either side, with a blank response field. Its rubric required a named business span, investor-facing consequences for that business, and one of positive, negative, neutral, mixed, not assessable or invalid span. Agreement on those 40 cases is descriptive. The original confirmation labels remain frozen. [Paired observations](sentiment-pairs.jsonl) · [Class estimates and confidence intervals](sentiment.json) · [Stanford sentiment](https://stanfordnlp.github.io/CoreNLP/sentiment.html)

## Coreference

| Three-mention rule | Subject pairs recovered / predicted | Precision | Recall of 65 subjects | F1 |
| --- | ---: | ---: | ---: | ---: |
| Named mentions | 37 / 56 | 66.07% | 56.92% | 61.16% |
| Named mentions plus chain references | 44 / 68 | 64.71% | 67.69% | 66.17% |

Chain expansion added seven subjects and five incidental issuers. The paired recall difference was +10.77 points (95% interval +3.92 to +19.61), precision −1.37 (−6.17 to +3.35), and F1 +5.01 (+0.11 to +11.52). An independent GPT-6.1 Terra review, blind to the subject labels, judged 28 of the 42 additional heads on the 12 newly qualifying pairs to refer to the anchored issuer. Counting only those references retained seven of the 12 pairs, six of which were judged subjects. This last calculation uses adjudication after inference and describes error mechanisms. [Antecedent judgments](terra-antecedents.jsonl)

The seed-43 focus test contains 183 articles that already had a GLiNER company detection. Statistical CoreNLP coreference uses the same body excerpt available to the reference judge, up to 12,000 characters. The published threshold counts named mentions for each accepted issuer link. For the expanded rule, a chain qualifies when its proper-name heads overlap accepted evidence for exactly one issuer (the full head must lie in the marked span). Each additional distinct nominal or pronominal head in that chain counts once if it does not overlap an extracted company name. The day-specific issuer-equivalence and subject judgments match the production focus audit. The historical article counts remain the baseline on truncated excerpts. This tests an addition to the three-mention rule on already linked pairs.

Paired intervals resample the 183 articles with replacement 2,000 times (seed 43) and recompute precision, recall and F1. The chain labels from Stanford are model outputs. Subject labels establish whether the company was a subject; reviewing each added head separately checks whether the chain assigned it to the right issuer. [Paired issuer decisions](focus-pairs.jsonl) · [Evidence offsets](added-heads.jsonl) · [Focus metrics](focus.json) · [Stanford coreference](https://stanfordnlp.github.io/CoreNLP/coref.html)

## Reproduction

From the repository root, use the pinned environment and restore the frozen raw articles, extracted metadata and company-link confirmation artifacts. Unpack the [official distribution](https://downloads.cs.stanford.edu/nlp/software/stanford-corenlp-4.5.10.zip) under `.runtime/corenlp-audit`. The archive SHA256 is `76a04089069dad21176c02881f46e07c19ca148b71c8581de2b5b2e2855e042e`. The original run used OpenJDK 21. CoreNLP inference runs locally. Source bodies are restored into the ignored runtime directory.

```sh
work=.runtime/corenlp-audit
scripts=src/python/scripts/corenlp_audit
uv run --project src/python --offline --frozen python "$scripts/prepare.py"
javac -cp "$work/stanford-corenlp-4.5.10/*" -d "$work" "$scripts/Audit.java"
java -Xmx5g -cp "$work:$work/stanford-corenlp-4.5.10/*" Audit sentiment "$work"
java -Xmx7g -cp "$work:$work/stanford-corenlp-4.5.10/*" Audit coref "$work"
cp data/inputs/article-metadata/corenlp-comparison/terra-sentiment.csv "$work/"
uv run --project src/python --offline --frozen python "$scripts/sentiment.py"
uv run --project src/python --offline --frozen python "$scripts/focus.py"
```
