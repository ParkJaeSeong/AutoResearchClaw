import hashlib
import json
import math
import subprocess
import sys

import pytest

from researchclaw.core.experiment_package_contract import (
    EXPERIMENT_PACKAGE_CONTRACT_PATH,
    SELF_TEST_REPORT_PATH,
    ValidatedExperimentPackage,
    validate_experiment_package_contract,
    validate_registered_self_test,
)
from tests.codex_native.helpers import build_known_answer_experiment_package


def _contract_path(project):
    return project.root / EXPERIMENT_PACKAGE_CONTRACT_PATH


def _load_contract(project):
    return json.loads(_contract_path(project).read_text(encoding="utf-8"))


def _write_contract(project, payload):
    _contract_path(project).write_text(
        json.dumps(payload, sort_keys=True, allow_nan=True) + "\n", encoding="utf-8"
    )


def _replace_main(project, source):
    main_path = project.root / "experiment/code/main.py"
    main_path.write_text(source, encoding="utf-8")
    manifest_path = project.root / "experiment/package_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"][0]["sha256"] = hashlib.sha256(source.encode("utf-8")).hexdigest()
    manifest_path.write_text(json.dumps(manifest, sort_keys=True) + "\n", encoding="utf-8")


def _write_self_test_report(project, package, **overrides):
    fixture_path = project.root / "experiment/self_test_fixture.json"
    payload = {
        "schema_version": 1,
        "package_contract": {
            "path": EXPERIMENT_PACKAGE_CONTRACT_PATH,
            "sha256": package.contract_sha256,
        },
        "package_manifest": {
            "path": "experiment/package_manifest.json",
            "sha256": hashlib.sha256(
                (project.root / "experiment/package_manifest.json").read_bytes()
            ).hexdigest(),
        },
        "entry_point": {
            "path": "experiment/code/main.py",
            "sha256": hashlib.sha256(
                (project.root / "experiment/code/main.py").read_bytes()
            ).hexdigest(),
        },
        "package_files": [
            {"path": entry["path"], "sha256": entry["sha256"]}
            for entry in json.loads(
                (project.root / "experiment/package_manifest.json").read_text(encoding="utf-8")
            )["files"]
        ],
        "fixture": {
            "path": "experiment/self_test_fixture.json",
            "sha256": hashlib.sha256(fixture_path.read_bytes()).hexdigest(),
        },
        "environment_fingerprint": "a" * 64,
        "metrics": [
            {"name": "mae", "actual": 0.5, "expected": 0.5, "tolerance": 0.0}
        ],
        "passed": True,
        "development_only": True,
    }
    payload.update(overrides)
    report_path = project.root / SELF_TEST_REPORT_PATH
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(payload, sort_keys=True, allow_nan=True) + "\n", encoding="utf-8"
    )
    return report_path


def test_package_contract_binds_metric_to_known_answer_implementation(tmp_path):
    project = build_known_answer_experiment_package(tmp_path / "project")

    validated = validate_experiment_package_contract(project)

    assert dict(validated.metric_entrypoints) == {
        "mae": "experiment.code.main:mean_absolute_error"
    }
    assert validated.self_test_argv[-1] == "--self-test"
    assert validated.self_test_argv != validated.execution_argv


@pytest.mark.parametrize(
    ("mutate", "error"),
    [
        (
            lambda contract: contract["metrics"][0].update(
                {"implementation": "experiment.code.main:missing"}
            ),
            "metric implementation",
        ),
        (lambda contract: contract.update({"extra": True}), "undeclared fields"),
        (
            lambda contract: contract.update(
                {"metrics": [*contract["metrics"], dict(contract["metrics"][0])]}
            ),
            "metric names must be unique",
        ),
        (
            lambda contract: contract["self_test"]["expected_metrics"][0].update(
                {"expected": math.inf}
            ),
            "finite",
        ),
        (
            lambda contract: contract["self_test"]["expected_metrics"][0].update(
                {"tolerance": math.nan}
            ),
            "finite",
        ),
        (
            lambda contract: contract["self_test"].update(
                {"fixture_path": "experiment/empty_fixture.json"}
            ),
            "fixture",
        ),
        (
            lambda contract: contract["execution"].update(
                {"argv_suffix": list(contract["self_test"]["argv_suffix"])}
            ),
            "distinct",
        ),
    ],
)
def test_package_contract_rejects_closed_contract_failures(tmp_path, mutate, error):
    project = build_known_answer_experiment_package(tmp_path / "project")
    contract = _load_contract(project)
    mutate(contract)
    if contract["self_test"]["fixture_path"] == "experiment/empty_fixture.json":
        (project.root / "experiment/empty_fixture.json").write_text("{}\n", encoding="utf-8")
    _write_contract(project, contract)

    with pytest.raises(ValueError, match=error):
        validate_experiment_package_contract(project)


