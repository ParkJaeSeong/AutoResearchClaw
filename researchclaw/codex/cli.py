"""Create and inspect durable local research projects."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence

from researchclaw.core.project import ResearchProject


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create and inspect local research projects.")
    subcommands = parser.add_subparsers(dest="command", required=True)

    init = subcommands.add_parser("init", help="create a research project")
    init.add_argument("root", metavar="ROOT")
    init.add_argument("--topic", required=True, metavar="TOPIC")
    init.add_argument("--profile", default="materials_ai", metavar="PROFILE")
    init.add_argument("--json", action="store_true", help="emit JSON")

    status = subcommands.add_parser("status", help="show project status")
    status.add_argument("root", metavar="ROOT")
    status.add_argument("--json", action="store_true", help="emit JSON")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        if args.command == "init":
            project = ResearchProject.create(args.root, topic=args.topic, profile=args.profile)
        else:
            project = ResearchProject.open(args.root)
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    payload = project.status_dict()
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    else:
        print(f"{payload['project_id']}: stage {payload['current_stage']} ({payload['status']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
