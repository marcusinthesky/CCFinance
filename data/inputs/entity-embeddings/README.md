# Can a company embedding distinguish an acquirer from its target?

This proposed validation asks whether a query about a buyer ranks the buyer in a different acquisition above that acquisition's target, and likewise for a target. Both candidate companies appear in the same story. Topic, publisher, date and article text are therefore identical for the two candidates. The development exercise used eight deals. Its 112 correlated comparisons scored 49.1–50.9% when the proposed instruction was switched on either side. The confirmation sample below is frozen. Role judgments and confirmation scores are pending.

## Sample

The sampling query reads usable 2018–2022 articles, requires acquisition language in the headline, a body of 300–6,000 characters, and exactly two accepted non-publisher issuers with linked surface forms in the headline. It excludes the earlier linker article sample and all eight development deal pairs. It selects one story per unordered issuer pair by hash and retains stories that rank first for both issuers. This gives 283 disjoint candidate stories. Asset purchases, ambiguous names and other false matches remain eligible for review. The estimand is performance on confirmed deals in this deliberately narrow frame.

| Publication year | Disjoint candidates | Drawn | Repeat and audit subset |
| --- | ---: | ---: | ---: |
| 2018 | 42 | 16 | 4 |
| 2019 | 44 | 16 | 4 |
| 2020 | 50 | 16 | 4 |
| 2021 | 82 | 16 | 4 |
| 2022 | 65 | 16 | 4 |

The 80 sampled articles contain 160 distinct issuer IDs and have zero article IDs in common with the separate 250-article general-news review packet. The frame uses all linked issuers in the pricing-perspective reporting years. Seven sampled articles include a pricing-perspective roster firm. The SHA-256 of the manifest is `c2a2b437175f0379e72c7c1bcd9688b806c145170d0d615e0503541b58216203`. It hashes the strings `id/first_cik/second_cik/audit_as_0_or_1` joined by `|` in ascending article-ID order.

Run the selection at the repository root in the pinned environment.

```sh
mkdir -p data/processed/experiments/entity-embeddings
duckdb -bail < data/inputs/entity-embeddings/sample-acquisitions.sql
```

## Blinded Pydantic AI reference

Give the primary `openai-codex:gpt-6-luna` judge the title, complete body and two issuer names in hash-shuffled order. Ask which firm bid for or acquired the other. Count a proposal or failed deal when the story explicitly identifies the bidder and target. Classify asset purchases, minority stakes, outside commentators and deals involving a third party as `other`. Use `unclear` for insufficient evidence. The reference schema has two fields.

```python
class DealLabel(BaseModel):
    direction: Literal["A_buys_B", "B_buys_A", "other", "unclear"]
    quote: str | None
```

Require a verbatim supporting quotation for a directional label. Use an `Agent.output_validator` to find the quote in the title or body and save its offsets locally. Log invalid or missing judgments after bounded retries. Keep the model, reasoning effort, schema, rubric, ordered input and judge role in the cache key. The reference judge only sees source material and issuer names. Map every decision back to its CIKs before comparing calls.

Use low reasoning effort. Repeat the same 20 preselected cases with Luna and reversed issuer order. Audit those 20 with `openai-codex:gpt-6.1-terra` in fresh calls. This schedules 120 reference judgments before retries. Report exact agreement with each repeat, directional reversals, evidence failures and unscorable counts. These are same-family model judgments. The existing metadata experiment and issuer output validators supply the implementation patterns. [Metadata judges](../../../src/python/apps/pipeline/src/pipeline/stages/processed/experiments/metadata_judges.py), [issuer validators](../../../src/python/apps/pipeline/src/pipeline/stages/processed/experiments/company_links.py), [judge settings](../../../params.yaml)

## Embeddings and decision

1. Pair the primary judge's confirmed deals by sorting on `sha256('role-comparison-1/' || id)` and taking adjacent stories. Publish the leftover ID if the count is odd. Each story belongs to one block. Use both search directions and both focal issuers, giving four comparisons per block. Roles enter only the scorer.
2. For each firm, the cheap baseline is its surface-name header and the source-order sentences overlapping its accepted mentions. The challenger uses the same header and one independently extracted factual sentence. Give a fresh extraction-only Terra call the article and one focal name. Ask what the firm did, experienced or proposed, preserve uncertainty, return a supporting quote, and allow abstention. The extractor receives neither the reference direction nor its supporting quote. Use one call per firm in the scored blocks, up to 160 additional calls. Luna supplies the primary reference and Terra's audit receives only the source and issuer names. Same-family dependence remains. Freeze the extractor prompt and model before seeing confirmation labels.
3. Hold every query fixed at the focal firm's mention sentences and the proposed role-search instruction. On the document side cross the two text choices with the presence or absence of that same instruction. The literal Python prefix is `"Instruct: Retrieve news passages describing a similar event in which the focal company played a similar role.\nQuery: "`. Freeze the OpenSearch revision `d558088abac35e8932772965a85e927aedfe49c7`, pooling, token budget, serialization and cosine scoring for all arms. Store issuer names as they appear in the article. Grade whether the same-role document outranks the opposite-role document. An exact tie earns half credit. A comparison with an abstaining document earns zero for the fact method. Report abstentions and the assessed coverage separately.
4. The primary contrast is the unprompted factual statement against the unprompted mention sentences. Report accuracy by role and paired percentage-point gain with a 95% percentile bootstrap interval over whole deal-pair blocks (10,000 draws, seed 48). The matched instruction differences are secondary. Report the 50% chance reference, raw counts and numbers of independent blocks. Technical failures remain pending or are reported as missing.