@pytest.mark.parametrize(
    "replacement",
    [
        "    return float(len(raw_bytes))\n",
        "    return float(Path('experiment/self_test_fixture.json').stat().st_size)\n",
        "    return float(os.path.getsize('experiment/self_test_fixture.json'))\n",
    ],
)
def test_package_contract_rejects_input_or_file_size_metric_proxies(tmp_path, replacement):
    project = build_known_answer_experiment_package(tmp_path / "project")
    main_path = project.root / "experiment/code/main.py"
    source = main_path.read_text(encoding="utf-8")
    source = source.replace(
        "    return sum(abs(a - b) for a, b in zip(targets, predictions, strict=True)) / len(targets)\n",
        replacement,
    )
    if "Path(" in replacement:
        source = "from pathlib import Path\n" + source
    if "os.path" in replacement:
        source = "import os\n" + source
    _replace_main(project, source)

    with pytest.raises(ValueError, match="size proxy"):
        validate_experiment_package_contract(project)


def test_package_contract_rejects_placeholder_fallback_marked_evidence_eligible(tmp_path):
    project = build_known_answer_experiment_package(tmp_path / "project")
    main_path = project.root / "experiment/code/main.py"
    _replace_main(
        project,
        main_path.read_text(encoding="utf-8")
        + "\ndef placeholder_fallback() -> dict[str, object]:\n"
        + "    return {'mae': 0.5, 'evidence_eligible': True}\n"
        + "\ndef run_placeholder() -> dict[str, object]:\n"
        + "    return placeholder_fallback()\n",
    )

    with pytest.raises(ValueError, match="fallback"):
        validate_experiment_package_contract(project)


def test_registered_self_test_is_closed_current_and_non_mutating(tmp_path):
    project = build_known_answer_experiment_package(tmp_path / "project")
    package = validate_experiment_package_contract(project)
    report_path = _write_self_test_report(project, package)
    original_state = project.state

    artifact = validate_registered_self_test(project, package)

    assert artifact.path == SELF_TEST_REPORT_PATH
    assert artifact.sha256 == hashlib.sha256(report_path.read_bytes()).hexdigest()
    assert artifact.size == report_path.stat().st_size
    assert project.state == original_state


@pytest.mark.parametrize(
    ("overrides", "error"),
    [
        ({"passed": False}, "passed"),
        ({"development_only": False}, "development_only"),
        ({"environment_fingerprint": "A" * 64}, "environment fingerprint"),
        ({"metrics": []}, "metric set"),
        (
            {"metrics": [{"name": "mae", "actual": 0.6, "expected": 0.5, "tolerance": 0.0}]},
            "does not match",
        ),
        (
            {"metrics": [{"name": "mae", "actual": math.inf, "expected": 0.5, "tolerance": 0.0}]},
            "finite",
        ),
    ],
)
def test_registered_self_test_rejects_invalid_external_report(tmp_path, overrides, error):
    project = build_known_answer_experiment_package(tmp_path / "project")
    package = validate_experiment_package_contract(project)
    _write_self_test_report(project, package, **overrides)

    with pytest.raises(ValueError, match=error):
        validate_registered_self_test(project, package)


def test_registered_self_test_rejects_a_manifest_bound_metric_change(tmp_path):
    project = build_known_answer_experiment_package(tmp_path / "project")
    package = validate_experiment_package_contract(project)
    _write_self_test_report(project, package)
    source = (project.root / "experiment/code/main.py").read_text(encoding="utf-8")
    _replace_main(
        project,
        source.replace(
            "    return sum(abs(a - b) for a, b in zip(targets, predictions, strict=True)) / len(targets)\n",
            "    return 0.0\n",
        ),
    )

    with pytest.raises(ValueError, match="package_manifest|package changed"):
        validate_registered_self_test(project, package)


