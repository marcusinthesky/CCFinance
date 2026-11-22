# Company mention micro-benchmark

The sample comprises eight article leads per publication year from 2019 through
2023. The frame contains English articles from the financial-publisher staging
snapshot that the [processed corpus](../../README.md) marks canonical and
consistently dated. Frame sizes are 1,250,715, 1,563,214, 1,571,984, 1,557,377
and 1,375,820, respectively. Within year, the sample takes the eight lowest
SHA256 hashes of `stanza-microbench-v1:<article-id>`. A lead begins at
character zero of the original body field and ends after its 150th
whitespace-delimited word or last word, preserving whitespace in between. The
[manifest](manifest.jsonl) records the source snapshot revision, DVC hashes,
ranks, IDs, years, hosts, source shards, passage hashes and exclusive Unicode
end offsets. The source bodies stay in the restored corpus.

An independent GPT-6.2-sol medium Codex agent labelled all 40 leads and a
GPT-6.2-sol low Codex agent labelled the first two ranks in each year from the
[annotation guide](annotation.md). Both worked blind to extractor outputs.
The repeat agent saw neither the primary labels nor the rest of the sample.
Their exact-span sets agreed on all ten repeated leads and all 26 reference
spans, including two empty leads. No disagreements required adjudication.
The [primary](primary-labels.jsonl) and [repeat](repeat-labels.jsonl) files
preserve the independent passes. The [frozen gold](gold.jsonl) is the unchanged
primary pass with 118 company spans across the 40 leads, eight of which have
none. These are model annotations, with agreement measured on a small subset.

The [frozen settings](settings.json) use Stanza 1.11.0 with the
`ontonotes_charlm` English model, `combined` tokenization and `combined`
multiword token expansion, plus the deployed GLiNER2.5 Small schema and 0.5
threshold from the [production launcher](../../../infra/inference/README.md).
The [inference record](inference.json) identifies the artifacts by checksum.
The [Stanza](stanza-predictions.jsonl) and [GLiNER](gliner-predictions.jsonl)
offset files save all emitted types. Scoring selects ORG and company,
respectively, and deduplicates by article ID and half-open Unicode offset pair.

## Panel A. Published Stanza context

| English benchmark | Entity types | Published all-class micro-F1 |
| --- | ---: | ---: |
| CoNLL03 | 4 | 92.1% |
| OntoNotes | 18 | 88.8% |