Use at least 40 confirmed deals and require agreement with the primary judge on at least 18/20 cases for each of the repeat and audit passes. Require at least eight primary-directional cases among those 20 so an audit dominated by rejections cannot pass. Lower yield or agreement warrants an inconclusive finding. With those conditions met, advance explicit facts to a larger search test if accuracy reaches 65%, the gain reaches ten percentage points, and its paired lower 95% bound exceeds zero. Stop investigating the more expensive representation for this task if the paired upper bound is below ten points. Otherwise record an inconclusive result. These are proposed pilot decision thresholds, chosen before commissioning labels.

For the paper, one table can report the two-by-two comparison, judge agreement and exclusions. Also inspect the first 20 generated statements by the hash of their article ID and CIK, blinded to performance. Record whether the quote supports the statement for that firm, including transaction status. Verbatim quotes are mechanically checkable. Entailment requires reading them. Label the result as model-adjudicated acquisition-role discrimination. Success would justify testing additional event families and retrieval from a larger index.

## Running the study

From the repository root in the pinned environment, prepare the model snapshots and run the local stages. The OpenSearch snapshot uses the production revision. The comparison uses its CPU Transformers reference when the overnight SGLang job occupies the GPU. Gemma and Qwen load their published Sentence Transformers modules in the same offline inference container.

```sh
bash src/python/scripts/acquisition_roles/setup.sh
just dvc repro acquisition_role_grounding
just dvc repro acquisition_role_report
```

Reference and extraction calls use the configured Codex provider. Validated responses are cached by input, rubric, schema, model, effort and role. The grounding packet has the statement, source quote and issuer for the 20-item review. The report produces per-comparison Parquet, a JSON decision record and a LaTeX table under `data/research/experiments/acquisition-roles/`. Rebuilding the report from the frozen vectors requires no judge calls.

## Confirmation judgments and source check

Luna classified 38 stories as directional, 39 as other and three as unclear. The 19 disjoint deal pairs yield 76 retrieval comparisons per condition. Luna's reordered repeat agreed on 20/20 cases. Terra agreed on 16/20, including three cases it classified as other and one as unclear where Luna assigned a direction. Twelve of the 20 audited stories had a directional primary label. Both the 40-deal minimum and the 18/20 audit threshold were missed.

Terra produced 73 factual sentences from 76 issuer inputs and abstained three times. In the score-blinded Codex review, 15/20 quotations supported the entire statement for the named firm on their own. Three needed surrounding text. One sentence reversed the relationship between a business and its incorporated name. One described a target using a bidder's CIK: the 2021 story distinguished Coherent Inc. from competing bidder II-VI, which later took the name Coherent Corp. A separate tracking-stock story illustrates the difficulty of deciding whether a transaction is a whole-company acquisition. The scored cohort follows its frozen primary judgments. [Grounding assessments](grounding-audit.csv)

The study used the OpenSearch CPU reference while the full-corpus GPU run was active. On three distinct source texts, cosine similarity with the saved production SGLang vectors ranged from 0.999976 to 0.999998. Gemma and Qwen passed direct pooling and projection parity checks in the pinned container. The eight development stories exercised all encoders with reference roles and explicit abstention fixtures before the confirmation evaluation.

| Stored document | Mention sentences | Extracted fact |
| --- | ---: | ---: |
| OpenSearch, plain | 52.6% | 46.1% |
| OpenSearch, document instruction | 47.4% | 50.0% |
| Qwen3-Embedding-0.6B | 55.3% | 48.7% |
| EmbeddingGemma-300M, body | 48.7% | 47.4% |
| EmbeddingGemma-300M, headline and body | 51.3% | 43.4% |

The primary OpenSearch gain was −6.6 percentage points (paired 95% interval −18.4 to +5.3). No input was truncated. The preregistered decision is **inconclusive** because the sample yield and cross-model judge agreement missed their thresholds. These results provide no positive signal for scaling the factual-sentence extraction. Each cell uses 76 comparisons from 19 independent deal pairs.