def test_registered_self_test_rejects_a_manifest_declared_file_change(tmp_path):
    project = build_known_answer_experiment_package(tmp_path / "project")
    package = validate_experiment_package_contract(project)
    _write_self_test_report(project, package)
    (project.root / "experiment/code/config.json").write_text(
        '{"changed": true}\n', encoding="utf-8"
    )

    with pytest.raises(ValueError, match="package manifest identity"):
        validate_registered_self_test(project, package)


@pytest.mark.parametrize(
    "replacement",
    [
        "    probe = Path('experiment/self_test_fixture.json')\n    return probe.stat()[6]\n",
        "    return size_alias()\n\n\ndef size_helper() -> float:\n    probe = Path('experiment/self_test_fixture.json')\n    return float(probe.stat().st_size)\n\n\nsize_alias = size_helper\n",
    ],
)
def test_package_contract_rejects_subscripted_or_aliased_size_proxies(tmp_path, replacement):
    project = build_known_answer_experiment_package(tmp_path / "project")
    source = (project.root / "experiment/code/main.py").read_text(encoding="utf-8")
    _replace_main(
        project,
        source.replace(
            "    return sum(abs(a - b) for a, b in zip(targets, predictions, strict=True)) / len(targets)\n",
            replacement,
        ),
    )

    with pytest.raises(ValueError, match="size proxy"):
        validate_experiment_package_contract(project)


def test_package_contract_rejects_indirect_dict_fallback_evidence(tmp_path):
    project = build_known_answer_experiment_package(tmp_path / "project")
    source = (project.root / "experiment/code/main.py").read_text(encoding="utf-8")
    _replace_main(
        project,
        source
        + "\ndef placeholder_fallback() -> dict[str, object]:\n"
        + "    return build_placeholder_output()\n"
        + "\ndef build_placeholder_output() -> dict[str, object]:\n"
        + "    return dict(mae=0.5, evidence_eligible=True)\n",
    )

    with pytest.raises(ValueError, match="fallback"):
        validate_experiment_package_contract(project)


@pytest.mark.parametrize("target", ["self_test", "execution"])
def test_package_contract_rejects_duplicate_config_flags(tmp_path, target):
    project = build_known_answer_experiment_package(tmp_path / "project")
    contract = _load_contract(project)
    contract[target]["argv_suffix"] = [
        "--config",
        "experiment/code/config.json",
        "--config",
        "experiment/code/self_test_config.json",
        *(["--self-test"] if target == "self_test" else []),
    ]
    _write_contract(project, contract)

    with pytest.raises(ValueError, match="exactly one --config"):
        validate_experiment_package_contract(project)


@pytest.mark.parametrize(
    ("fixture_bytes", "error"),
    [
        (b'{"targets": [], "targets": []}\n', "JSON keys must be unique"),
        (b'{"payload": "' + b"x" * (65 * 1024) + b'"}\n', "fixture exceeds the bound"),
    ],
)
def test_package_contract_rejects_nonclosed_or_oversized_fixture(tmp_path, fixture_bytes, error):
    project = build_known_answer_experiment_package(tmp_path / "project")
    (project.root / "experiment/self_test_fixture.json").write_bytes(fixture_bytes)

    with pytest.raises(ValueError, match=error):
        validate_experiment_package_contract(project)


@pytest.mark.parametrize("field", ["contract", "report"])
def test_package_contract_rejects_boolean_schema_version(tmp_path, field):
    project = build_known_answer_experiment_package(tmp_path / "project")
    if field == "contract":
        contract = _load_contract(project)
        contract["schema_version"] = True
        _write_contract(project, contract)
        with pytest.raises(ValueError, match="schema_version"):
            validate_experiment_package_contract(project)
        return
    package = validate_experiment_package_contract(project)
    _write_self_test_report(project, package, schema_version=True)

    with pytest.raises(ValueError, match="schema_version"):
        validate_registered_self_test(project, package)


