"""Build or publish the approved companion CCFinance article bodies."""

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

import duckdb
import yaml
from huggingface_hub import CommitOperationAdd, HfApi, hf_hub_download

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
RAW = ROOT / "data/raw/fine-news"
DIGESTS = ROOT / "data/processed/article-metadata/articles"
REPO = "marcusinthesky/CCFinance"
BASE = "524d04acec2ed7dfc5b76cfb09fae9e57850b062"
SOURCE = "3168f32f57107eac95a2c53f024e5e340c91ef2e"
PROVENANCE = "64099e7dfd6ba98b0a9e086aed21f0ab17f86a1bd94875bf4bc817a63a8ef4cc"


def digest(path: Path) -> str:
    """Hash the bytes on disk."""
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def card(rows: int, total: int) -> str:
    """Extend the published metadata card for the text release."""
    _, raw, body = (HERE / "card.md.in").read_text().split("---\n", 2)
    metadata = yaml.safe_load(raw)
    metadata["license"] = "odc-by"
    metadata["configs"][0]["default"] = True
    metadata["configs"].append(
        {
            "config_name": "text",
            "data_files": [{"split": "corpus", "path": "text/*.parquet"}],
        }
    )
    heading = "## Data dictionary"
    section = f"""## Article text

The `text` configuration contains frozen Fine-News article bodies for {rows:,}
of {total:,} captures. Its coverage reflects which bodies could be publicly
redistributed. Join its `id` to the default corpus to use the dates, annotations
and embeddings. Character offsets apply directly to these bodies.

```python
from datasets import load_dataset

bodies = load_dataset(
    "marcusinthesky/CCFinance", "text", split="corpus", streaming=True,
)
```

[Text release manifest](documentation/text-manifest.json)

"""
    rights = "Marcus Gawronsky releases"
    notice = (
        "CCFinance makes the database rights it holds available under the "
        "[Open Data Commons Attribution License (ODC-By) 1.0]"
        "(https://opendatacommons.org/licenses/by/1-0/). "
        "Use of the CC-NEWS-derived content is subject to "
        "[Common Crawl's Terms of Use](https://commoncrawl.org/terms-of-use) "
        "and applicable upstream terms. Copyright in the article bodies remains "
        "with the respective rights holders.\n\n"
    )
    body = body.replace(heading, section + heading, 1).replace(
        rights, notice + rights, 1
    )
    body = body.replace("The downloadable shards", "The default corpus shards")
    return "---\n" + yaml.safe_dump(metadata, sort_keys=False) + "---\n" + body


