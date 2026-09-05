"""Repository-owned IO, identity and result publication for authored regression."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time

from .agent_experiment import (
    decode_rows,
    evaluate,
    mean_absolute_error,
    validate_package,
)
from .execution_environment import inspect_execution_environment
from .experiment_package_contract import _read_candidate_package_bytes
from .project import ResearchProject


def _canonical(value):
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode()


def _identity(path, payload, *, prefix="", size=False):
    value = {"path": prefix + path, "sha256": hashlib.sha256(payload).hexdigest()}
    if size:
        value["size"] = len(payload)
    return value


def _bound_bytes(root, identity):
    payload = _read_candidate_package_bytes(
        root, identity["path"], maximum_bytes=16 * 1024 * 1024
    )
    if hashlib.sha256(payload).hexdigest() != identity["sha256"] or (
        "size" in identity and len(payload) != identity["size"]
    ):
        raise ValueError("execution input identity changed")
    return payload


def _publish(root, path, value):
    from .paths import resolve_project_artifact

    target = resolve_project_artifact(root, path)
    payload = _canonical(value)
    with target.open("xb") as handle:
        handle.write(payload)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--self-test-environment")
    parser.add_argument("--refinement-self-test-context")
    parser.add_argument("--refinement-run-context")
    args = parser.parse_args(argv)
    if not sys.flags.safe_path:
        raise ValueError(
            "v2 runtime requires the prepared safe-path interpreter command"
        )
    root = Path.cwd().resolve(strict=True)
    candidate = bool(args.refinement_self_test_context or args.refinement_run_context)
    layout, manifest, package, cfg, fixture, held = validate_package(
        root, candidate=candidate
    )
    if (
        args.config != layout["self_config" if args.self_test else "config"]
        or (args.refinement_self_test_context and not args.self_test)
        or (args.refinement_run_context and args.self_test)
        or (args.self_test_environment and (candidate or not args.self_test))
    ):
        raise ValueError("runtime arguments do not match contract")
    environment = inspect_execution_environment(
        Path(sys.executable).resolve(strict=True), ()
    )
    command_prefix = [
        environment.launcher,
        "-P",
        "-m",
        "researchclaw.core.agent_experiment_runtime",
    ]
    # macOS framework launchers rewrite orig_argv[0] to Python.app. The
    # interpreter is independently fingerprinted; preserve every actual flag.
    invoked_argv = [environment.launcher, *sys.orig_argv[1:]]
    if invoked_argv[:4] != command_prefix:
        raise ValueError("runtime requires the exact prepared module command")
    if args.self_test:
        expected_argv = [*command_prefix, *package["self_test"]["argv_suffix"]]
        if candidate:
            expected_argv += [
                "--refinement-self-test-context",
                args.refinement_self_test_context,
            ]
        else:
            if args.self_test_environment != environment.fingerprint:
                raise ValueError("execution environment changed")
            expected_argv += ["--self-test-environment", args.self_test_environment]
        if invoked_argv != expected_argv:
            raise ValueError("self-test argv mismatch")
        value = mean_absolute_error(fixture["targets"], fixture["predictions"])
        answer = package["self_test"]["expected_metrics"][0]
        if abs(value - answer["expected"]) > answer["tolerance"]:
            raise ValueError("self-test known answer failed")
        report = {
            "schema_version": 1,
            "package_contract": _identity(layout["contract"], held[layout["contract"]]),
            "fixture": _identity(layout["fixture"], held[layout["fixture"]]),
            "environment_fingerprint": environment.fingerprint,
            "package_manifest": _identity(layout["manifest"], held[layout["manifest"]]),
            "entry_point": _identity(layout["entry"], held[layout["entry"]]),
            "package_files": [
                {"path": f["path"], "sha256": f["sha256"]} for f in manifest["files"]
            ],
            "metrics": [
                {
                    "name": "mae",
                    "actual": value,
                    "expected": answer["expected"],
                    "tolerance": answer["tolerance"],
                }
            ],
            "passed": True,
            "development_only": True,
        }
        if candidate:
            context = json.loads(args.refinement_self_test_context)
            project_root = root.parents[2]
            _bound_bytes(project_root, context["preparation"])
            for key in (
                "candidate_manifest",
                "council_decision",
                "evidence_packet",
                "baseline_manifest",
                "package_contract",
                "package_manifest",
                "entry_point",
                "fixture",
                "config",
            ):
                _bound_bytes(project_root, context[key])
            for identity in context["candidate_files"]:
                _bound_bytes(project_root, identity)
            if context["environment_fingerprint"] != environment.fingerprint:
                raise ValueError("execution environment changed")
            created = datetime.now(timezone.utc).isoformat()
            report.update(context)
            report.update(created_at=created, report_created_at=created)
        else:
            from .experiment_package_contract import prepare_experiment_self_test

            preparation = prepare_experiment_self_test(
                ResearchProject.open_readonly(root)
            )
            if (
                preparation.environment_fingerprint != environment.fingerprint
                or list(preparation.argv) != invoked_argv
            ):
                raise ValueError("execution environment changed")
        if validate_package(root, candidate=candidate)[-1] != held:
            raise ValueError("package changed during self-test")
        _publish(root, layout["report"], report)
        return report

    if candidate:
        from .refinement_execution import _result_expected_provenance

        project_root = root.parents[2]
        context_path = Path(args.refinement_run_context)
        relative = context_path.relative_to(project_root).as_posix()
        project = ResearchProject.open_readonly(project_root)
        registered = project.state.artifacts.get(relative)
        if registered is None:
            raise ValueError("refinement run contract not registered")
        contract_bytes = _bound_bytes(
            project_root,
            {"path": relative, "sha256": registered.sha256, "size": registered.size},
        )
        context = json.loads(contract_bytes)
        execution = context["execution"]
        if execution["cwd"] != str(root) or execution["argv"] != invoked_argv:
            raise ValueError("refinement run argv mismatch")
        for key in (
            "candidate_manifest",
            "council_decision",
            "evidence_packet",
            "baseline_manifest",
            "baseline_result",
            "package_contract",
            "package_manifest",
            "entry_point",
        ):
            _bound_bytes(project_root, context[key])
        for identity in context["candidate_files"]:
            _bound_bytes(project_root, identity)
        if execution["environment_fingerprint"] != environment.fingerprint:
            raise ValueError("execution environment changed")
        inputs = context["allowed_inputs"]
        maximum = context["envelope"]["reserved_maximum_seconds"]
        result = {
            k: context[k]
            for k in (
                "project_id",
                "session_id",
                "candidate_id",
                "run_id",
                "producer",
                "producer_role",
            )
        }
        result.update(
            created_at=datetime.now(timezone.utc).isoformat(),
            execution_contract={
                "path": relative,
                "contract_id": context["contract_id"],
                "sha256": hashlib.sha256(contract_bytes).hexdigest(),
                "size": len(contract_bytes),
            },
            provenance=_result_expected_provenance(context),
        )
    else:
        from .research_execution import (
            _build_execution_contract,
            _existing_current_contract,
            EXECUTION_CONTRACT_PATH,
        )

        project_root = root
        project = ResearchProject.open_readonly(root)
        expected = _build_execution_contract(project)
        contract_bytes = _existing_current_contract(
            project, expected, stale_category=True
        )
        if contract_bytes is None:
            raise ValueError("approved execution contract required")
        context = json.loads(contract_bytes)
        if (
            context["argv"] != invoked_argv
            or context["environment_fingerprint"] != environment.fingerprint
        ):
            raise ValueError("execution argv or environment changed")
        inputs = context["inputs"]
        resources = json.loads(_bound_bytes(root, context["bindings"]["resources"]))
        maximum = resources["budget"]["total_estimated_duration_seconds"]
        result = {
            "project_id": context["project_id"],
            "execution_contract": {
                "path": EXECUTION_CONTRACT_PATH,
                "contract_id": context["contract_id"],
                "sha256": hashlib.sha256(contract_bytes).hexdigest(),
            },
            "provenance": {"bindings": context["bindings"], "inputs": inputs},
        }
    if [i["path"] for i in inputs] != cfg["input_contract"]["required_paths"]:
        raise ValueError("execution inputs differ from configured inputs")
    started = time.monotonic()
    partitions, summary = decode_rows(
        _bound_bytes(project_root, inputs[0]), cfg["columns"]
    )
    _model, _predictions, value = evaluate(
        held[layout["algorithm"]].decode(),
        partitions,
        cfg["columns"],
        cfg["parameters"],
    )
    elapsed = time.monotonic() - started
    if elapsed > maximum:
        raise ValueError("experiment exceeded runtime budget")
    result.update(
        schema_version=1,
        development_only=False,
        evidence_eligible=True,
        status="completed",
        metrics={"primary": {**cfg["metrics"][0], "value": value}},
        split_summary=summary,
        runtime={"elapsed_seconds": elapsed, "maximum_seconds": maximum},
    )
    if validate_package(root, candidate=candidate)[-1] != held:
        raise ValueError("package changed during execution")
    for identity in inputs:
        _bound_bytes(project_root, identity)
    _publish(root, layout["result"], result)
    return result


if __name__ == "__main__":
    main()
