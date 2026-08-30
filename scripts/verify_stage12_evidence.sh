#!/bin/sh
set -eu

cd "$(dirname "$0")/.."

if [ -z "${PYTHON_BIN:-}" ]; then
    pytest_path=$(command -v pytest)
    pytest_shebang=$(sed -n '1s/^#!//p' "$pytest_path")
    case "$pytest_shebang" in
        /*) PYTHON_BIN=$pytest_shebang ;;
        *) PYTHON_BIN=$(command -v python3) ;;
    esac
fi

run_mandatory_pytest() {
    result_log=$(mktemp "${TMPDIR:-/tmp}/stage12-pytest.XXXXXX")
    if ! "$PYTHON_BIN" -m pytest -q -ra "$@" >"$result_log" 2>&1; then
        cat "$result_log"
        rm -f "$result_log"
        return 1
    fi
    cat "$result_log"
    if grep -E '[0-9]+ (skipped|xfailed|xpassed)' "$result_log" >/dev/null; then
        echo "mandatory Stage-12 gate contained skipped/xfailed/xpassed tests" >&2
        rm -f "$result_log"
        return 1
    fi
    rm -f "$result_log"
}

run_mandatory_pytest tests/codex_native/test_stage12_trustworthy_evidence_integration.py
run_mandatory_pytest tests/codex_native
# The 1 GiB test remains excluded from ordinary pytest collection by its marker;
# this release gate opts in explicitly and treats it as mandatory.
run_mandatory_pytest tests/performance/test_evidence_store_benchmark.py -m large_evidence
"$PYTHON_BIN" -m compileall -q researchclaw tests/codex_native
ruff check researchclaw tests/codex_native
git diff --check
