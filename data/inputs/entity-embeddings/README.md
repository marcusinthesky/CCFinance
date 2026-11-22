# Company-focused embeddings in CCFinance

The maintained evaluation asks whether switching the named company changes which company's account an article vector retrieves. The [protocol](entity-focus.md) defines the inputs, split and decision rule. Production whole-article embeddings use a separate [SGLang worker](../../../infra/inference/README.md). Its outputs are incremental. A corpus-wide coverage figure requires a census of completed row groups and nonblank source texts.

## Main result

Of 150 held-out stories, Luna found 18 distinguishable company accounts and 16 pairs fit all encoders. A success required both companies to prefer their own name-masked accounts. The independent Terra comparison had eight eligible stories. Neither denominator reached the planned minimum (60 Luna, 20 Terra).

| Model | Company header | Selected instruction | Sentences mentioning the company |
| --- | ---: | ---: | ---: |
| EmbeddingGemma-300M | 2/16 | 2/16 | 10/16 |
| OpenSearch neural embed v1 | 2/16 | 2/16 | 9/16 |
| Qwen3-Embedding-0.6B | 2/16 | 3/16 | 10/16 |

For the paper, report eligibility alongside these paired counts. Sentence
selection is the candidate for independent confirmation. The pilot is too
small to establish a model ranking. A follow-up should freeze the Gemma
header, instruction and sentence arms before drawing fresh stories, and
report how often the two companies share their supporting sentences.

## Appendix evidence

- Across-story acquisition retrieval yielded 38 directional stories among 80 sampled. Each condition used 76 comparisons across 19 independent deal pairs. Terra agreed with Luna on 16 of 20 audited stories. The primary gain was −6.6 percentage points (paired 95% interval −18.4 to +5.3). The prespecified decision was inconclusive. The [grounding audit](grounding-audit.csv) records the score-blinded source checks.
- The exploratory pooling comparison reused 25 eligible Luna stories from both original splits. Contextual sentence pooling scored 12/25 for Gemma and 11/25 for OpenSearch, one below each extracted-sentence baseline. Both scored 0/24 on controlled role swaps where both companies share a sentence mask. OpenSearch mention pooling scored 4/24. No one-pass method qualified.

## Reproduction and archive

From the repository root, run `devenv shell -- just dvc repro -s entity_embedding_tables` to rebuild three CSV tables in `data/research/experiments/entity-paper/` from the local frozen results. The acquisition and pooling DVC pointers retain the original per-comparison evidence. The template grid, margins and bootstrap outputs remain available in the entity-focus research directory.

The local Git tag `embedding-studies-v1` contains the original runners, model snapshot revisions, production parity notes, rubrics, fixture definitions and DVC lock. To inspect that version independently, create a worktree at the tag and point its local DVC cache setting at the original repository's absolute DVC cache path. Check out the study outputs using the stage names in that lock. This workspace also holds a hash-verified restore under `.runtime/embedding-studies-v1/data/`, mirroring repository-relative paths. These local-only data must accompany the source to reproduce frozen scores on another machine. Historical scratch files and rehearsal parity evidence are under the archive's `scratch/` directory.
