#!/bin/sh
set -eu

validate_python() {
    candidate=$1
    [ -x "$candidate" ] || return 1
    "$candidate" -c 'import sys, pytest; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' \
        >/dev/null 2>&1
}

resolve_command() {
    command -v "$1" 2>/dev/null || return 1
}

select_python() {
    if [ -n "${PYTHON_BIN:-}" ]; then
        explicit=$PYTHON_BIN
        case "$explicit" in
            */*) ;;
            *) explicit=$(resolve_command "$explicit") || {
                echo "PYTHON_BIN is not an executable Python command: $PYTHON_BIN" >&2
                return 1
            } ;;
        esac
        if validate_python "$explicit"; then
            printf '%s\n' "$explicit"
            return 0
        fi
        echo "PYTHON_BIN must be Python >=3.11 with pytest importable: $PYTHON_BIN" >&2
        return 1
    fi

    for project_candidate in .venv/bin/python venv/bin/python; do
        if validate_python "$project_candidate"; then
            printf '%s\n' "$project_candidate"
            return 0
        fi
    done

    pytest_path=$(resolve_command pytest || true)
    if [ -n "$pytest_path" ] && IFS= read -r shebang <"$pytest_path"; then
        case "$shebang" in
            '#!'/*)
                interpreter=${shebang#\#!}
                case "$interpreter" in
                    *' '*|*"	"*)
                        case "$interpreter" in
                            '/usr/bin/env '*)
                                env_name=${interpreter#'/usr/bin/env '}
                                case "$env_name" in
                                    *' '*|*"	"*|'') ;;
                                    *)
                                        env_candidate=$(resolve_command "$env_name" || true)
                                        if [ -n "$env_candidate" ] && validate_python "$env_candidate"; then
                                            printf '%s\n' "$env_candidate"
                                            return 0
                                        fi
                                        ;;
                                esac
                                ;;
                        esac
                        ;;
                    *)
                        if validate_python "$interpreter"; then
                            printf '%s\n' "$interpreter"
                            return 0
                        fi
                        ;;
                esac
                ;;
        esac
    fi

    for command_name in python3 python; do
        candidate=$(resolve_command "$command_name" || true)
        if [ -n "$candidate" ] && validate_python "$candidate"; then
            printf '%s\n' "$candidate"
            return 0
        fi
    done
    echo "no Python >=3.11 interpreter with pytest importable was found" >&2
    return 1
}

cd "$(dirname "$0")/.."
PYTHON_BIN=$(select_python)
if [ "${1:-}" = "--print-python" ]; then
    printf '%s\n' "$PYTHON_BIN"
    exit 0
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