def build(approved: Path | None, output: Path) -> None:
    """Export the approved bodies into a fresh directory."""
    if output.exists():
        raise FileExistsError(output)
    manifest_path = RAW / "provenance.json"
    if digest(manifest_path) != PROVENANCE:
        raise ValueError("Frozen source manifest digest mismatch")
    source = json.loads(manifest_path.read_text())
    if source["revision"] != SOURCE:
        raise ValueError("Unexpected source revision")
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=output.parent) as temporary:
        scratch = Path(temporary)
        release = scratch / "release"
        (release / "text").mkdir(parents=True)
        (release / "documentation").mkdir()
        inventory = []
        exported = 0
        with duckdb.connect() as con:
            con.execute("SET memory_limit='5GB'")
            con.execute("SET temp_directory=?", [str(scratch / "duckdb")])
            initial = None
            total = source["records"]
            if approved is not None:
                con.execute("CREATE TABLE approved (id VARCHAR PRIMARY KEY)")
                initial = digest(approved)
                con.execute(
                    "INSERT INTO approved SELECT * FROM read_csv(?, header=true, "
                    "columns={'id': 'VARCHAR'}, auto_detect=false)",
                    [str(approved)],
                )
                total = con.execute("SELECT count(*) FROM approved").fetchone()[0]
                if not total or digest(approved) != initial:
                    raise ValueError("Approved capture CSV is empty or changed")
            for shard in source["shards"]:
                path = RAW / shard["path"]
                if (
                    path.stat().st_size != shard["bytes"]
                    or digest(path) != shard["sha256"]
                ):
                    raise ValueError(f"Frozen source shard differs: {path}")
                relative = Path(shard["path"])
                stem = "--".join(relative.with_suffix("").parts)
                query = (
                    "CREATE OR REPLACE TEMP TABLE selected AS "
                    "SELECT id, text FROM read_parquet(?)"
                )
                if approved is not None:
                    query += " SEMI JOIN approved USING (id)"
                con.execute(query, [str(path)])
                count, unique, nonempty = con.execute(
                    "SELECT count(*), count(DISTINCT id), count(*) FILTER "
                    "(WHERE text IS NOT NULL AND text <> '') FROM selected"
                ).fetchone()

                if not count:
                    continue
                if count != unique or count != nonempty:
                    raise ValueError(f"Duplicate ID or empty body in {relative}")
                matched, correct = con.execute(
                    "SELECT count(*), count(*) FILTER "
                    "(WHERE sha256(s.text) = d.text_sha256) "
                    "FROM selected s JOIN read_parquet(?) d USING (id)",
                    [str(DIGESTS / f"{stem}--*.parquet")],
                ).fetchone()
                distinct_matches = con.execute(
                    "SELECT count(DISTINCT s.id) FROM selected s "
                    "JOIN read_parquet(?) d USING (id)",
                    [str(DIGESTS / f"{stem}--*.parquet")],
                ).fetchone()[0]
                if matched != count or correct != count or distinct_matches != count:
                    raise ValueError(f"Published body digest mismatch in {relative}")
                dest = release / "text" / f"{stem}.parquet"
                con.execute(
                    "COPY (SELECT id, text FROM selected ORDER BY id) TO ? "
                    "(FORMAT PARQUET, COMPRESSION ZSTD, ROW_GROUP_SIZE 4096)",
                    [str(dest)],
                )
                if approved is not None:
                    con.execute(
                        "DELETE FROM approved USING selected "
                        "WHERE approved.id = selected.id"
                    )
                inventory.append(
                    {
                        "path": dest.relative_to(release).as_posix(),
                        "rows": count,
                        "bytes": dest.stat().st_size,
                        "sha256": digest(dest),
                    }
                )
                exported += count
            # Catch source IDs repeated across shards.
            if exported != total:
                raise ValueError(f"Expected {total:,} bodies, exported {exported:,}")
            duplicates = con.execute(
                "SELECT count(*) FROM (SELECT r.id FROM read_parquet(?) r "
                "SEMI JOIN read_parquet(?) t USING (id) "
                "GROUP BY r.id HAVING count(*) <> 1)",
                [
                    [str(RAW / s["path"]) for s in source["shards"]],
                    str(release / "text/*.parquet"),
                ],
            ).fetchone()[0]
            if duplicates:
                raise ValueError(
                    f"{duplicates:,} approved IDs occur in multiple source shards"
                )
        (release / "documentation/text-manifest.json").write_text(
            json.dumps(
                {
                    "metadata_revision": BASE,
                    "staging_revision": SOURCE,
                    "upstream_source": source["upstream_source"],
                    "approved_ids_sha256": initial,
                    "selection": "all" if approved is None else "approved_ids",
                    "records": exported,
                    "files": inventory,
                },
                indent=2,
            )
            + "\n"
        )
        (release / "README.md").write_text(card(exported, source["records"]))
        release.rename(output)


