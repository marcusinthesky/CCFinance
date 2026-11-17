# Native decision inference

These scripts run the pinned native Kev server using the CUDA libraries of an
already cached container image. SGLang is not launched. Native Kev shares the
article prefix across its independent identity and coverage questions.

From the repository root, prepare the small serving dependencies and then supply
the existing checkpoint and Hugging Face base-model cache:

```bash
just inference::setup
just inference::serve /path/to/kev-4b /path/to/huggingface/hub \
    data/inputs/article-labels/kev-4b-low-memory.json
docker logs ccfinance-kev-native
just inference::status
```

The versioned runtime manifest records the model, source, image, precision,
kernels and admission limit. The entrypoint applies that limit to both the
article and every complete article-question sequence. Oversized inputs fail
explicitly; text truncation is disabled. Local package and compilation caches
live under ignored `.runtime/`.

The third argument selects the versioned runtime profile. Pass the selected 4B
profile explicitly; omitting it selects the historical 0.8B baseline.

The 4B profile uses BF16 and retains one article prefix. Its adapter and head
checksums are checked before loading. The serving trial records actual memory
use separately from the model publisher's memory estimate.

To restore the pinned public 4B files with the repository's Hugging Face CLI:

```bash
uv run --project src/python --offline --frozen hf download jaredpalmer/kev-4b \
    adapter_config.json adapter_model.safetensors head.pt \
    --revision 139fdd94f1b6a6ad80cc15e08fcb99cac885a101 \
    --local-dir .runtime/models/kev-4b
HF_HUB_CACHE="$PWD/.runtime/hf-cache" \
    uv run --project src/python --offline --frozen hf download Qwen/Qwen3.5-4B-Base \
    --revision 1001bb4d826a52d1f399e183466143f4da7b741b \
    --include '*.json' --include '*.safetensors' \
    --include merges.txt --include vocab.json
```

The base weights require approximately 9.3 GB of storage. Model files and caches
stay under ignored `.runtime/`; their revisions and checkpoint checksums remain
in the versioned profile. Setup expects the recorded container image to exist
locally and a working NVIDIA Container Toolkit CDI device.

The completed company-labeling pilot used `kev-4b.json` with three concise
binary questions per distinct company descriptor, sharing the full article
prefix. Its graph buffers hold four states, 16 rows and 16,384 tokens. Active
pilot samples reached 15,654 MiB with 197 MiB free on the 16,311 MiB GPU. An
earlier diagnostic graph capture ran out of memory and fell back to eager
inference; the completed pilot's native graph and prefix OOM counters stayed
zero. One client timeout was retried successfully.

Production uses the separate `kev-4b-low-memory.json` profile: two graph states,
eight rows and 8,192 graph tokens. The 8,192-token context admission, prefix
cache, weights, precision, temperature and questions remain the same. Sixteen
exact pilot requests, including its eight longest admitted bodies, compared 337
probabilities: maximum difference 0.0073, mean difference 0.0001134, with no
changes at the 0.5 or 0.95 boundaries. The differences reflect floating-point
reassociation across smaller passes. Occupancy samples reached 14,580 MiB during
long-body inference and 15,074 MiB after graph capture, with 777 MiB free. These
observations describe the tested requests rather than guarantee every future
workload's peak.

`kev-0.8b.json` records a separate experimental 16k admission trial. The smaller
model was rejected for this pilot after the same fresh source cases produced
more false positives. The seven-case long-context study was stopped after one
HTTP success; it does not establish 16k semantic quality. The original
`runtime.json` remains the historical 8k baseline.

Stop the server with `just inference::stop`; remove its stopped
container with `docker rm ccfinance-kev-native` before starting a replacement.

## GLiNER extraction benchmark

The separate GLiNER environment measures company spans, per-span roles and
article type on source-verified samples. Its image is pinned above; the package
and model revisions are pinned in `gliner-requirements.txt` and
`gliner-setup.sh`. Setup downloads public model weights and applies a small
GLiNER 2.1.0 patches: attribute logits are on the CPU when indexed, so their
index tensor must be on that same device; and synthetic sentence punctuation
must not be mapped onto the source when a window ends without punctuation.
The patches do not change the model weights. Corrected window spans retain a
`synthetic_suffix_removed` flag; other out-of-window spans are marked invalid.
An additional opt-in patch supports `--batched-attributes`: it collects spans
using GLiNER's existing decoder, then scores their role attributes together on
the GPU. The original path remains the default. Floating-point reassociation
can change nearly tied role labels, so paired parity checks remain necessary.

