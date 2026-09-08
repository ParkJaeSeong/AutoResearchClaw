"""M1 CLI parser and dispatch, isolated from legacy project commands."""
import json
from pathlib import Path

from researchclaw.core.m1.project import init_project, resume_project
from researchclaw.core.m1.packets import prepare_node, register_outputs
from researchclaw.core.m1 import store
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
    resume = commands.add_parser('resume', help='show current work, inputs and waits without changes')
    resume.add_argument('root', metavar='ROOT')
    resume.add_argument('--json', action='store_true')
    node = commands.add_parser('node', help='prepare and register node drafts')
    node_commands = node.add_subparsers(dest='node_command', required=True)
    prepare = node_commands.add_parser('prepare', help='prepare the current eligible node')
    prepare.add_argument('root', metavar='ROOT')
    prepare.add_argument('--node', required=True)
    prepare.add_argument('--command-id', required=True)
    prepare.add_argument('--json', action='store_true')
    register = node_commands.add_parser('register', help='register packet-owned draft files')
    register.add_argument('root', metavar='ROOT')
    register.add_argument('--packet', required=True)
    register.add_argument('--submission', type=Path, required=True)
    register.add_argument('--command-id', required=True)
    register.add_argument('--json', action='store_true')


def dispatch(args) -> dict:
    if args.m1_command == 'init':
        return init_project(Path(args.root), topic=args.topic, profile=args.profile,
                            max_returns=args.max_returns, content_origin=args.content_origin)
    if args.m1_command == 'resume':
        return resume_project(Path(args.root))
    if args.m1_command == 'node':
        if args.node_command == 'prepare':
            return prepare_node(Path(args.root), args.node, command_id=args.command_id)
        submission = json.loads(store._read_file(args.submission), object_pairs_hook=store._unique_pairs)
        result = register_outputs(Path(args.root), packet_id=args.packet,
                                  submission=submission, command_id=args.command_id)
        if result['issues']:
            raise ValueError('m1_output_validation_failed: ' + json.dumps(result, ensure_ascii=False, sort_keys=True))
        return result
    return read_head(Path(args.root))