def publish(release: Path) -> None:
    """Stage, verify and publish an approved release directory."""
    manifest_path = "documentation/text-manifest.json"
    manifest = json.loads((release / manifest_path).read_text())
    if manifest["metadata_revision"] != BASE or manifest["staging_revision"] != SOURCE:
        raise ValueError("Unexpected release revisions")
    if (
        not manifest["records"]
        or sum(r["rows"] for r in manifest["files"]) != manifest["records"]
    ):
        raise ValueError("Invalid release count")
    payload = {}
    for row in manifest["files"]:
        name = row["path"]
        path = release / name
        if Path(name).parent != Path("text") or path.suffix != ".parquet":
            raise ValueError(f"Unexpected payload path: {name}")
        if (
            name in payload
            or path.stat().st_size != row["bytes"]
            or digest(path) != row["sha256"]
        ):
            raise ValueError(f"Invalid local shard: {name}")
        payload[name] = row
    if (release / "README.md").read_text() != card(manifest["records"], 14_807_287):
        raise ValueError("Unexpected release card")
    api = HfApi()
    public = HfApi(token=False)
    branch = "ccfinance-text-" + digest(release / manifest_path)[:16]
    baseline = public.dataset_info(REPO, revision=BASE, files_metadata=True)
    metadata = json.loads(
        Path(
            hf_hub_download(
                REPO,
                "documentation/manifest.json",
                repo_type="dataset",
                revision=BASE,
                token=False,
            )
        ).read_text()
    )
    baseline_files = {item.rfilename: item for item in baseline.siblings}
    for row in metadata["files"]:
        item = baseline_files[row["path"]]
        if (
            not item.lfs
            or item.lfs.sha256 != row["sha256"]
            or item.size != row["bytes"]
        ):
            raise ValueError(f"Baseline manifest mismatch: {row['path']}")
    current = public.dataset_info(REPO)
    if current.private or current.gated:
        raise ValueError("Unexpected Hub access settings")
    if current.sha == BASE:
        api.create_branch(
            REPO, branch=branch, revision=BASE, repo_type="dataset", exist_ok=True
        )
    staged = api.dataset_info(REPO, revision=branch, files_metadata=True)
    if current.sha not in {BASE, staged.sha}:
        raise ValueError("Hub main moved; reconcile before publishing")
    siblings = {item.rfilename: item for item in staged.siblings}
    for name, item in siblings.items():
        if name in payload:
            if (
                not item.lfs
                or item.lfs.sha256 != payload[name]["sha256"]
                or item.size != payload[name]["bytes"]
            ):
                raise ValueError(f"Unexpected staged shard: {name}")
        elif name not in {"README.md", manifest_path} and item != baseline_files.get(
            name
        ):
            raise ValueError(f"Unexpected staged file: {name}")
    if baseline_files.keys() - siblings.keys():
        raise ValueError("Staged release dropped baseline files")
    head = staged.sha
    pending = sorted(payload.keys() - siblings.keys())
    for start in range(0, len(pending), 10):
        paths = pending[start : start + 10]
        head = api.create_commit(
            REPO,
            repo_type="dataset",
            revision=branch,
            parent_commit=head,
            operations=[CommitOperationAdd(p, release / p) for p in paths],
            commit_message="Add verified CCFinance text shards",
        ).oid
    docs = ["README.md", manifest_path]
    head = api.create_commit(
        REPO,
        repo_type="dataset",
        revision=branch,
        parent_commit=head,
        operations=[CommitOperationAdd(p, release / p) for p in docs],
        commit_message="Describe the CCFinance text release and its terms",
    ).oid
    verified = public.dataset_info(REPO, revision=head, files_metadata=True)
    by_name = {item.rfilename: item for item in verified.siblings}
    if by_name.keys() != baseline_files.keys() | payload.keys() | set(docs):
        raise ValueError("Unexpected files in staged release")
    for name, row in payload.items():
        item = by_name[name]
        if (
            not item.lfs
            or item.lfs.sha256 != row["sha256"]
            or item.size != row["bytes"]
        ):
            raise ValueError(f"Remote shard verification failed: {name}")
    for name, item in baseline_files.items():
        if name not in docs and by_name[name] != item:
            raise ValueError(f"Baseline file changed: {name}")
    for name in docs:
        remote = hf_hub_download(
            REPO, name, repo_type="dataset", revision=head, token=False
        )
        if digest(Path(remote)) != digest(release / name):
            raise ValueError(f"Staged documentation differs: {name}")
    current = public.dataset_info(REPO)
    if current.sha != head:
        if current.sha != BASE or current.private or current.gated:
            raise ValueError("Hub main moved or access settings changed")
        with TemporaryDirectory() as git_dir:

            def git(*args: str) -> None:
                subprocess.run(["git", "-C", git_dir, *args], check=True)  # noqa: S603, S607

            url = f"https://huggingface.co/datasets/{REPO}"
            git("init", "--bare", "--quiet")
            git("fetch", "--no-tags", url, f"refs/heads/{branch}")
            git("merge-base", "--is-ancestor", BASE, head)
            git(
                "push",
                f"--force-with-lease=refs/heads/main:{BASE}",
                url,
                f"{head}:refs/heads/main",
            )
    live = public.dataset_info(REPO)
    if live.sha != head or live.private or live.gated:
        raise ValueError("Anonymous public revision verification failed")
    for name, query in [
        (next(iter(payload)), "SELECT id, text FROM read_parquet(?) LIMIT 1"),
        (metadata["files"][0]["path"], "SELECT id FROM read_parquet(?) LIMIT 1"),
    ]:
        with TemporaryDirectory() as sample:
            shard = hf_hub_download(
                REPO,
                name,
                repo_type="dataset",
                revision=head,
                token=False,
                local_dir=sample,
            )
            with duckdb.connect() as con:
                if not con.execute(query, [shard]).fetchone():
                    raise ValueError(f"Public sample is empty: {name}")
    print(f"https://huggingface.co/datasets/{REPO}/tree/{head}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    builder = commands.add_parser("build")
    builder.add_argument("approved", type=Path)
    builder.add_argument("output", type=Path)
    publisher = commands.add_parser("publish")
    publisher.add_argument("release", type=Path)
    args = parser.parse_args()
    if args.command == "build":
        build(args.approved.resolve(), args.output.resolve())
    else:
        release = args.release.resolve()
        if not release.exists():
            build(None, release)
        publish(release)
