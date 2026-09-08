"""M1 CLI parser and dispatch, isolated from legacy project commands."""
from pathlib import Path

from researchclaw.core.m1.project import init_project
from researchclaw.core.m1.store import read_head


def add_m1_parser(subcommands) -> None:
    parser = subcommands.add_parser('m1', help='create and inspect M1 research graphs')
    commands = parser.add_subparsers(dest='m1_command', required=True)
    init = commands.add_parser('init', help='create or reopen a new M1 project')
    init.add_argument('root', metavar='ROOT')
    init.add_argument('--topic', required=True)
    init.add_argument('--profile', default='materials_ai')
    init.add_argument('--max-returns', type=int, default=2)
    init.add_argument('--content-origin', choices=('research', 'synthetic'), default='research')
    init.add_argument('--json', action='store_true')
    status = commands.add_parser('status', help='read verified M1 HEAD without changes')
    status.add_argument('root', metavar='ROOT')
    status.add_argument('--json', action='store_true')


def dispatch(args) -> dict:
    if args.m1_command == 'init':
        return init_project(Path(args.root), topic=args.topic, profile=args.profile,
                            max_returns=args.max_returns, content_origin=args.content_origin)
    return read_head(Path(args.root))
