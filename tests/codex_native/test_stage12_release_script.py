import os
from pathlib import Path
import stat
import subprocess
import sys
import shlex


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/verify_stage12_evidence.sh"
REAL_PYTHON = sys.executable


def _executable(path: Path, payload: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def _fake_python(path: Path, *, valid: bool) -> Path:
    if valid:
        return _executable(
            path, f"#!/bin/sh\nexec {shlex.quote(REAL_PYTHON)} \"$@\"\n"
        )
    return _executable(path, "#!/bin/sh\nexit 1\n")


def _run(
    tmp_path: Path,
    *,
    python_bin: str | None = None,
    arguments: tuple[str, ...] = ("--print-python",),
):
    environment = os.environ.copy()
    environment["PATH"] = f"{tmp_path / 'bin'}:/usr/bin:/bin"
    if python_bin is None:
        environment.pop("PYTHON_BIN", None)
    else:
        environment["PYTHON_BIN"] = python_bin
    return subprocess.run(
        [str(SCRIPT), *arguments],
        cwd=ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )


def _validate_pytest_logs(
    tmp_path: Path,
    *,
    collection: str,
    execution: str,
):
    collection_log = tmp_path / "collection.log"
    execution_log = tmp_path / "execution.log"
    collection_log.write_text(collection, encoding="utf-8")
    execution_log.write_text(execution, encoding="utf-8")
    return _run(
        tmp_path,
        python_bin=REAL_PYTHON,
        arguments=(
            "--validate-pytest-logs",
            str(collection_log),
            str(execution_log),
            "tests/example.py::",
        ),
    )


def test_release_selector_accepts_explicit_python_path_with_spaces(tmp_path):
    candidate = _fake_python(tmp_path / "runtime with spaces/python", valid=True)
    completed = _run(tmp_path, python_bin=str(candidate))
    assert completed.returncode == 0
    assert completed.stdout.strip() == REAL_PYTHON


def test_release_selector_rejects_invalid_explicit_python_without_fallback(tmp_path):
    candidate = _fake_python(tmp_path / "invalid-python", valid=False)
    completed = _run(tmp_path, python_bin=str(candidate))
    assert completed.returncode != 0
    assert "Python >=3.11 with pytest importable" in completed.stderr


def test_release_selector_resolves_env_python_shebang_by_probe(tmp_path):
    _fake_python(tmp_path / "bin/python3", valid=True)
    _executable(tmp_path / "bin/pytest", "#!/usr/bin/env python3\n")
    completed = _run(tmp_path)
    assert completed.returncode == 0
    assert completed.stdout.strip() == REAL_PYTHON


def test_release_selector_accepts_valid_direct_absolute_shebang(tmp_path):
    candidate = _fake_python(tmp_path / "direct-python", valid=True)
    _executable(tmp_path / "bin/pytest", f"#!{candidate}\n")
    completed = _run(tmp_path)
    assert completed.returncode == 0
    assert completed.stdout.strip() == REAL_PYTHON


def test_release_selector_ignores_wrapper_shebang_and_probes_python3(tmp_path):
    _fake_python(tmp_path / "bin/python3", valid=True)
    _executable(tmp_path / "bin/pytest", "#!/bin/sh\nexit 0\n")
    completed = _run(tmp_path)
    assert completed.returncode == 0
    assert completed.stdout.strip() == REAL_PYTHON


def test_release_selector_supports_python_312_only_candidate(tmp_path):
    _fake_python(tmp_path / "bin/python3", valid=True)
    _fake_python(tmp_path / "bin/python", valid=False)
    completed = _run(tmp_path)
    assert completed.returncode == 0
    assert completed.stdout.strip() == REAL_PYTHON


def test_release_selector_fails_clearly_when_no_candidate_is_supported(tmp_path):
    _fake_python(tmp_path / "bin/python3", valid=False)
    _fake_python(tmp_path / "bin/python", valid=False)
    _executable(tmp_path / "bin/pytest", "#!/bin/sh\nexit 0\n")
    completed = _run(tmp_path)
    assert completed.returncode != 0
    assert "no Python >=3.11 interpreter with pytest importable" in completed.stderr


def test_release_selector_rejects_zero_exit_noop_wrapper(tmp_path):
    candidate = _executable(tmp_path / "noop", "#!/bin/sh\nexit 0\n")
    completed = _run(tmp_path, python_bin=str(candidate))
    assert completed.returncode != 0


def test_release_selector_rejects_fixed_spoof_and_wrong_nonce(tmp_path):
    candidate = _executable(
        tmp_path / "fixed-spoof",
        "#!/bin/sh\nprintf 'RC_STAGE12_PYTHON_V1\\twrong-nonce\\t3\\t12\\t/bin/sh\\t8.0\\t/fake.py\\n'\n",
    )
    completed = _run(tmp_path, python_bin=str(candidate))
    assert completed.returncode != 0


def test_release_selector_rejects_malformed_probe_output(tmp_path):
    candidate = _executable(
        tmp_path / "malformed", "#!/bin/sh\nprintf 'not-the-protocol\\n'\n"
    )
    completed = _run(tmp_path, python_bin=str(candidate))
    assert completed.returncode != 0


def test_release_selector_rejects_huge_probe_output(tmp_path):
    candidate = _executable(
        tmp_path / "huge",
        "#!/bin/sh\nwhile :; do printf '0123456789abcdef'; done\n",
    )
    completed = _run(tmp_path, python_bin=str(candidate))
    assert completed.returncode != 0


def test_responsive_spoof_cannot_satisfy_mandatory_pytest_output_gate(tmp_path):
    candidate = tmp_path / "responsive-spoof"
    quoted = shlex.quote(str(candidate))
    _executable(
        candidate,
        "#!/bin/sh\n"
        "if [ \"$1\" = \"-c\" ]; then\n"
        f"  printf 'RC_STAGE12_PYTHON_V1\\t%s\\t3\\t12\\t%s\\t8.0\\t/fake.py\\n' \"$3\" {quoted}\n"
        "  exit 0\n"
        "fi\n"
        "exit 0\n",
    )
    selected = _run(tmp_path, python_bin=str(candidate))
    assert selected.returncode == 0
    assert selected.stdout.strip() == str(candidate)

    completed = _run(tmp_path, python_bin=str(candidate), arguments=())
    assert completed.returncode != 0
    assert "pytest collection was missing or malformed" in completed.stderr


def test_release_contract_documents_trusted_executable_boundary():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    script = SCRIPT.read_text(encoding="utf-8")
    assert "trusted, operator-controlled" in readme
    assert "cannot authenticate a responsive same-user executable" in readme
    assert "validates Python/pytest" in script
    assert "cannot authenticate" in script


def test_release_parser_accepts_equal_exact_collection_and_pass_counts(tmp_path):
    completed = _validate_pytest_logs(
        tmp_path,
        collection=(
            "tests/example.py::test_one\n"
            "tests/example.py::test_two\n"
            "2 tests collected in 0.01s\n"
        ),
        execution=".. [100%]\n2 passed in 0.02s\n",
    )
    assert completed.returncode == 0
    assert completed.stdout.strip() == "2 passed in 0.02s"


def test_release_parser_accepts_singular_collection_and_long_timing(tmp_path):
    completed = _validate_pytest_logs(
        tmp_path,
        collection="tests/example.py::test_one\n1 test collected in 0.01s\n",
        execution=". [100%]\n1 passed in 61.00s (0:01:01)\n",
    )
    assert completed.returncode == 0
    assert completed.stdout.strip() == "1 passed in 61.00s (0:01:01)"


def test_release_parser_rejects_collection_execution_count_mismatch(tmp_path):
    completed = _validate_pytest_logs(
        tmp_path,
        collection="tests/example.py::test_one\n2 tests collected in 0.01s\n",
        execution=". [100%]\n1 passed in 0.02s\n",
    )
    assert completed.returncode != 0
    assert "collected/passed count mismatch" in completed.stderr


def test_release_parser_rejects_collection_summary_suffix(tmp_path):
    completed = _validate_pytest_logs(
        tmp_path,
        collection="tests/example.py::test_one\n2 tests collected in 0.01s trailing\n",
        execution="2 passed in 0.02s\n",
    )
    assert completed.returncode != 0
    assert "missing, malformed, or ambiguous" in completed.stderr


def test_release_parser_rejects_execution_summary_suffix(tmp_path):
    completed = _validate_pytest_logs(
        tmp_path,
        collection="tests/example.py::test_one\n2 tests collected in 0.01s\n",
        execution="2 passed in 0.02s trailing\n",
    )
    assert completed.returncode != 0
    assert "missing, malformed, or ambiguous" in completed.stderr


def test_release_parser_rejects_execution_summary_prefix(tmp_path):
    completed = _validate_pytest_logs(
        tmp_path,
        collection="tests/example.py::test_one\n2 tests collected in 0.01s\n",
        execution="prefix 2 passed in 0.02s\n",
    )
    assert completed.returncode != 0
    assert "missing, malformed, or ambiguous" in completed.stderr


def test_release_parser_rejects_combined_outcome_summary(tmp_path):
    completed = _validate_pytest_logs(
        tmp_path,
        collection="tests/example.py::test_one\n2 tests collected in 0.01s\n",
        execution="2 passed, 1 skipped in 0.02s\n",
    )
    assert completed.returncode != 0
    assert "missing, malformed, or ambiguous" in completed.stderr


def test_release_parser_rejects_duplicate_summary_lines(tmp_path):
    completed = _validate_pytest_logs(
        tmp_path,
        collection="tests/example.py::test_one\n2 tests collected in 0.01s\n",
        execution="2 passed in 0.01s\n2 passed in 0.02s\n",
    )
    assert completed.returncode != 0
    assert "missing, malformed, or ambiguous" in completed.stderr


def test_release_parser_rejects_early_successful_subset_execution(tmp_path):
    completed = _validate_pytest_logs(
        tmp_path,
        collection="tests/example.py::test_one\n4 tests collected in 0.01s\n",
        execution="1 passed in 0.01s\n",
    )
    assert completed.returncode != 0
    assert "collected/passed count mismatch" in completed.stderr