def test_package_contract_rejects_self_test_actual_hard_coded_away_from_metric(tmp_path):
    project = build_known_answer_experiment_package(tmp_path / "project")
    source = (project.root / "experiment/code/main.py").read_text(encoding="utf-8")
    _replace_main(project, source.replace('"actual": result["mae"]', '"actual": 0.5'))

    with pytest.raises(ValueError, match="self-test adapter"):
        validate_experiment_package_contract(project)


def test_known_answer_entrypoint_writes_only_its_mode_specific_output(tmp_path):
    project = build_known_answer_experiment_package(tmp_path / "project")
    command = [sys.executable, "experiment/code/main.py"]
    self_test = subprocess.run(
        [*command, "--config", "experiment/code/self_test_config.json", "--self-test"],
        cwd=project.root,
        check=True,
        capture_output=True,
        text=True,
    )

    assert self_test.returncode == 0
    assert (project.root / SELF_TEST_REPORT_PATH).is_file()
    assert not (project.root / "experiment/results.json").exists()
    (project.root / SELF_TEST_REPORT_PATH).unlink()
    execution = subprocess.run(
        [*command, "--config", "experiment/code/config.json"],
        cwd=project.root,
        check=True,
        capture_output=True,
        text=True,
    )

    assert execution.returncode == 0
    assert (project.root / "experiment/results.json").is_file()
    assert not (project.root / SELF_TEST_REPORT_PATH).exists()


def test_validated_experiment_package_keeps_the_exact_public_field_contract():
    assert tuple(ValidatedExperimentPackage.__dataclass_fields__) == (
        "contract_sha256",
        "metric_entrypoints",
        "self_test_argv",
        "execution_argv",
    )


def test_package_contract_rejects_a_local_alias_before_later_reassignment(tmp_path):
    project = build_known_answer_experiment_package(tmp_path / "project")
    source = (project.root / "experiment/code/main.py").read_text(encoding="utf-8")
    replacement = '''    size_alias = size_proxy
    value = size_alias()
    size_alias = safe_metric
    return value
'''
    source = source.replace(
        "    return sum(abs(a - b) for a, b in zip(targets, predictions, strict=True)) / len(targets)\n",
        replacement,
    ) + '''

def size_proxy() -> float:
    probe = Path("experiment/self_test_fixture.json")
    return float(probe.stat()[6])


def safe_metric() -> float:
    return 0.5
'''
    _replace_main(project, source)

    with pytest.raises(ValueError, match="size proxy|callable alias"):
        validate_experiment_package_contract(project)


def test_package_contract_rejects_a_reassigned_local_callable_alias(tmp_path):
    project = build_known_answer_experiment_package(tmp_path / "project")
    source = (project.root / "experiment/code/main.py").read_text(encoding="utf-8")
    replacement = '''    size_alias = size_proxy
    size_alias = safe_metric
    return size_alias()
'''
    source = source.replace(
        "    return sum(abs(a - b) for a, b in zip(targets, predictions, strict=True)) / len(targets)\n",
        replacement,
    ) + '''

def size_proxy() -> float:
    return 0.0


def safe_metric() -> float:
    return 0.5
'''
    _replace_main(project, source)

    with pytest.raises(ValueError, match="callable alias"):
        validate_experiment_package_contract(project)


def test_package_contract_rejects_a_dict_alias_evidence_fallback(tmp_path):
    project = build_known_answer_experiment_package(tmp_path / "project")
    source = (project.root / "experiment/code/main.py").read_text(encoding="utf-8")
    _replace_main(
        project,
        source
        + '''
dict_alias = dict


def placeholder_fallback() -> dict[str, object]:
    return dict_alias(mae=0.5, evidence_eligible=True)
''',
    )

    with pytest.raises(ValueError, match="fallback|callable alias"):
        validate_experiment_package_contract(project)


def test_package_contract_rejects_a_dead_decoy_metric_record(tmp_path):
    project = build_known_answer_experiment_package(tmp_path / "project")
    source = (project.root / "experiment/code/main.py").read_text(encoding="utf-8")
    source = source.replace(
        '        report = {\n',
        '        decoy = {"name": "mae", "actual": result["mae"]}\n'
        '        report = {\n',
    )
    _replace_main(project, source)

    with pytest.raises(ValueError, match="self-test adapter"):
        validate_experiment_package_contract(project)


