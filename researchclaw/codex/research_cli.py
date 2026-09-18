"""Research graph lifecycle CLI, without execution or private body projections."""
import json
from pathlib import Path
from researchclaw.core.research_graph import commands, migration, store
from researchclaw.core.research_graph.views import build_view, _load
from researchclaw.core.research_graph.councils import reviewer_packet


def add_research_parser(subcommands):
    parser = subcommands.add_parser('research', help='Version-isolated research graph')
    actions = parser.add_subparsers(dest='research_command', required=True)
    from .atlas_service_cli import add_parser
    add_parser(actions)
    atlas = actions.add_parser('atlas-import', help='Preview or import a saved Atlas QA Markdown file')
    atlas.add_argument('root', type=Path)
    atlas.add_argument('file', type=Path)
    atlas.add_argument('--preview', action='store_true')
    atlas.add_argument('--expected-head')
    atlas.add_argument('--command-id')
    atlas.add_argument('--json', action='store_true')
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
    inspect.add_argument('--head', dest='head_id')
    inspect.add_argument('--json', action='store_true')
    assess = actions.add_parser('assess-work', help='Check a concrete next-work plan without executing it')
    assess.add_argument('root', type=Path)
    assess.add_argument('--payload', required=True, type=Path)
    assess.add_argument('--json', action='store_true')
    viewer = actions.add_parser('view')
    viewer.add_argument('root', type=Path)
    viewer.add_argument('--host', default='127.0.0.1', choices=('127.0.0.1',))
    viewer.add_argument('--port', type=int, default=0)
    viewer.add_argument('--discovery-root', type=Path, help='Explicit read-only discovery run directory')
    viewer.add_argument('--workspace', type=Path, help='Explicit local project catalog directory')
    viewer.add_argument('--json', action='store_true')
    apply = actions.add_parser('apply')
    apply.add_argument('root', type=Path)
    apply.add_argument('--operation', required=True, choices=sorted(commands._HANDLERS))
    apply.add_argument('--payload', required=True, type=Path, help='Path to one closed JSON operation payload')
    apply.add_argument('--expected-head', required=True)
    apply.add_argument('--command-id', required=True)
    apply.add_argument('--json', action='store_true')
    packet = actions.add_parser('packet')
    packet.add_argument('root', type=Path)
    packet.add_argument('--assignment', required=True)
    packet.add_argument('--head', dest='head_id')
    packet.add_argument('--json', action='store_true')


def dispatch(args):
    if args.research_command == 'atlas-service':
        from .atlas_service_cli import run
        return run(args)
    if args.research_command == 'atlas-import':
        from .atlas_intake import read_qa, import_qa
        from researchclaw.core.research_graph.atlas_format import parse_atlas_qa
        data = read_qa(args.file)
        if args.preview:
            return parse_atlas_qa(data)
        if not args.expected_head or not args.command_id:
            raise ValueError('atlas_expected_head_and_command_id_required')
        return import_qa(args.root, data=data, filename=args.file.name,
                         expected_head=args.expected_head, command_id=args.command_id)
    if args.research_command == 'view':
        from .research_viewer import serve_view
        options = {'host': args.host, 'port': args.port}
        if getattr(args, 'discovery_root', None) is not None:
            options['discovery_root'] = args.discovery_root
        if getattr(args, 'workspace', None) is not None:
            options['workspace'] = args.workspace
        serve_view(args.root, **options)
        return {'status': 'stopped'}
    if args.research_command == 'inspect':
        return build_view(args.root, head_id=args.head_id)
    if args.research_command == 'assess-work':
        from researchclaw.core.research_graph.budgets import assess_next_work
        payload = json.loads(args.payload.read_text(encoding='utf-8'), object_pairs_hook=store._unique_pairs)
        return assess_next_work(commands.read_policy_snapshot(args.root), payload)
    if args.research_command == 'packet':
        snapshot, _ = _load(args.root, args.head_id)
        return reviewer_packet(snapshot, args.assignment)
    if args.research_command == 'apply':
        payload = json.loads(args.payload.read_text(encoding='utf-8'), object_pairs_hook=store._unique_pairs)
        receipt = commands.apply_command(args.root, operation=args.operation, payload=payload,
            expected_head=args.expected_head, command_id=args.command_id)
        return {**store._VERSION, 'id': receipt['id'], 'head_id': receipt['id'], 'operation': args.operation}
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
