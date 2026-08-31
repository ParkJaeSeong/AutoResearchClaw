"""Create and inspect durable local research projects."""

from __future__ import annotations

import argparse
import json
import shlex
import sys
from dataclasses import asdict
from collections.abc import Sequence

from researchclaw.core.project import ResearchProject
from researchclaw.core.approval import approve_current_gate
from researchclaw.core.events import build_foundation_report
from researchclaw.core.experiment_package_contract import (
    prepare_experiment_self_test,
    register_experiment_self_test,
)
from researchclaw.core.execution_gate import (
    recheck_development_input,
    recheck_execution_readiness,
)
from researchclaw.core.development_execution import (
    run_development_experiment,
    validate_development_result,
)
from researchclaw.core.research_execution import (
    prepare_research_execution,
    register_research_result,
)
from researchclaw.core.evidence_store import (
    EvidenceIntegrityError,
    EvidenceStore,
    ResultQuarantineCapacityError,
    cleanup_quarantined_result,
    quarantine_unregistered_result,
    request_result_quarantine_operator_cleanup,
    result_quarantine_inventory,
)
from researchclaw.core.evidence_registration import registered_evidence_status
from researchclaw.core.task_packets import prepare_task_packet
from researchclaw.core.validation import validate_current_stage


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="researchclaw-codex",
        description="Create and inspect durable Codex-native research projects.",
    )
    subcommands = parser.add_subparsers(dest="command", required=True)

    init = subcommands.add_parser("init", help="create a research project")
    init.add_argument("root", metavar="ROOT")
    init.add_argument("--topic", required=True, metavar="TOPIC")
    init.add_argument("--profile", default="materials_ai", metavar="PROFILE")
    init.add_argument("--json", action="store_true", help="emit JSON")

    status = subcommands.add_parser("status", help="show project status")
    status.add_argument("root", metavar="ROOT")
    status.add_argument("--json", action="store_true", help="emit JSON")

    resume = subcommands.add_parser("resume", help="reconstruct the next durable project action")
    resume.add_argument("root", metavar="ROOT")
    resume.add_argument("--json", action="store_true", help="emit JSON")

    approve = subcommands.add_parser("approve", help="record a decision for the current approval gate")
    approve.add_argument("root", metavar="ROOT")
    approve.add_argument("--decision", required=True, choices=("approve", "reject"))
    approve.add_argument("--note", default="", metavar="TEXT")
    approve.add_argument("--json", action="store_true", help="emit JSON")

    evaluate = subcommands.add_parser("evaluate", help="report foundation workflow metrics")
    evaluate.add_argument("root", metavar="ROOT")
    evaluate.add_argument("--json", action="store_true", help="emit JSON")

    experiment = subcommands.add_parser(
        "experiment", help="manage experiment-package validation evidence"
    )
    experiment_commands = experiment.add_subparsers(
        dest="experiment_command", required=True
    )
    prepare_self_test = experiment_commands.add_parser(
        "prepare-self-test",
        help="return the verified argv for an external known-answer self-test",
    )
    prepare_self_test.add_argument("root", metavar="PROJECT")
    prepare_self_test.add_argument("--json", action="store_true", help="emit JSON")
    register_self_test = experiment_commands.add_parser(
        "register-self-test", help="register an externally run known-answer self-test"
    )
    register_self_test.add_argument("root", metavar="PROJECT")
    register_self_test.add_argument(
        "--report", required=True, metavar="PROJECT_RELATIVE_PATH"
    )
    register_self_test.add_argument(
        "--confirm-self-test",
        action="store_true",
        required=True,
        help="confirm registration of the externally produced self-test report",
    )
    register_self_test.add_argument("--json", action="store_true", help="emit JSON")

    stage = subcommands.add_parser("stage", help="prepare a research stage")
    stage_commands = stage.add_subparsers(dest="stage_command", required=True)
    prepare = stage_commands.add_parser("prepare", help="prepare a stage task packet")
    prepare.add_argument("root", metavar="ROOT")
    prepare.add_argument(
        "--establish-legacy-baseline",
        action="store_true",
        help="explicitly establish a safe missing Stage-10 legacy baseline",
    )
    prepare.add_argument("--json", action="store_true", help="emit JSON")
    validate = stage_commands.add_parser("validate", help="validate and advance the current stage")
    validate.add_argument("root", metavar="ROOT")
    validate.add_argument("--json", action="store_true", help="emit JSON")

    execution = subcommands.add_parser("execution", help="inspect the Stage 12 execution gate")
    execution_commands = execution.add_subparsers(dest="execution_command", required=True)
    recheck = execution_commands.add_parser("recheck", help="refresh declared readiness facts")
    recheck.add_argument("root", metavar="ROOT")
    recheck.add_argument("--input-manifest", metavar="PROJECT_RELATIVE_PATH")
    recheck.add_argument(
        "--development",
        action="store_true",
        help="validate an explicit synthetic development input without changing the execution gate",
    )
    recheck.add_argument("--json", action="store_true", help="emit JSON")
    run = execution_commands.add_parser(
        "run", help="run an explicitly confirmed synthetic development fixture"
    )
    run.add_argument("root", metavar="ROOT")
    run.add_argument(
        "--input-manifest",
        required=True,
        metavar="PROJECT_RELATIVE_PATH",
    )
    run.add_argument(
        "--development",
        action="store_true",
        required=True,
        help="confirm that this is a synthetic development-only run",
    )
    run.add_argument(
        "--confirm-development-run",
        action="store_true",
        required=True,
        help="explicitly confirm the bounded local development run",
    )
    run.add_argument(
        "--max-seconds",
        type=int,
        default=120,
        metavar="N",
        help="positive local execution deadline in seconds (default: 120)",
    )
    run.add_argument("--json", action="store_true", help="emit JSON")
    validate_result = execution_commands.add_parser(
        "validate-result", help="validate a saved synthetic development result"
    )
    validate_result.add_argument("root", metavar="ROOT")
    validate_result.add_argument(
        "--result", required=True, metavar="PROJECT_RELATIVE_PATH"
    )
    validate_result.add_argument(
        "--development",
        action="store_true",
        required=True,
        help="confirm that the saved result is development-only",
    )
    validate_result.add_argument("--json", action="store_true", help="emit JSON")
    prepare_run = execution_commands.add_parser(
        "prepare-run", help="write the approved research execution handoff"
    )
    prepare_run.add_argument("root", metavar="ROOT")
    prepare_run.add_argument("--json", action="store_true", help="emit JSON")
    register_result = execution_commands.add_parser(
        "register-result", help="register an explicit research result"
    )
    register_result.add_argument("root", metavar="ROOT")
    register_result.add_argument(
        "--result", required=True, metavar="PROJECT_RELATIVE_PATH"
    )
    register_result.add_argument(
        "--confirm-research-result",
        action="store_true",
        required=True,
        help="confirm registration of a contract-bound research result",
    )
    register_result.add_argument("--json", action="store_true", help="emit JSON")
    quarantine_result = execution_commands.add_parser(
        "quarantine-result",
        help="copy one unregistered result to quarantine without removing the source",
    )
    quarantine_result.add_argument("root", metavar="PROJECT")
    quarantine_result.add_argument("--reason", required=True, metavar="CATEGORY")
    quarantine_result.add_argument("--confirm", action="store_true")
    quarantine_result.add_argument("--json", action="store_true", help="emit JSON")
    cleanup_result = execution_commands.add_parser(
        "cleanup-quarantined-result",
        help="explicitly preserve and remove the validated stale result pathname",
    )
    cleanup_result.add_argument("root", metavar="PROJECT")
    cleanup_result.add_argument("--confirm", action="store_true")
    cleanup_result.add_argument("--json", action="store_true", help="emit JSON")

    evidence = subcommands.add_parser("evidence", help="audit and collect evidence")
    evidence_commands = evidence.add_subparsers(dest="evidence_command", required=True)
    gc = evidence_commands.add_parser("gc", help="plan or confirm evidence collection")
    gc.add_argument("root", metavar="PROJECT")
    gc_mode = gc.add_mutually_exclusive_group(required=True)
    gc_mode.add_argument("--dry-run", action="store_true")
    gc_mode.add_argument("--confirm-token", metavar="TOKEN")
    gc.add_argument("--json", action="store_true", help="emit JSON")
    audit = evidence_commands.add_parser("audit", help="audit immutable evidence grounding")
    audit.add_argument("root", metavar="PROJECT")
    audit.add_argument("--json", action="store_true", help="emit JSON")
    quarantine_inventory = evidence_commands.add_parser(
        "quarantine-inventory", help="inspect retained result quarantine capacity"
    )
    quarantine_inventory.add_argument("root", metavar="PROJECT")
    quarantine_inventory.add_argument("--json", action="store_true", help="emit JSON")
    quarantine_cleanup = evidence_commands.add_parser(
        "quarantine-operator-cleanup",
        help="confirm the fail-closed manual quarantine cleanup route",
    )
    quarantine_cleanup.add_argument("root", metavar="PROJECT")
    quarantine_cleanup.add_argument("--confirm", action="store_true")
    quarantine_cleanup.add_argument("--json", action="store_true", help="emit JSON")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    exit_code = 0
    try:
        args = parser.parse_args(argv)
    except SystemExit as error:
        return int(error.code)
    try:
        if args.command == "init":
            project = ResearchProject.create(args.root, topic=args.topic, profile=args.profile)
            payload = project.status_dict()
        elif args.command == "status":
            project = ResearchProject.open(args.root)
            payload = project.status_dict()
        elif args.command == "resume":
            project = ResearchProject.open(args.root)
            payload = project.build_handoff().to_dict()
        elif args.command == "approve":
            project = ResearchProject.open(args.root)
            payload = approve_current_gate(project, args.decision, args.note).to_dict()
        elif args.command == "evaluate":
            project = ResearchProject.open(args.root)
            payload = build_foundation_report(project)
        elif args.command == "experiment" and args.experiment_command == "prepare-self-test":
            project = ResearchProject.open_readonly(args.root)
            payload = prepare_experiment_self_test(project).to_dict()
        elif args.command == "experiment" and args.experiment_command == "register-self-test":
            project = ResearchProject.open(args.root)
            artifact = register_experiment_self_test(project, args.report)
            payload = {
                "path": artifact.path,
                "sha256": artifact.sha256,
                "size": artifact.size,
            }
        elif args.command == "execution" and args.execution_command == "recheck":
            if args.development:
                project = ResearchProject.open_readonly(args.root)
                if args.input_manifest is None:
                    raise ValueError("--development requires --input-manifest")
                payload = recheck_development_input(
                    project,
                    args.input_manifest,
                ).to_dict()
            elif args.input_manifest is not None:
                raise ValueError("--input-manifest requires --development")
            else:
                project = ResearchProject.open(args.root)
                payload = recheck_execution_readiness(project).to_dict()
        elif args.command == "execution" and args.execution_command == "run":
            if args.max_seconds <= 0:
                raise ValueError("--max-seconds must be a positive integer")
            project = ResearchProject.open_readonly(args.root)
            payload = run_development_experiment(
                project,
                args.input_manifest,
                max_seconds=args.max_seconds,
            ).to_dict()
        elif args.command == "execution" and args.execution_command == "validate-result":
            project = ResearchProject.open_readonly(args.root)
            payload = validate_development_result(project, args.result).to_dict()
        elif args.command == "execution" and args.execution_command == "prepare-run":
            project = ResearchProject.open(args.root)
            payload = prepare_research_execution(project).to_dict()
        elif args.command == "execution" and args.execution_command == "register-result":
            project = ResearchProject.open(args.root)
            payload = register_research_result(project, args.result).to_dict()
        elif args.command == "execution" and args.execution_command == "quarantine-result":
            project = ResearchProject.open(args.root)
            payload = quarantine_unregistered_result(
                project, args.reason, args.confirm
            ).to_dict()
        elif args.command == "execution" and args.execution_command == "cleanup-quarantined-result":
            project = ResearchProject.open(args.root)
            payload = cleanup_quarantined_result(project, args.confirm).to_dict()
        elif args.command == "evidence" and args.evidence_command == "gc":
            store = EvidenceStore(ResearchProject.open(args.root).root)
            plan = store.plan_gc()
            payload = (
                asdict(plan)
                if args.dry_run
                else asdict(store.collect(plan, args.confirm_token))
            )
        elif args.command == "evidence" and args.evidence_command == "audit":
            project = ResearchProject.open_readonly(args.root)
            try:
                from researchclaw.core.evidence_store import (
                    _validated_manifest_candidates,
                )

                store = EvidenceStore(project.root, create=False)
                _validated_manifest_candidates(project, store)
                status = registered_evidence_status(project, store=store)
                payload = {
                    "project_id": project.state.project_id,
                    "classification": (
                        "immutable_registered"
                        if status is not None
                        else "legacy_untrusted"
                    ),
                    "registration": None if status is None else status.to_dict(),
                }
            except (EvidenceIntegrityError, OSError, TypeError, ValueError):
                payload = {
                    "project_id": project.state.project_id,
                    "classification": "registered_evidence_corrupt",
                    "registration": None,
                    "integrity_status": "failed",
                    "error_category": "evidence_object_integrity_failure",
                    "recommended_action": (
                        "restore_from_trusted_backup_then_reaudit"
                    ),
                    "recommended_command": shlex.join(
                        (
                            "researchclaw-codex",
                            "evidence",
                            "audit",
                            str(project.root.resolve()),
                            "--json",
                        )
                    ),
                }
                exit_code = 2
        elif args.command == "evidence" and args.evidence_command == "quarantine-inventory":
            project = ResearchProject.open_readonly(args.root)
            payload = result_quarantine_inventory(project).to_dict()
        elif (
            args.command == "evidence"
            and args.evidence_command == "quarantine-operator-cleanup"
        ):
            project = ResearchProject.open_readonly(args.root)
            payload = request_result_quarantine_operator_cleanup(
                project, args.confirm
            ).to_dict()
            if payload["manual_filesystem_action_required"]:
                exit_code = 2
        elif args.command == "stage" and args.stage_command == "prepare":
            project = ResearchProject.open(args.root)
            payload = prepare_task_packet(
                project,
                establish_legacy_baseline=args.establish_legacy_baseline,
            ).to_dict()
        else:
            project = ResearchProject.open(args.root)
            report = validate_current_stage(project)
            payload = report.to_dict()
            exit_code = 0 if report.valid else 2
    except (ResultQuarantineCapacityError, EvidenceIntegrityError) as error:
        if getattr(args, "json", False):
            print(
                json.dumps(error.to_dict(), ensure_ascii=False, sort_keys=True),
                file=sys.stderr,
            )
        else:
            print(f"error: {error}", file=sys.stderr)
        return 2
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    else:
        if args.command == "stage" and args.stage_command == "prepare":
            print(f"{payload['project_id']}: stage {payload['stage_id']} ({payload['name']})")
        elif args.command == "approve":
            print(f"stage {payload['stage_id']}: {payload['decision']}")
        elif args.command == "stage":
            print(f"stage {payload['stage_id']}: {'valid' if payload['valid'] else 'invalid'}")
        elif args.command == "evaluate":
            print(f"{payload['project_id']}: {payload['stage_completion_rate']:.0%} complete")
        elif args.command == "experiment":
            if args.experiment_command == "prepare-self-test":
                print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
            else:
                print(f"registered self-test: {payload['path']}")
        elif args.command == "execution":
            if args.execution_command == "prepare-run":
                argv = payload.get("argv")
                if not isinstance(argv, list) or not all(
                    isinstance(item, str) for item in argv
                ):
                    raise ValueError("execution_contract_invalid")
                print(shlex.join(argv))
            else:
                readiness = payload.get("readiness")
                if isinstance(readiness, str):
                    print(f"stage 12: {readiness}")
                else:
                    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        elif args.command == "evidence":
            print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        else:
            print(f"{payload['project_id']}: stage {payload['current_stage']} ({payload['status']})")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