```bash
bash infra/inference/gliner-setup.sh
just inference::gliner-check
uv run --project src/python --offline --frozen --all-packages \
    python infra/inference/gliner_sample.py --output .runtime/gliner-benchmark/sample
bash infra/inference/gliner-run.sh gliner2.5-small-v1 \
    --sample .runtime/gliner-benchmark/sample/articles.jsonl \
    --output .runtime/gliner-benchmark/results/small-fp16-flash \
    --limit 10000 --batch-size 64 --precision fp16 --backend disentangled_flash
```

The sample is drawn from retained source rows by a seeded SHA-256 priority; its
selection and body checksums are recorded. Samples contain article text and
remain in ignored local storage. The output preserves model predictions and
identifies invalid offsets explicitly. Timings include extraction, validation
and compressed output but exclude model loading, warmup and source reads; those
are reported separately. They do not establish model accuracy.

Long documents are split into overlapping 384-word windows, with 64 words of
overlap. GLiNER merges entity spans across windows and selects the highest
confidence window's classification. Roles are per extracted mention and need
not describe the entire article. These experimental outputs require validation
and a separate company-identity linking step before use as research labels.
`quantize=True` in GLiNER means FP16; INT8 is a separate TorchAO trial. GLiNER
2.1.0 does not allow DisentangledFlash and `torch.compile` simultaneously.
The experimental `disentangled_flash_heads` backend keeps the prepared encoder
outside compilation and compiles only the extraction-head modules. Validate
paired output agreement before adopting it.

For a shorter paired comparison, select a deterministic 500-record subset and
run each configuration through the same entrypoint. Each run has its own
container and output directory. Keep initialization and timed extraction
separate when comparing configurations.

```bash
python infra/inference/gliner_screen_sample.py \
    .runtime/gliner-benchmark/sample/articles.jsonl \
    .runtime/gliner-benchmark/screen.jsonl
bash infra/inference/gliner-run.sh gliner2.5-small-v1 \
    --sample .runtime/gliner-benchmark/screen.jsonl \
    --output .runtime/gliner-benchmark/screen-results/small-fp32 \
    --limit 500 --batch-size 64 --precision fp32
bash infra/inference/gliner-run.sh gliner2.5-small-v1 \
    --sample .runtime/gliner-benchmark/screen.jsonl \
    --output .runtime/gliner-benchmark/screen-results/small-fp16-flash \
    --limit 500 --batch-size 64 --precision fp16 --backend disentangled_flash
python infra/inference/gliner_compare.py \
    .runtime/gliner-benchmark/screen-results/small-fp32/predictions.jsonl.gz \
    .runtime/gliner-benchmark/screen-results/small-fp16-flash/predictions.jsonl.gz \
    --output .runtime/gliner-benchmark/screen-results/comparison.json
```

Agreement between configurations measures stability, not accuracy. The output
does not resolve extracted names to issuers or show that a company is a primary
subject of a complete article.

The GPU batch size and article buffer size are separate. A larger article
buffer lets GLiNER's DataLoader prepare future window batches while the GPU
processes the current batch. Use `--buffer-size 2048 --workers 4` to test this
schedule; the container provides 1 GiB of shared memory for worker transfers.
The benchmark caps its CUDA allocator at 80% of device memory by default.
Reports record every parameter device and dtype, CUDA memory, and worker counts.
FP8 and NVFP4 trials quantize encoder linear projections; embeddings, extraction
heads and other operations retain their higher precision.

```bash
bash infra/inference/gliner-run.sh gliner2.5-small-v1 \
    --script infra/inference/gliner_profile.py \
    --sample .runtime/gliner-benchmark/screen.jsonl \
    --output .runtime/gliner-benchmark/profile-compiled --limit 64
```

Profiling attributes CPU calls and CUDA kernels, with instrumentation overhead;
use separate unprofiled runs for throughput. Precision probes test CUDA kernel
compatibility independently of model speed and extraction quality.

## Measured configuration