def test_package_contract_rejects_metric_provenance_overwritten_before_report_write(tmp_path):
    project = build_known_answer_experiment_package(tmp_path / "project")
    source = (project.root / "experiment/code/main.py").read_text(encoding="utf-8")
    source = source.replace(
        '        report = {\n',
        '        actual_value = result["mae"]\n'
        '        actual_value = 0.5\n'
        '        report = {\n',
    ).replace('"actual": result["mae"]', '"actual": actual_value')
    _replace_main(project, source)

    with pytest.raises(ValueError, match="self-test adapter"):
        validate_experiment_package_contract(project)


def test_package_contract_rejects_ambiguous_self_test_provenance_branch(tmp_path):
    project = build_known_answer_experiment_package(tmp_path / "project")
    source = (project.root / "experiment/code/main.py").read_text(encoding="utf-8")
    source = source.replace(
        '        report = {\n',
        '        if config:\n'
        '            result["mae"] = result["mae"]\n'
        '        report = {\n',
    )
    _replace_main(project, source)

    with pytest.raises(ValueError, match="self-test adapter"):
        validate_experiment_package_contract(project)


def test_package_contract_rejects_multi_hop_local_size_proxy_alias(tmp_path):
    project = build_known_answer_experiment_package(tmp_path / "project")
    source = (project.root / "experiment/code/main.py").read_text(encoding="utf-8")
    source = source.replace(
        "    return sum(abs(a - b) for a, b in zip(targets, predictions, strict=True)) / len(targets)\n",
        "    first = size_proxy\n    second = first\n    return second()\n",
    ) + '''

def size_proxy() -> float:
    probe = Path("experiment/self_test_fixture.json")
    return float(probe.stat().st_size)
'''
    _replace_main(project, source)

    with pytest.raises(ValueError, match="size proxy|callable alias"):
        validate_experiment_package_contract(project)


def test_package_contract_rejects_size_proxy_despite_cross_function_shadow(tmp_path):
    project = build_known_answer_experiment_package(tmp_path / "project")
    source = (project.root / "experiment/code/main.py").read_text(encoding="utf-8")
    source = source.replace(
        "    return sum(abs(a - b) for a, b in zip(targets, predictions, strict=True)) / len(targets)\n",
        "    return size_proxy()\n",
    ) + '''

def size_proxy() -> float:
    probe = Path("experiment/self_test_fixture.json")
    return float(probe.stat().st_size)


def unrelated_shadow() -> dict[str, object]:
    size_proxy = dict
    return size_proxy(ok=True)
'''
    _replace_main(project, source)

    with pytest.raises(ValueError, match="size proxy"):
        validate_experiment_package_contract(project)


def test_package_contract_rejects_multi_hop_local_dict_fallback_alias(tmp_path):
    project = build_known_answer_experiment_package(tmp_path / "project")
    source = (project.root / "experiment/code/main.py").read_text(encoding="utf-8")
    _replace_main(
        project,
        source
        + '''

def placeholder_fallback() -> dict[str, object]:
    first = dict
    second = first
    return second(mae=0.5, evidence_eligible=True)
''',
    )

    with pytest.raises(ValueError, match="fallback|callable alias"):
        validate_experiment_package_contract(project)


def test_package_contract_rejects_fallback_despite_cross_function_shadow(tmp_path):
    project = build_known_answer_experiment_package(tmp_path / "project")
    source = (project.root / "experiment/code/main.py").read_text(encoding="utf-8")
    _replace_main(
        project,
        source
        + '''

def placeholder_fallback() -> dict[str, object]:
    return build_output()


def build_output() -> dict[str, object]:
    return {"mae": 0.5, "evidence_eligible": True}


def unrelated_shadow() -> dict[str, object]:
    build_output = dict
    return build_output(ok=True)
''',
    )

    with pytest.raises(ValueError, match="fallback"):
        validate_experiment_package_contract(project)


