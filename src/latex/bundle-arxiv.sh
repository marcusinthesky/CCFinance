#!/usr/bin/env bash
set -euo pipefail

project=$(realpath "$1")
output="$project/build/arxiv"
mkdir -p "$output"
work=$(mktemp -d "$output/.bundle.XXXXXXXX")
trap 'rm -rf -- "$work"' EXIT
mkdir -p "$work/source/sections" "$work/unpacked"

cd "$work/source"
sed 's|{\.\./\.\./\.\./templates/ccfinance-manuscript}|{ccfinance-manuscript}|' \
  "$project/src/targets/arxiv.tex" > main.tex
cp "$project/../../templates/ccfinance-manuscript.sty" .
cp "$project/src/"{metadata.tex,body.tex,appendix.tex,refs.bib} .
cp "$project/src/sections/"*.tex sections/

compile() {
  pdflatex -no-shell-escape -interaction=nonstopmode -halt-on-error -recorder main.tex > compile.log || {
    tail -40 compile.log >&2
    return 1
  }
}

compile
bibtex main
# Include only the section files TeX actually read. Other submission targets
# and scratch files in the project are never copied into the tarball.
{
  printf '%s\n' main.tex metadata.tex body.tex appendix.tex refs.bib main.bbl ccfinance-manuscript.sty
  sed -nE 's|^INPUT (\./)?(sections/[^/]+\.tex)$|\2|p' main.fls
} | LC_ALL=C sort -u > "$work/files"
tar --mtime=@0 --owner=0 --group=0 --numeric-owner --mode=0644 \
  -cf - -T "$work/files" | gzip -n > "$work/arxiv.tar.gz"

cd "$work/unpacked"
tar -xzf "$work/arxiv.tar.gz"
compile
compile
compile
if rg -n 'Citation.+undefined|Reference.+undefined|There were undefined|multiply-defined|Multiply defined|Rerun to get' main.log; then
  echo 'Unresolved citations or cross-references in arXiv bundle' >&2
  exit 1
fi
mv "$work/arxiv.tar.gz" "$output/arxiv.tar.gz"
echo "Created $output/arxiv.tar.gz"
