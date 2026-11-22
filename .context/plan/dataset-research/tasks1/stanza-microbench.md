---
title: A paired company-mention micro-benchmark
description: Measure how two frozen extractors recover financial company names on the same 40 passages.
---

# A paired company-mention micro-benchmark

**Question.** On the same financial news passages, how often do English Stanza and the deployed CCFinance GLiNER2.5 Small configuration recover the exact span of a named company? The unit is a company mention, including mentions of private firms. Dated issuer resolution is a later operation.

## Reference points

Stanford reports English all-class micro-F1 of **92.1 on CoNLL03** (four entity types) and **88.8 on OntoNotes** (18 types). Record those as published benchmark context. Report local company-span results in a separate panel with their own denominator. [Stanza NER model table](https://stanfordnlp.github.io/stanza/ner_models.html)

Schwenkler and Zheng used Stanford **CoreNLP** to extract organizations, normalized names and matched them to Compustat/CRSP to construct a sentence-level firm network. Their Figure 1 illustrates how losing one firm can lose several pairs. This motivates inspecting co-mentions here. Stanza supplies the technical baseline for this exercise. [Paper, section 3.2 and Figure 1](https://wrds-www.wharton.upenn.edu/documents/1125/news.pdf) · [Authors’ implementation](https://github.com/zhenghannan/Schwenkler-Zheng-2019)

## Exercise

1. **Freeze 40 passages.** From the pinned English usable, canonical articles in 2019–2023, take eight IDs per publication year in ascending SHA256 order of `stanza-microbench-v1:<article-id>`. Take the first 150 whitespace-delimited words of each original body, preserving all intervening characters. Keep passages with zero mentions. Save the source revision, ID, year, host, text hash and end offset. The balanced sample estimates performance on article leads within this design.
2. **Label before viewing predictions.** Mark every explicitly named company, retaining suffixes and excluding possessives, exchange codes and bare tickers. Treat a named subsidiary as its own mention. Exclude government bodies, unions and product names used solely for products. Record half-open Unicode character offsets. Independently double-label the first two passages per year, report exact-span agreement and resolve disagreements before scoring.
3. **Run both systems on identical text.** Pin Stanza's English OntoNotes NER package and resources; retain its ORG predictions. Run the repository’s [GLiNER2.5 Small configuration](../../../../infra/inference/README.md) on the same passages using the deployed company schema and threshold. Record revisions, commands and raw offsets. Keep noncompany ORG predictions as false positives under the company target; break them out in the error analysis so the broader Stanza label is visible. Freeze settings before opening labels.
4. **Score and interpret.** Match unique spans one-to-one by article ID, start and end. Pool TP, FP and FN across passages and report micro precision, recall and F1 for each system, the gold mention count and count of zero-mention passages. For the paired F1 difference, resample passages within year, recomputing pooled scores on each of 2,000 draws with seed 42. Report the percentile interval and any undefined draws. Inspect boundary errors, missed firms and noncompany organizations. For one multi-firm sentence if available, show which gold company pairs each extraction would retain.
5. **Deliver.** Link the frozen manifest, annotation instructions, gold spans, predictions, scoring command and two-panel results from the [task record](../tasks/stanza-microbench/README.md). State the sampling frame, model revisions, observed disagreement and uncertainty. Keep the comparison descriptive at this sample size.
