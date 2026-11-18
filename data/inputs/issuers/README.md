# Issuer reference

The universe for company linking is **US-listed SEC filers**, identified by CIK.

## Snapshot (`snapshot_issuers`)

The snapshot stage records three public sources in `data/raw/issuers/`:

| Source | Contents |
|---|---|
| SEC `company_tickers_exchange.json` | Current CIK, name, ticker and exchange. |
| SEC bulk `submissions.zip` | Kept only for listed CIKs, without filings: name, former names with dates, entity type and SIC. |
| Wikidata, via the four queries here | Dated exchange listings (`tickers.rq`), English labels and aliases (`names.rq`), and subsidiaries through parent organization or owner (`parents.rq`, `owners.rq`). |

`provenance.json` records each URL, retrieval time and SHA-256, plus the query hashes.

SEC fair-access rules require a User-Agent naming the requester. Supply it only for this command:

```bash
SEC_USER_AGENT="Name contact@example.org" just dvc repro snapshot_issuers
just dvc freeze snapshot_issuers
```

## Prepared tables (`prepare_issuers`)

`data/processed/issuers/` holds three tables, plus `summary.json`:

- **`issuers`:** every CIK with a ticker on an exchange in [exchanges.csv](exchanges.csv) that was still listed on or after `issuers.since`.
- **`tickers`:** dated listings. Wikidata supplies start and end dates. SEC tickers are current; they are dated from the issuer's earliest Wikidata US listing (Alphabet from 2016) and are otherwise undated. Where Wikidata gives a parent's open listing to an operating subsidiary (AAL on American Airlines, Inc.), the ticker's current SEC registrant keeps it.
- **`aliases`:** comparison keys from `normalize`, with validity dates where known:
  - current and former SEC names;
  - Wikidata labels and aliases;
  - tickers;
  - subsidiaries with at least `issuers.min_sitelinks` Wikipedia editions, followed through at most one intermediate parent (YouTube → Google → Alphabet). "Owned by" also records shareholdings, so it counts only for items that are not issuers themselves.

## Limitations

- **Delisted issuers** come only from Wikidata, so delisted firms that Wikidata lacks are missing.
- **Listing dates** are unknown for SEC-only tickers without Wikidata dates, so those issuers are treated as listed throughout.
- **Wikidata "unknown value" dates** are read as open-ended.
