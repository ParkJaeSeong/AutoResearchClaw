"""Agent-facing commands share exactly the UI service operations."""
import argparse
import math
import json
import sys
import time
from pathlib import Path
from .atlas_service_http import FIELDS, dispatch


def _interval(value):
    number = float(value)
    if not math.isfinite(number) or not 1 <= number <= 60:
        raise argparse.ArgumentTypeError('interval must be between 1 and 60 seconds')
    return number


def add_parser(actions):
    parser=actions.add_parser('atlas-service',help='Connect to Atlas and resume durable research questions')
    commands=parser.add_subparsers(dest='service_action',required=True)
    outcome = commands.add_parser('outcome', help='Record a coordinator decision using completed council submissions')
    outcome.add_argument('root', type=Path)
    outcome.add_argument('--key', required=True)
    outcome.add_argument('--file', required=True, type=Path)
    outcome.add_argument('--json', action='store_true')
    council = commands.add_parser('review', help='Run or resume independent and cross reviews of a received research answer')
    council.add_argument('root', type=Path)
    council.add_argument('--key', required=True)
    council.add_argument('--host', required=True, type=Path)
    council.add_argument('--json', action='store_true')
    native = commands.add_parser('ask-question', help='Submit a registered research question with its decision context')
    native.add_argument('root', type=Path)
    native.add_argument('--key', required=True)
    native.add_argument('--question-id', required=True)
    native.add_argument('--previous')
    native.add_argument('--json', action='store_true')
    advance = commands.add_parser('advance', help='Resume a request through evidence input preparation')
    advance.add_argument('root', type=Path)
    advance.add_argument('--key', required=True)
    advance.add_argument('--watch', action='store_true', help='Observe until ready or attention is required; interruption preserves the job')
    advance.add_argument('--interval', type=_interval, default=10)
    advance.add_argument('--json', action='store_true')
    for name in ('connect','status','bind','ask','poll','receive','supporting'):
        command=commands.add_parser(name)
        command.add_argument('root',type=Path)
        command.add_argument('--json',action='store_true')
        for field in sorted(FIELDS['service-'+name]):
            command.add_argument('--'+field.replace('_','-'),required=field!='previous')


def run(args):
    if args.service_action == 'outcome':
        from .atlas_outcome import record_outcome
        from .atlas_service_http import configured_session
        return record_outcome(configured_session(args.root), args.key, json.loads(args.file.read_text()))
    if args.service_action == 'review':
        from .atlas_council import run_council
        from .atlas_reviewer import host_reviewer
        from .atlas_service_http import configured_session
        return run_council(configured_session(args.root), args.key, host_reviewer(args.host))
    if args.service_action == 'ask-question':
        from .atlas_question import ask_research_question
        from .atlas_service_http import configured_session
        return ask_research_question(configured_session(args.root), args.key, args.question_id, args.previous)
    if args.service_action == 'advance':
        from .atlas_advance import advance_request
        from .atlas_service_http import configured_session
        session = configured_session(args.root)
        while True:
            result = advance_request(session, args.key)
            if not args.watch or result['stage'] != 'waiting_for_atlas':
                return result
            print('Atlas가 답변을 준비하고 있습니다. 중단해도 같은 요청으로 재개할 수 있습니다.', file=sys.stderr, flush=True)
            time.sleep(args.interval)
    action='service-'+args.service_action
    return dispatch(args.root,action,{key:getattr(args,key) for key in FIELDS[action]})
