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
    inspect = commands.add_parser('inspect', help='read a registered current or historical view')
    inspect.add_argument('root', metavar='ROOT')
    inspect.add_argument('--head', help='reachable immutable commit ID')
    inspect.add_argument('--json', action='store_true')
    trace = commands.add_parser('trace', help='trace a synthesis claim to exact registered evidence')
    trace.add_argument('root', metavar='ROOT')
    trace.add_argument('--claim', required=True)
    trace.add_argument('--synthesis', help='registered synthesis artifact ID; defaults to latest')
    trace.add_argument('--json', action='store_true')
    returns = commands.add_parser('return', help='plan and apply an authorized return')
    return_commands = returns.add_subparsers(dest='return_command', required=True)
    plan = return_commands.add_parser('plan', help='preview exact dependency and approval impacts')
    plan.add_argument('root', metavar='ROOT')
    plan.add_argument('--decision', required=True)
    plan.add_argument('--target', required=True)
    plan.add_argument('--issues', nargs='+', required=True)
    plan.add_argument('--json', action='store_true')
    apply = return_commands.add_parser('apply', help='apply an exact current return plan')
    apply.add_argument('root', metavar='ROOT')
    apply.add_argument('--plan', type=Path, required=True)
    apply.add_argument('--command-id', required=True)
    apply.add_argument('--json', action='store_true')
    budget = commands.add_parser('budget', help='record an explicit user return ceiling')
    budget_commands = budget.add_subparsers(dest='budget_command', required=True)
    budget_set = budget_commands.add_parser('set')
    budget_set.add_argument('root', metavar='ROOT')
    budget_set.add_argument('--max-returns', type=int, required=True)
    budget_set.add_argument('--note', required=True)
    budget_set.add_argument('--command-id', required=True)
    budget_set.add_argument('--json', action='store_true')
    corpus = commands.add_parser('corpus', help='record explicit user corpus decisions')
    corpus_commands = corpus.add_subparsers(dest='corpus_command', required=True)
    decide = corpus_commands.add_parser('decide', help='approve or reject the current corpus')
    decide.add_argument('root', metavar='ROOT')
    decide.add_argument('--binding', required=True)
    decide.add_argument('--decision', choices=('approve', 'reject'), required=True)
    decide.add_argument('--note', required=True)
    decide.add_argument('--command-id', required=True)
    decide.add_argument('--json', action='store_true')
    council = commands.add_parser('council', help='collect independent review deliberation')
    council_commands = council.add_subparsers(dest='council_command', required=True)
    for name in ('prepare', 'initial', 'response', 'final', 'decide', 'packet', 'replace'):
        action = council_commands.add_parser(name)
        action.add_argument('root', metavar='ROOT')
        action.add_argument('--json', action='store_true')
        if name == 'prepare':
            action.add_argument('--attempt', required=True)
            action.add_argument('--assignments', type=Path, required=True)
        else:
            action.add_argument('--session', required=True)
            if name != 'decide':
                action.add_argument('--assignment', required=True)
        if name in ('initial', 'response', 'final', 'decide'):
            action.add_argument('--submission', type=Path, required=True)
        if name == 'replace':
            action.add_argument('--replacement', type=Path, required=True)
            action.add_argument('--reason', required=True)
        if name != 'packet':
            action.add_argument('--command-id', required=True)
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


def _dispatch(args) -> dict:
    if args.m1_command == 'init':
        return init_project(Path(args.root), topic=args.topic, profile=args.profile,
                            max_returns=args.max_returns, content_origin=args.content_origin)
    if args.m1_command == 'resume':
        return resume_project(Path(args.root))
    if args.m1_command == 'inspect':
        from researchclaw.core.m1.views import build_view
        return build_view(Path(args.root), head_id=args.head)
    if args.m1_command == 'trace':
        from researchclaw.core.m1.synthesis import read_trace_head, trace_claim
        return trace_claim(read_trace_head(Path(args.root), synthesis_ref_id=args.synthesis), args.claim)
    if args.m1_command == 'return':
        from researchclaw.core.m1.transitions import plan_return, apply_return
        if args.return_command == 'apply':
            plan = json.loads(store._read_file(args.plan), object_pairs_hook=store._unique_pairs)
            return apply_return(Path(args.root), plan=plan, command_id=args.command_id)
        return plan_return(Path(args.root), decision_id=args.decision,
                           target_node_id=args.target, issue_ids=args.issues)
    if args.m1_command == 'budget':
        from researchclaw.core.m1.budgets import set_return_budget
        return set_return_budget(Path(args.root), limit=args.max_returns, note=args.note, command_id=args.command_id)
    if args.m1_command == 'corpus':
        from researchclaw.core.m1.approvals import record_corpus_approval
        return record_corpus_approval(Path(args.root), corpus_binding=args.binding,
                                     decision=args.decision, note=args.note, command_id=args.command_id)
    if args.m1_command == 'council':
        from researchclaw.core.m1.council import (prepare_council, register_final_position,
                                                register_initial, register_response,
                                                read_reviewer_packet, replace_assignment)
        def read(path):
            return json.loads(store._read_file(path), object_pairs_hook=store._unique_pairs)
        if args.council_command == 'prepare':
            return prepare_council(Path(args.root), attempt_id=args.attempt,
                                   assignments=read(args.assignments), command_id=args.command_id)
        if args.council_command == 'packet':
            return read_reviewer_packet(Path(args.root), session_id=args.session, assignment_id=args.assignment)
        if args.council_command == 'replace':
            return replace_assignment(Path(args.root), session_id=args.session, assignment_id=args.assignment,
                                      replacement=read(args.replacement), reason=args.reason, command_id=args.command_id)
        if args.council_command == 'response':
            return register_response(Path(args.root), session_id=args.session, assignment_id=args.assignment,
                                     payload=read(args.submission), command_id=args.command_id)
        if args.council_command == 'decide':
            from researchclaw.core.m1.decisions import register_decision
            return register_decision(Path(args.root), session_id=args.session,
                                     payload=read(args.submission), command_id=args.command_id)
        if args.council_command == 'final':
            return register_final_position(Path(args.root), session_id=args.session,
                                           assignment_id=args.assignment, payload=read(args.submission),
                                           command_id=args.command_id)
        return register_initial(Path(args.root), session_id=args.session, assignment_id=args.assignment,
                                payload=read(args.submission), command_id=args.command_id)
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


def dispatch(args) -> dict:
    from researchclaw.core.m1.council import redact_pending_councils
    return redact_pending_councils(_dispatch(args))
