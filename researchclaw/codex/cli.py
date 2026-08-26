"""Create and inspect durable local research projects."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence

from researchclaw.core.project import ResearchProject
from researchclaw.core.approval import approve_current_gate
from researchclaw.core.events import build_foundation_report
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

    stage = subcommands.add_parser("stage", help="prepare a research stage")
    stage_commands = stage.add_subparsers(dest="stage_command", required=True)
    prepare = stage_commands.add_parser("prepare", help="prepare a stage task packet")
    prepare.add_argument("root", metavar="ROOT")
    prepare.add_argument("--json", action="store_true", help="emit JSON")
    validate = stage_commands.add_parser("validate", help="validate and advance the current stage")
    validate.add_argument("root", metavar="ROOT")
    validate.add_argument("--json", action="store_true", help="emit JSON")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    exit_code = 0
    try:
        args = parser.parse_args(argv)
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
        elif args.command == "stage" and args.stage_command == "prepare":
            project = ResearchProject.open(args.root)
            payload = prepare_task_packet(project).to_dict()
        else:
            project = ResearchProject.open(args.root)
            report = validate_current_stage(project)
            payload = report.to_dict()
            exit_code = 0 if report.valid else 2
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
        else:
            print(f"{payload['project_id']}: stage {payload['current_stage']} ({payload['status']})")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
