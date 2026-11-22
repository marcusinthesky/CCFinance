set shell := ["bash", "-euo", "pipefail", "-c"]
set positional-arguments

mod python 'src/python/justfile'
mod latex 'src/latex/justfile'
mod agents '.agents/justfile'
mod inference 'infra/inference/justfile'
workflow := "env -u PYTHONPATH -u PYTHONHOME -u VIRTUAL_ENV uv run --offline --frozen --script src/python/scripts/workflow/script.py"

# Discover this project's commands.
default:
    @just --list

# Prepare locked dependencies and Git hooks (uses the network).
setup:
    env -u PYTHONPATH -u PYTHONHOME -u VIRTUAL_ENV uv run --frozen --script src/python/scripts/workflow/script.py prepare
    just python::setup
    just latex::setup
    just agents::apply
    prek install

# Check source, views and selected languages without repairing files.
check:
    bash infra/nix/check.sh
    {{ workflow }} check
    just python::check
    just inference::lint
    just latex::check
    just data-check
    just semflow-check
    just changelog-check
    just skills-check
    just agents::check

# Run the selected language tests.
test:
    just python::test
    just latex::test

# Explicitly format sources.
fmt:
    git ls-files -z --cached --others --exclude-standard | while IFS= read -r -d '' file; do case "$file" in justfile|*/justfile|Justfile|*/Justfile|*.just) just --justfile "$file" --fmt --unstable ;; esac; done
    nixfmt devenv.nix infra/nix/devenv.nix infra/nix/pkgs/schematter.nix infra/nix/pkgs/agentsync.nix
    rumdl fmt .
    # DVC's YAML emitter can leave trailing spaces when wrapping scalar values.
    if [[ -f dvc.lock ]]; then sed -i 's/[[:blank:]]*$//' dvc.lock; fi
    just python::fmt
    just inference::fmt
    just latex::fmt

# Check external links online.
links:
    git ls-files -z '*.md' | xargs -0 -r lychee --config lychee.toml --no-progress

# Run root-level DVC using the locked Python environment.
dvc *args:
    env -u PYTHONPATH -u PYTHONHOME -u VIRTUAL_ENV uv run --project src/python --offline --frozen dvc "$@"

# Build the metadata-only Hugging Face release from restored artifacts.
release-metadata output:
    env -u PYTHONPATH -u PYTHONHOME -u VIRTUAL_ENV uv run --frozen --script src/python/scripts/hub_release/build.py "$1"

# Validate DVC metadata without fetching data.
data-check:
    just dvc status
    just dvc dag

# Refresh generated planning and reference views.
sync:
    {{ workflow }} sync

# Validate document schemas, links and generated views.
context-check:
    {{ workflow }} check

# Create a plan without overwriting existing content.
plan-new slug title:
    {{ workflow }} plan-new "$1" --title "$2"

# Create a task inside an existing plan or task.
task-new parent slug title:
    {{ workflow }} task-new "$1" "$2" --title "$3"

# Create a local reference record with its directory as citation key.
reference-new key title:
    {{ workflow }} reference-new "$1" --title "$2"

# Validate the repository changelog structure and change categories.
changelog-check:
    schematter validate --schema infra/schemas/documents/changelog.document-schema.yaml CHANGELOG.md

# Check semantic fingerprints once DVC has executable stages.
semflow-check:
    if env -u PYTHONPATH -u PYTHONHOME -u VIRTUAL_ENV uv run --project src/python --offline --frozen python -c 'import pathlib, sys, yaml; from semflow.config import load_config; load_config(); doc = yaml.safe_load(pathlib.Path("dvc.yaml").read_text()); sys.exit(0 if isinstance(doc, dict) and doc.get("stages") == {} else 1)'; then echo 'Semflow: no DVC stages to instrument.'; else env -u PYTHONPATH -u PYTHONHOME -u VIRTUAL_ENV uv run --project src/python --offline --frozen --all-packages semflow check; fi

# Preview the semantic dependency changes before applying them.
semflow-patch:
    env -u PYTHONPATH -u PYTHONHOME -u VIRTUAL_ENV uv run --project src/python --offline --frozen --all-packages semflow patch

# Apply reviewed DVC and semantic fingerprint changes.
semflow-apply:
    env -u PYTHONPATH -u PYTHONHOME -u VIRTUAL_ENV uv run --project src/python --offline --frozen --all-packages semflow patch --apply

# Refresh existing semantic fingerprints without editing the DVC graph.
semflow-refresh:
    env -u PYTHONPATH -u PYTHONHOME -u VIRTUAL_ENV uv run --project src/python --offline --frozen --all-packages semflow refresh --apply

# Validate repository-owned skill documents and their directory names.
skills-check:
    git ls-files -z --cached --others --exclude-standard -- ':(glob)**/SKILL.md' 'SKILL.md' | while IFS= read -r -d '' file; do [[ -f "$file" ]] || continue; schematter validate --schema infra/schemas/documents/skill.document-schema.yaml "$file"; awk 'END { if (NR > 500) { print FILENAME ": exceeds 500 lines" > "/dev/stderr"; exit 1 } }' "$file"; env -u PYTHONPATH -u PYTHONHOME -u VIRTUAL_ENV uv run --project src/python --offline --frozen python -c 'import pathlib, re, sys, yaml; p = pathlib.Path(sys.argv[1]); frontmatter = re.split(r"(?m)^---[ \t]*\r?$", p.read_text(), maxsplit=2)[1]; name = yaml.safe_load(frontmatter)["name"]; sys.exit(0 if name == p.parent.name else f"{p}: name {name!r} must match parent directory {p.parent.name!r}")' "$file"; done