def test_package_contract_rejects_cyclic_or_unresolved_local_callable_alias(tmp_path):
    project = build_known_answer_experiment_package(tmp_path / "project")
    source = (project.root / "experiment/code/main.py").read_text(encoding="utf-8")
    source = source.replace(
        "    return sum(abs(a - b) for a, b in zip(targets, predictions, strict=True)) / len(targets)\n",
        "    first = second\n    second = first\n    return first()\n",
    )
    _replace_main(project, source)

    with pytest.raises(ValueError, match="callable alias"):
        validate_experiment_package_contract(project)


def test_package_contract_rejects_inverted_self_test_predicate(tmp_path):
    project = build_known_answer_experiment_package(tmp_path / "project")
    source = (project.root / "experiment/code/main.py").read_text(encoding="utf-8")
    _replace_main(project, source.replace("if args.self_test:", "if not args.self_test:"))

    with pytest.raises(ValueError, match="self-test adapter"):
        validate_experiment_package_contract(project)


def test_package_contract_rejects_an_additional_ambiguous_self_test_predicate(tmp_path):
    project = build_known_answer_experiment_package(tmp_path / "project")
    source = (project.root / "experiment/code/main.py").read_text(encoding="utf-8")
    source = source.replace(
        '    result = run_experiment(config)\n',
        '    if not args.self_test:\n'
        '        pass\n'
        '    result = run_experiment(config)\n',
    )
    _replace_main(project, source)

    with pytest.raises(ValueError, match="self-test adapter"):
        validate_experiment_package_contract(project)


def test_package_contract_rejects_a_later_self_test_report_overwrite(tmp_path):
    project = build_known_answer_experiment_package(tmp_path / "project")
    source = (project.root / "experiment/code/main.py").read_text(encoding="utf-8")
    source = source.replace(
        '    result = run_experiment(config)\n',
        '    result = run_experiment(config)\n'
        '    Path("experiment/self_test_report.json").write_text(\n'
        '        json.dumps({"metrics": []}) + "\\n", encoding="utf-8"\n'
        '    )\n',
    )
    _replace_main(project, source)

    with pytest.raises(ValueError, match="self-test adapter"):
        validate_experiment_package_contract(project)


def test_package_contract_rejects_open_write_report_overwrite(tmp_path):
    project = build_known_answer_experiment_package(tmp_path / "project")
    source = (project.root / "experiment/code/main.py").read_text(encoding="utf-8")
    source = source.replace(
        '    result = run_experiment(config)\n',
        '    retained_report = open(\n'
        '        "experiment/self_test_report.json", "w", encoding="utf-8"\n'
        '    )\n'
        '    retained_report.write(json.dumps({"metrics": []}) + "\\n")\n'
        '    retained_report.close()\n'
        '    result = run_experiment(config)\n',
    )
    _replace_main(project, source)

    with pytest.raises(ValueError, match="self-test adapter"):
        validate_experiment_package_contract(project)


def test_package_contract_rejects_path_import_alias_report_overwrite(tmp_path):
    project = build_known_answer_experiment_package(tmp_path / "project")
    source = (project.root / "experiment/code/main.py").read_text(encoding="utf-8")
    source = source.replace(
        "from pathlib import Path\n",
        "from pathlib import Path\nfrom pathlib import Path as ReportPath\n",
    ).replace(
        '    result = run_experiment(config)\n',
        '    ReportPath("experiment/self_test_report.json").write_text(\n'
        '        json.dumps({"metrics": []}) + "\\n", encoding="utf-8"\n'
        '    )\n'
        '    result = run_experiment(config)\n',
    )
    _replace_main(project, source)

    with pytest.raises(ValueError, match="self-test adapter"):
        validate_experiment_package_contract(project)


def test_package_contract_rejects_computed_report_path_overwrite(tmp_path):
    project = build_known_answer_experiment_package(tmp_path / "project")
    source = (project.root / "experiment/code/main.py").read_text(encoding="utf-8")
    source = source.replace(
        '    result = run_experiment(config)\n',
        '    retained_report = "experiment/" + "self_test_report.json"\n'
        '    Path(retained_report).write_text(\n'
        '        json.dumps({"metrics": []}) + "\\n", encoding="utf-8"\n'
        '    )\n'
        '    result = run_experiment(config)\n',
    )
    _replace_main(project, source)

    with pytest.raises(ValueError, match="self-test adapter"):
        validate_experiment_package_contract(project)


