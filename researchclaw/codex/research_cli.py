"""Research graph lifecycle CLI, without execution or private body projections."""
from pathlib import Path
from researchclaw.core.research_graph import commands, migration, store


def add_research_parser(subcommands):
    parser = subcommands.add_parser('research', help='Version-isolated research graph')
    actions = parser.add_subparsers(dest='research_command', required=True)
    init = actions.add_parser('init')
    init.add_argument('root', type=Path)
    init.add_argument('--topic', required=True)
    init.add_argument('--content-origin', choices=('real', 'synthetic', 'mixed'), required=True)
    init.add_argument('--max-returns', type=int, default=3)
    init.add_argument('--max-verification-runs', type=int, default=10)
    init.add_argument('--json', action='store_true')
    importer = actions.add_parser('import-m1')
    importer.add_argument('source', type=Path)
    importer.add_argument('target', type=Path)
    importer.add_argument('--source-head', required=True)
    importer.add_argument('--command-id', required=True)
    importer.add_argument('--json', action='store_true')
    inspect = actions.add_parser('inspect')
    inspect.add_argument('root', type=Path)
    inspect.add_argument('--json', action='store_true')


def dispatch(args):
    if args.research_command == 'init':
        return commands.init_project(args.root, topic=args.topic, content_origin=args.content_origin,
            max_returns=args.max_returns, max_verification_runs=args.max_verification_runs)
    if args.research_command == 'import-m1':
        head = migration.import_m1(args.source, args.target, source_head=args.source_head, command_id=args.command_id)
    else:
        head = store.read_head(args.root)
    return {**store._VERSION, 'head_id': head['id'], 'project_id': head['state']['project_id'],
            'content_origin': head['state']['content_origin'], 'object_count': len(head['objects']),
            'event_count': len(head['events']), **migration.import_summary(head)}
