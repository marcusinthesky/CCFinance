# CCFinance

CCFinance links archived English-language news to corporate issuers so that
researchers can reconstruct the sample behind a financial news study. The
frozen selection contains 14,807,287 captures from Fine News, a processed
release of Common Crawl News. Of these, 5,220,290 are consistently dated,
canonical captures with an accepted issuer link. Requiring three mentions
of the same issuer reduces that count to 2,547,597.

## Use the dataset

The [Hugging Face dataset](https://huggingface.co/datasets/marcusinthesky/CCFinance)
provides one sharded Parquet dataset with one row per capture. Each row contains
the publication and capture dates, eligibility decisions, entity offsets,
issuer assignments, window scores and a 768-dimensional FP16 body embedding.
Readers can project just the columns they need. The dataset card includes a
streaming example, a query to reproduce the counts above, the label order,
and estimates of extraction, linking and subject-focus accuracy.

CCFinance-authored annotations and embeddings carry CC BY 4.0. The card
identifies the upstream metadata sources and their terms. Researchers who
require the underlying articles can use the frozen upstream identifiers to
locate the corresponding bodies under the applicable source terms.

## Start

Use the pinned development environment to build the data pipeline or manuscript.

```bash
bash infra/nix/install-devenv.sh
devenv shell
just setup
just python::run --help
just python::run stages list
just check
```

Shared agent instructions and Codex configuration are maintained in
[`.agents/`](.agents/README.md). `just setup` applies them; use
`just agents::preview` to preview link changes and `just agents::check` to
verify the generated links.

`just check` validates Justfile syntax and formatting alongside the other
quality gates. Run `just fmt` to format Justfiles and other source files.

For Python alone, with Python 3.13, uv and just installed:

```bash
just python::setup
just python::check
```

## Data and reproducibility

DVC is initialized at the repository root with analytics disabled. Use:

```bash
just dvc status
just dvc dag
```

To restore the frozen paper inputs in a fresh checkout, run
`just restore-source` with authorized access to the staging dataset and
`just restore-vectors` for the public CCFinance metadata revision. Both
commands take an optional destination and require a fresh output directory.
The vector restore projects IDs, text-presence flags and FP16 coordinates
from each public shard and checks every reconstructed file against its DVC
digest. The remaining paper artifacts come from the private DVC bucket.

Semflow tracks the executable Python dependencies of DVC stages. When adding a
stage, run `just semflow-patch` to review its proposed fingerprints, then
`just semflow-apply` to materialize them. Commit the generated
`.semflow/hashes/` files with the DVC definition. After semantic source changes,
run `just semflow-refresh`; `just semflow-check` detects stale fingerprints.
The frozen [Fine News acquisition stage](data/inputs/fine-news/README.md) retains
the published staging snapshot and its historical selection recipe. DVC verifies
the restored output during reproduction. The
[source comparison](data/inputs/source-comparison/README.md) prepares small
probability samples using Parquet metadata before acquiring article payloads.
[Article metadata](infra/inference/README.md) is extracted on a local GPU after
a seeded benchmark; the long run resumes from completed row groups.
Keep data, configuration and environment dependencies explicit in DVC: Semflow's
static analysis cannot discover string-driven dynamic imports.

See [Python commands](src/python/README.md), [LaTeX commands](src/latex/README.md)
and [infrastructure](infra/README.md). The project code is licensed under
[Apache-2.0](LICENSE).

With the frozen inputs and processed outputs restored, run
`just release-metadata .runtime/ccfinance-release` to build the Hub files in a
new directory. The exporter selects public columns explicitly, preserves the
stored FP16 vectors, reconciles row totals and writes a SHA256 manifest.

## Replication studies

With the source snapshots and processed corpus restored, run a study from
the pinned environment.

```bash
just dvc repro report_baker_emv
just dvc repro report_kazinnik_banks
just dvc repro report_lopez_portfolios
```

The [replication plan](.context/plan/replication/README.md) records the study
populations, targets and verification criteria. The [comparison with the
reference papers](.context/plan/replication/comparison.md) gives estimates and
uncertainty for all three studies. The
[EMV tracker](data/inputs/baker-emv/README.md) uses publisher-month article
counts. The [bank networks](data/inputs/kazinnik-banks/README.md) use dated
bank co-mentions. The [overnight probes](data/inputs/lopez-lira-tang/README.md)
use fixed embeddings of article bodies available before the market cutoff.

## Publish a text follow-up

When all frozen article bodies have a documented basis for public
redistribution on Hugging Face, run
`just publish-text .runtime/ccfinance-text-release`. A missing output directory
triggers a full build before upload. An existing release directory is reused.

For a subset, run `just release-text <approved-ids.csv> <fresh-output>` with the frozen
source and article metadata restored. The private approval input is a
single-column UTF-8 CSV with header `id`, containing only capture IDs whose
exact bodies have a documented basis for public redistribution on Hugging
Face. Keep the underlying rights records outside the upload. The exporter
verifies the original source and checks each exported body against its
annotation digest.

After reviewing the coverage, generated card and manifest, run
`just publish-text <output>` from the pinned environment with write access
through both the Hub client and Git HTTPS. The staging branch is publicly
readable, so use the publish command only for the approved release. The
command prints the public revision after verification.