def test_package_contract_rejects_report_mapping_mutation_before_write(tmp_path):
    project = build_known_answer_experiment_package(tmp_path / "project")
    source = (project.root / "experiment/code/main.py").read_text(encoding="utf-8")
    source = source.replace(
        '        report = {\n',
        '        report = {\n',
    ).replace(
        '        Path("experiment/self_test_report.json").write_text',
        '        result.update({"mae": 0.5})\n'
        '        Path("experiment/self_test_report.json").write_text',
    )
    _replace_main(project, source)

    with pytest.raises(ValueError, match="self-test adapter"):
        validate_experiment_package_contract(project)


def test_package_contract_rejects_report_mapping_mutation_in_reachable_helper(tmp_path):
    project = build_known_answer_experiment_package(tmp_path / "project")
    source = (project.root / "experiment/code/main.py").read_text(encoding="utf-8")
    source = source.replace(
        '\n\ndef main(argv: list[str] | None = None) -> dict[str, object]:\n',
        '\n\ndef overwrite_metric(result: dict[str, object]) -> None:\n'
        '    result.update({"mae": 0.5})\n'
        '\n\ndef main(argv: list[str] | None = None) -> dict[str, object]:\n',
    ).replace(
        '        Path("experiment/self_test_report.json").write_text',
        '        overwrite_metric(result)\n'
        '        Path("experiment/self_test_report.json").write_text',
    )
    _replace_main(project, source)

    with pytest.raises(ValueError, match="self-test adapter"):
        validate_experiment_package_contract(project)


def test_registered_self_test_accepts_reconstructed_fresh_package(tmp_path):
    project = build_known_answer_experiment_package(tmp_path / "project")
    original = validate_experiment_package_contract(project)
    reconstructed = ValidatedExperimentPackage(
        contract_sha256=original.contract_sha256,
        metric_entrypoints=original.metric_entrypoints,
        self_test_argv=original.self_test_argv,
        execution_argv=original.execution_argv,
    )
    _write_self_test_report(project, reconstructed)

    assert validate_registered_self_test(project, reconstructed).path == SELF_TEST_REPORT_PATH


def test_registered_self_test_has_no_process_global_identity_registry():
    from researchclaw.core import experiment_package_contract

    assert not hasattr(experiment_package_contract, "_PACKAGE_IDENTITIES")


def test_registered_self_test_rejects_a_forged_public_package(tmp_path):
    project = build_known_answer_experiment_package(tmp_path / "project")
    package = validate_experiment_package_contract(project)
    forged = ValidatedExperimentPackage(
        contract_sha256="0" * 64,
        metric_entrypoints=package.metric_entrypoints,
        self_test_argv=package.self_test_argv,
        execution_argv=package.execution_argv,
    )
    _write_self_test_report(project, package)

    with pytest.raises(ValueError, match="package changed"):
        validate_registered_self_test(project, forged)


def test_registered_self_test_requires_the_complete_manifest_file_identity_set(tmp_path):
    project = build_known_answer_experiment_package(tmp_path / "project")
    package = validate_experiment_package_contract(project)
    _write_self_test_report(project, package, package_files=[])

    with pytest.raises(ValueError, match="package_files"):
        validate_registered_self_test(project, package)


def test_registered_self_test_rejects_package_drift_after_reconstruction(tmp_path):
    project = build_known_answer_experiment_package(tmp_path / "project")
    package = validate_experiment_package_contract(project)
    reconstructed = ValidatedExperimentPackage(
        package.contract_sha256,
        package.metric_entrypoints,
        package.self_test_argv,
        package.execution_argv,
    )
    _write_self_test_report(project, reconstructed)
    source = (project.root / "experiment/code/main.py").read_text(encoding="utf-8")
    _replace_main(
        project,
        source.replace(
            "    return sum(abs(a - b) for a, b in zip(targets, predictions, strict=True)) / len(targets)\n",
            "    return 0.0\n",
        ),
    )

    with pytest.raises(ValueError, match="package_manifest|package changed"):
        validate_registered_self_test(project, reconstructed)
