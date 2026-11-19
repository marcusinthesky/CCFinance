# Validating GLiNER metadata

The extraction benchmark describes model outputs across 10,000 articles. The validation experiment estimates agreement with blinded model judgments in the usable Fine News corpus. Its units are whole articles for journalistic form, extracted company spans for local relevance and investor-facing sentiment, and model input windows for multi-label event families. Overlapping windows represent separate prediction opportunities.

## Sampling and judging

Seed 45 draws 30 development units from each frame. Seed 46 excludes those articles and selects 400 units per frame. For form and sentiment, half of the allocation is proportional to the predicted class size and half is divided equally across classes, subject to available units. For events, half goes to windows below 0.5 on all families and half to positive windows stratified by their highest-scoring family. The sample records population and draw counts for each stratum. Mention and event stratum numbers index the extraction schema starting at one.

The primary judge is GPT-6 Luna at low reasoning effort. A second Luna call and GPT-6.1 Terra at low effort independently label the same random 100 units per frame. These are same-family judgments. Inputs contain the article title and body, a marked mention with up to 750 characters on either side, or the exact event window. The judge sees no prediction or scores. An issuer announcement copied by a news site remains a press release. A journalist quoting the announcement can produce reporting. Sentiment applies to the marked company's local financial consequences. Event families indicate topics discussed and can include a proposed or denied transaction.

## Reading the outputs

Run the sample and judge stages to reproduce the audit. To rebuild the analysis using completed labels, run:

```bash
just dvc repro -s report_metadata_validation
```

The research stage writes `validation.json` and a booktabs fragment, `validation.tex`, under `data/research/experiments/article-metadata/`. The confusion matrix rows are predictions and columns are judge labels. Cells use inverse inclusion weights. Precision and recall include the point estimate and a 95% article-cluster multiplier interval with stratum weight totals held fixed. Interpret intervals for rare classes alongside their observed counts. Ratios with empty denominators are null.

For the main paper, report press-release precision, recall, and the paired change in estimated prevalence, distinguishing the distinct-article and article–issuer denominators. Report the held-out focus rule comparison beside the number of Pricing Perspective firms passing the five-year screen. The configured rule uses three mentions and a zero relevance cutoff. For the appendix, include all classes, empty event windows, judge disagreement, the paired audit subset, score sensitivity and examples. Mention scores apply to extracted spans; measuring missed companies or issuer-level aggregated sentiment requires additional labels.

## Development diagnostics

The ten authored benchmark cases cover opposing sentiment, analyst versus target, regulator versus company, person versus place, generic aliases, negated and conditional acquisitions, two separate transactions, actual versus forecast values, and a press release. The stored diagnostic outputs illustrate why target attribution matters: both Microsoft and Intel received negative sentiment in a passage contrasting Microsoft's gains with Intel's losses. The analyst-source example split Goldman Sachs into two spans, and both received positive sentiment alongside Apple. Those examples motivated marking the target in each mention prompt. Synthetic cases contribute zero weight to confirmation estimates.

## Confirmation findings

Among distinct usable articles, the weighted press-release share was 42.1% under GLiNER and 4.2% under Luna. The paired difference was −37.9 percentage points (95% interval −40.1 to −35.6). Press-release precision was 8.0% (3.7–13.9%) and recall was 80.2% (57.6–94.4%). Only 14 sampled articles received the primary judge's press-release label. For usable article–issuer links, the paired difference was −37.3 points (−47.0 to −27.6). Report raw press-release counts as classifier outputs when describing corpus composition.

For company mentions, positive sentiment precision was 40.7% and negative precision was 50.0%. In an estimated 7.4% of mentions, GLiNER and the primary judge assigned opposite positive and negative labels. Weighted sentiment agreement across the five labels and invalid-span decisions was 82.3% on the Luna repeat and 57.2% between Luna and Terra. Keep investor-facing sentiment exploratory. The study evaluates extracted mentions and uses same-family model judges.

Substantive local relevance had 71.5% precision and 67.0% recall. For whole-article company focus, three mentions alone reproduced the configured rule's 66.1% precision, 56.9% recall and 57 qualifying roster firms. A relevance-only cutoff of 0.40, chosen on development articles, yielded 41.7% precision, 53.8% recall and 83 qualifying firms. The additional roster coverage comes with substantially lower precision.

The primary judge found at least one event family in 160 of the 200 windows where all GLiNER scores fell below 0.5. For transactions, precision was 65.1% and recall was 23.6%. An empty predicted event set provides weak evidence of event absence in this corpus.

The primary judge marked three article forms as insufficient context. They account for 0.55% of weighted distinct articles. Counting all three as press releases would raise the judge-estimated share from 4.18% to 4.73%. The publication table reports the observed sample count for each reference label.