On 17 November 2026, the 74M-parameter small checkpoint completed three runs of
the same source-verified 10,000-record sample at 163.7, 162.3 and 162.5 articles
per second on the RTX 5060 Ti. The aggregate rate was 162.8/second, projecting
20.9 hours of extraction for 12,241,870 retained records. This excludes source
reconstruction and downstream issuer linking. Peak PyTorch reserved CUDA memory
was 7.50 GiB; driver allocations are separate.

The configuration uses FP16, DisentangledFlash, compiled extraction heads,
batched role scoring, 128-window GPU batches, four preprocessing workers and an
8,192-article buffer. Windows contain 384 word tokens with 64-token overlap.
All model parameters were verified on CUDA. Every record passed structural
checks; the first and third repetitions produced identical predictions.

```bash
just inference::gliner-run gliner2.5-small-v1 \
    --sample .runtime/gliner-benchmark/sample/articles.jsonl \
    --output .runtime/gliner-benchmark/custom-run \
    --limit 10000 --batch-size 128 --buffer-size 8192 --workers 4 \
    --precision fp16 --backend disentangled_flash_heads --batched-attributes
```

The [benchmark report](../../data/research/experiments/article-labels/gliner-benchmark/report.md)
and its DVC artifact retain selections, predictions, timings, comparisons,
compatibility probes and historical experiment launchers. These results establish
computational feasibility, not label accuracy. Diagnostic examples include
people and places labeled as companies; the roles also describe windows rather
than calibrated whole-article subject probabilities. Human validation and dated
issuer linking remain prerequisites for research use.

## Financial metadata pilot

`gliner_schema.py` retains the historical `build_schema()` benchmark contract.
`build_metadata_schema()` adds companies, people, public bodies and places;
company-specific local relevance and financial sentiment; article form; and
multi-label event families. Its optional record schema extracts event triggers,
participants, quantities, periods, comparisons, dates, locations, attribution,
assertion and lifecycle stage. Event families are documented coarse rollups of
[SENTiVENT](https://github.com/GillesJ/sentivent-event-annotation-guidelines).
Article form and subject remain separate, following
[IPTC NewsCodes](https://iptc.org/std/NewsCodes/guidelines/).

The `transactions` profile is a focused acquisition control, anchored by the
acquiring company. It tests whether fewer fields improve argument grouping;
its presence does not establish that an acquisition occurred.

```bash
just inference::gliner-metadata gliner2.5-small-v1 \
    --sample .runtime/gliner-benchmark/screen.jsonl \
    --output .runtime/gliner-metadata/custom-small \
    --limit 100 --batch-size 16 \
    --profiles baseline core events transactions
```

The runner reuses the first 100 members of the deterministic screening sample
and appends ten authored diagnostic examples. Those examples test negation,
conditional deals, conflicting sentiment, multiple transactions, person/place
confusion, generic aliases, regulators, analyst attribution, forecasts and
press releases. They are separate from the real-news sample and do not estimate
population accuracy. Inputs use complete article bodies without adding titles.

Instance-local hooks in `gliner_probabilities.py` expose scores already computed
by the pinned 2.1.0 decoder. They add no encoder pass. Single-label classification
and company attributes use softmax; event-family classifications use independent
sigmoids. The upstream multi-label decoder can return its highest label even
when every score is below the threshold. Inspect the complete distribution and
the reported fallback count before interpreting that label as detected content.
Structured-record enum confidences are decoder scores, not normalized class
distributions. Enum labels are kept separate from source evidence: upstream
coordinates can identify their record anchor rather than the literal label.

Each profile saves its schema, merged predictions, window evidence, complete
classification and attribute distributions, and numerical and source-offset
checks. The manifest records sample, model-weight and executing-code hashes.
Timings include probability diagnostics and use small batches; they do not
replace the full-sample throughput benchmark. Scores remain uncalibrated, and
local attributes do not establish whole-article company primacy.

The [metadata pilot report](../../data/research/experiments/article-labels/gliner-metadata/report.md)
compares both cached models on the same 100 real articles and ten diagnostic
examples. It documents false company proposals, diffuse sentiment scores,
schema-dependent labels and confident event errors. The DVC artifact includes
complete vectors, reviewed examples, source selections and executing code.
