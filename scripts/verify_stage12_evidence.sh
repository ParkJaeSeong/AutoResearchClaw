#!/bin/sh
set -eu

cd "$(dirname "$0")/.."
pytest -q tests/codex_native/test_stage12_trustworthy_evidence_integration.py
pytest -q tests/codex_native
pytest -q tests/performance/test_evidence_store_benchmark.py -m large_evidence
python3.11 -m compileall -q researchclaw tests/codex_native
ruff check researchclaw tests/codex_native
git diff --check
