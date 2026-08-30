import os
from pathlib import Path
import stat
import subprocess


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/verify_stage12_evidence.sh"


def _executable(path: Path, payload: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def _fake_python(path: Path, *, valid: bool) -> Path:
    return _executable(path, f"#!/bin/sh\nexit {0 if valid else 1}\n")


def _run(tmp_path: Path, *, python_bin: str | None = None):
    environment = os.environ.copy()
    environment["PATH"] = f"{tmp_path / 'bin'}:/usr/bin:/bin"
    if python_bin is None:
        environment.pop("PYTHON_BIN", None)
    else:
        environment["PYTHON_BIN"] = python_bin
    return subprocess.run(
        [str(SCRIPT), "--print-python"],
        cwd=ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )


def test_release_selector_accepts_explicit_python_path_with_spaces(tmp_path):
    candidate = _fake_python(tmp_path / "runtime with spaces/python", valid=True)
    completed = _run(tmp_path, python_bin=str(candidate))
    assert completed.returncode == 0
    assert completed.stdout.strip() == str(candidate)


def test_release_selector_rejects_invalid_explicit_python_without_fallback(tmp_path):
    candidate = _fake_python(tmp_path / "invalid-python", valid=False)
    completed = _run(tmp_path, python_bin=str(candidate))
    assert completed.returncode != 0
    assert "Python >=3.11 with pytest importable" in completed.stderr


def test_release_selector_resolves_env_python_shebang_by_probe(tmp_path):
    candidate = _fake_python(tmp_path / "bin/python3", valid=True)
    _executable(tmp_path / "bin/pytest", "#!/usr/bin/env python3\n")
    completed = _run(tmp_path)
    assert completed.returncode == 0
    assert completed.stdout.strip() == str(candidate)


def test_release_selector_accepts_valid_direct_absolute_shebang(tmp_path):
    candidate = _fake_python(tmp_path / "direct-python", valid=True)
    _executable(tmp_path / "bin/pytest", f"#!{candidate}\n")
    completed = _run(tmp_path)
    assert completed.returncode == 0
    assert completed.stdout.strip() == str(candidate)


def test_release_selector_ignores_wrapper_shebang_and_probes_python3(tmp_path):
    candidate = _fake_python(tmp_path / "bin/python3", valid=True)
    _executable(tmp_path / "bin/pytest", "#!/bin/sh\nexit 0\n")
    completed = _run(tmp_path)
    assert completed.returncode == 0
    assert completed.stdout.strip() == str(candidate)


def test_release_selector_supports_python_312_only_candidate(tmp_path):
    candidate = _fake_python(tmp_path / "bin/python3", valid=True)
    _fake_python(tmp_path / "bin/python", valid=False)
    completed = _run(tmp_path)
    assert completed.returncode == 0
    assert completed.stdout.strip() == str(candidate)


def test_release_selector_fails_clearly_when_no_candidate_is_supported(tmp_path):
    _fake_python(tmp_path / "bin/python3", valid=False)
    _fake_python(tmp_path / "bin/python", valid=False)
    _executable(tmp_path / "bin/pytest", "#!/bin/sh\nexit 0\n")
    completed = _run(tmp_path)
    assert completed.returncode != 0
    assert "no Python >=3.11 interpreter with pytest importable" in completed.stderr