These figures refer to Stanford's benchmark test sets and entity taxonomies.
[Stanford NER model table](https://stanfordnlp.github.io/stanza/ner_models.html)

## Panel B. Local exact company spans

| Extractor | TP | FP | FN | Micro precision | Micro recall | Micro F1 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Stanza ORG | 69 | 132 | 49 | 34.33% | 58.47% | 43.26% |
| GLiNER company | 69 | 80 | 49 | 46.31% | 58.47% | 51.69% |

The observed difference in micro-F1 is **+8.43 percentage points** for GLiNER
with a paired 95% percentile interval of **−1.76 to +18.76 points**. Each of
2,000 draws resamples eight lead pairs with replacement within each publication
year, using seed 42, then recomputes the pooled micro-F1 for both systems. All
draws were defined. The difference is descriptive for this balanced lead
sample. See the [machine-readable results](scores.json).

### Errors and co-mentions

| False-positive span | Stanza | GLiNER |
| --- | ---: | ---: |
| Overlaps a gold span with different boundaries | 26 | 11 |
| Identified noncompany organization | 17 | 7 |
| Other unmatched spans | 89 | 62 |

The Codex error inspection identified political parties,
public institutions, a church and a professional group. Both models returned
the European Union and Eurostat in the CNBC lead at 2021 rank 2. Other false
positives include tickers, brands used as products and financial indices.
Stanza attached a possessive to Credit Suisse Group AG at 2023 rank 6. GLiNER
trimmed Porsche Financial Services to Porsche at 2019 rank 4, and missed the
BofA co-mention at 2020 rank 1. Stanza missed Simply Good Foods in the heading
at 2020 rank 2.

The closing complete sentence of the Benzinga lead at 2020 rank 1 mentions
Mosaic Company, Chipotle Mexican Grill, Alexion Pharmaceuticals, Take-Two
Interactive, L Brands and BofA. The five stocks form ten pairs with each other,
and their data source BofA forms one pair with each stock. Stanza retained all
15 exact-span pairs. GLiNER retained the ten among the stocks and lost the five
involving BofA. In the opening sentence of the Business Standard lead at 2023
rank 6, GLiNER retained the UBS Group AG and Credit Suisse Group AG pair.
Stanza lost this pair because the Credit Suisse span included the possessive.
A missed company mention can suppress several links in a sentence-level news
network, changing who appears connected and when. These examples count mention
pairs before dated issuer resolution. Schwenkler and Zheng applied
**CoreNLP**, followed by normalization and Compustat/CRSP matching, in their
sentence-level firm network. [Schwenkler and Zheng, Section 3.2 and Figure 1](https://wrds-www.wharton.upenn.edu/documents/1125/news.pdf)

## Reproduction

Run from the repository root in `devenv shell`. Scoring the saved spans uses
the locked Python project alone.

```sh
uv run --project src/python --offline --frozen python \
  src/python/scripts/stanza_microbench/score.py
```

To regenerate the lead text and GLiNER input, restore the two DVC inputs and
reproduce the manifest in a fresh work directory.

```sh
work=.runtime/stanza-microbench-reproduction
frozen=data/inputs/stanza-microbench
scripts=src/python/scripts/stanza_microbench

just dvc status filter_fine_news prepare_articles
uv run --project src/python --offline --frozen python "$scripts/freeze.py" \
  --work "$work" --manifest "$work/manifest.jsonl"
diff -u "$frozen/manifest.jsonl" "$work/manifest.jsonl"
```

Run the pinned GLiNER configuration with the configured GPU and model cache.
For a fresh cache, first run `just inference::setup`.

```sh
just inference::extract "$work/gliner-input" "$work/gliner-output"
uv run --project src/python --offline --frozen python "$scripts/export_gliner.py" \
  --source "$work/gliner-output" --passages "$work/passages.jsonl" \
  --output "$work/gliner-predictions.jsonl"
```

Stage Stanza's published resources and isolated Python libraries before running
inference with networking disabled.

```sh
image=$(jq -r .gliner.image "$frozen/settings.json")
revision=$(jq -r .stanza.hub_revision "$frozen/settings.json")
resources_revision=$(jq -r .stanza.resources_git_revision "$frozen/inference.json")

mkdir -p "$work/stanza-resources" "$work/stanza-site"
curl -fLsS \
  "https://raw.githubusercontent.com/stanfordnlp/stanza-resources/$resources_revision/resources_1.11.0.json" \
  -o "$work/stanza-resources/resources.json"
HF_HUB_DISABLE_IMPLICIT_TOKEN=1 uv run --project src/python --offline --frozen \
  hf download stanfordnlp/stanza-en --revision "$revision" \
  --local-dir "$work/model-downloads" \
  models/tokenize/combined.pt models/mwt/combined.pt models/ner/ontonotes_charlm.pt \
  models/pretrain/fasttextcrawl.pt models/forward_charlm/1billion.pt \
  models/backward_charlm/1billion.pt
ln -s ../model-downloads/models "$work/stanza-resources/en"
docker run --rm --user "$(id -u):$(id -g)" \
  --mount "type=bind,source=$PWD/$work/stanza-site,target=/site" \
  --entrypoint python "$image" -m pip install --no-cache-dir --no-deps \
  --target /site stanza==1.11.0 emoji==2.14.1
docker run --rm --network none --user "$(id -u):$(id -g)" \
  --mount "type=bind,source=$PWD/$work,target=/benchmark" \
  --mount "type=bind,source=$PWD/infra/inference/stanza_microbench.py,target=/run_stanza.py,readonly" \
  --env PYTHONPATH=/benchmark/stanza-site --entrypoint python "$image" /run_stanza.py \
  --resources /benchmark/stanza-resources --input /benchmark/passages.jsonl \
  --output /benchmark/stanza-predictions.jsonl
```

Score the new predictions with the same frozen annotations. The optional
passages argument checks every saved mention against its original text.

```sh
cp "$frozen"/{gold,primary-labels,repeat-labels}.jsonl "$work/"
uv run --project src/python --offline --frozen python "$scripts/score.py" \
  --input "$work" --passages "$work/passages.jsonl"
```
