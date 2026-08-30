#!/bin/sh
set -eu

new_probe_nonce() {
    nonce_path=$(mktemp "${TMPDIR:-/tmp}/stage12-python-nonce.XXXXXX")
    nonce_name=${nonce_path##*/}
    rm -f "$nonce_path"
    printf '%s-%s\n' "$nonce_name" "$$"
}

probe_python() {
    candidate=$1
    [ -x "$candidate" ] || return 1
    nonce=$(new_probe_nonce) || return 1
    probe_output=$(mktemp "${TMPDIR:-/tmp}/stage12-python-probe.XXXXXX") || return 1
    if ! (
        ulimit -f 8
        "$candidate" -c 'import sys, pytest
nonce = sys.argv[1]
if sys.version_info < (3, 11) or not sys.executable or not pytest.__version__ or not pytest.__file__:
    raise SystemExit(2)
fields = ("RC_STAGE12_PYTHON_V1", nonce, str(sys.version_info.major), str(sys.version_info.minor), sys.executable, pytest.__version__, pytest.__file__)
if any((not value) or "\t" in value or "\n" in value or "\r" in value for value in fields):
    raise SystemExit(3)
print("\t".join(fields))' "$nonce" >"$probe_output" 2>/dev/null
    ); then
        rm -f "$probe_output"
        return 1
    fi
    output_size=$(wc -c <"$probe_output")
    output_lines=$(wc -l <"$probe_output")
    if [ "$output_size" -gt 4096 ] || [ "$output_lines" -ne 1 ]; then
        rm -f "$probe_output"
        return 1
    fi
    tab=$(printf '\t')
    IFS="$tab" read -r tag echoed_nonce major minor canonical pytest_version pytest_module extra <"$probe_output" || {
        rm -f "$probe_output"
        return 1
    }
    rm -f "$probe_output"
    case "$major:$minor" in
        *[!0-9:]*|:*|*:) return 1 ;;
    esac
    if [ "$tag" != "RC_STAGE12_PYTHON_V1" ] \
        || [ "$echoed_nonce" != "$nonce" ] \
        || [ -n "$extra" ] \
        || [ -z "$pytest_version" ] \
        || [ -z "$pytest_module" ] \
        || [ "$major" -lt 3 ] \
        || { [ "$major" -eq 3 ] && [ "$minor" -lt 11 ]; }; then
        return 1
    fi
    case "$canonical" in
        /*) ;;
        *) return 1 ;;
    esac
    [ -x "$canonical" ] || return 1
    printf '%s\n' "$canonical"
}

validate_python() {
    candidate=$1
    canonical=$(probe_python "$candidate") || return 1
    confirmed=$(probe_python "$canonical") || return 1
    [ "$confirmed" = "$canonical" ] || return 1
    printf '%s\n' "$canonical"
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
        if canonical=$(validate_python "$explicit"); then
            printf '%s\n' "$canonical"
            return 0
        fi
        echo "PYTHON_BIN must be Python >=3.11 with pytest importable: $PYTHON_BIN" >&2
        return 1
    fi

    for project_candidate in .venv/bin/python venv/bin/python; do
        if canonical=$(validate_python "$project_candidate"); then
            printf '%s\n' "$canonical"
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
                                        if [ -n "$env_candidate" ] && canonical=$(validate_python "$env_candidate"); then
                                            printf '%s\n' "$canonical"
                                            return 0
                                        fi
                                        ;;
                                esac
                                ;;
                        esac
                        ;;
                    *)
                        if canonical=$(validate_python "$interpreter"); then
                            printf '%s\n' "$canonical"
                            return 0
                        fi
                        ;;
                esac
                ;;
        esac
    fi

    for command_name in python3 python; do
        candidate=$(resolve_command "$command_name" || true)
        if [ -n "$candidate" ] && canonical=$(validate_python "$candidate"); then
            printf '%s\n' "$canonical"
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
