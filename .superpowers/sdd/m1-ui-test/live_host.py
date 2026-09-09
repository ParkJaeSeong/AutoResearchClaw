"""Acceptance-only Codex host: native CLI writes, real independent role outputs.

No checkpoint seeding and no manufactured reviewer votes. This is a synthetic
case, not authenticated research. Role separation is instructions_only.
"""
import concurrent.futures
import hashlib
import json
from pathlib import Path
import subprocess
from uuid import uuid4

from researchclaw.core.research_graph import commands, store
from researchclaw.core.research_graph.m1_nodes import current_node, _context

BASE = Path(__file__).resolve().parent
REPO = BASE.parents[2]
ROOT = BASE / 'native-live-project'
CLI = REPO / '.venv/bin/researchclaw-codex'
HOST = Path('/Users/jspark/.local/bin/codex')
ROLES = ('domain', 'methodology', 'critical')


def uid():
    return str(uuid4())


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2))


def cli(*args):
    process = subprocess.run([str(CLI), 'research', *map(str, args), '--json'],
                             cwd=REPO, capture_output=True, text=True, check=False)
    if process.returncode:
        raise RuntimeError(process.stderr or process.stdout)
    return json.loads(process.stdout)


def head():
    return store.read_head(ROOT)


def snap():
    return commands.read_policy_snapshot(ROOT)


def apply(operation, payload):
    identity = uid()
    path = BASE / 'commands' / f'{identity}.json'
    save(path, payload)
    result = cli('apply', ROOT, '--operation', operation, '--payload', path,
                 '--expected-head', head()['id'], '--command-id', identity)
    with (BASE / 'command-log.jsonl').open('a') as stream:
        stream.write(json.dumps({'operation': operation, 'payload_file': str(path),
                                'receipt': result}, ensure_ascii=False) + '\n')
    return result


def envelope(producer='case-author'):
    return {**store._VERSION, 'project_id': head()['state']['project_id'],
            'id': uid(), 'event_id': uid(), 'producer_id': producer,
            'content_origin': 'synthetic', 'provenance_status': 'declared_only',
            'observation_refs': []}


def ref(record, alias=None):
    return {'project_id': head()['state']['project_id'], 'head_id': head()['id'],
            'artifact_id': alias or record['id'],
            'sha256': hashlib.sha256(store._canonical(record)).hexdigest()}


def node_ref(node):
    return current_node(_context(snap()), node)[1]


def register(node, content, parents=(), reason=None):
    previous = node_ref(node) if node in head()['state'].get('m1_node_heads', {}) else None
    artifact = {**envelope(), 'node': node, 'attempt': uid(), 'previous_ref': previous,
                'input_refs': {name: node_ref(name) for name in parents},
                'content': content, 'revision_reason': reason}
    apply('m1.node.register', {'artifact': artifact})
    return artifact


SCHEMA = {'type': 'object', 'additionalProperties': False,
          'required': ['rationale', 'recommendation', 'issues'],
          'properties': {
              'rationale': {'type': 'string'},
              'recommendation': {'type': ['string', 'null'],
                                 'enum': ['ready', 'ready_with_limits', 'revise', 'defer', None]},
              'issues': {'type': 'array', 'items': {
                  'type': 'object', 'additionalProperties': False,
                  'required': ['question', 'category', 'severity', 'resolution_condition'],
                  'properties': {'question': {'type': 'string'},
                                 'category': {'type': 'string', 'enum': ['scope', 'source', 'logic', 'methodology', 'empirical', 'other']},
                                 'severity': {'type': 'string', 'enum': ['blocking', 'major', 'optional']},
                                 'resolution_condition': {'type': 'string'}}}}}}


def host_review(label, role, packet, materials):
    run = BASE / 'host-runs' / f'{label}-{role}'
    run.mkdir(parents=True, exist_ok=False)
    save(run / 'packet.json', packet)
    save(run / 'materials.json', materials)
    save(run / 'schema.json', SCHEMA)
    persona = {
        'domain': '연구 질문의 의미, 모집단·지표·주장 범위와 제공 자료의 적합성을 검토한다.',
        'methodology': '반증 가능성, 대안 설명, 표본 구성과 인과 추론의 한계를 검토한다.',
        'critical': '근거 없는 일반화·불일치·숨은 전제를 찾고 미해결 반론을 보존한다.',
    }[role]
    prompt = f'''당신은 실제 연구 검토자 {role}입니다. {persona}
이것은 합성 자료를 쓰는 M1 개발 수용 테스트입니다. 실제 문헌 검색·실험 결과로 오인하지 마세요.
도구 사용이나 파일 탐색 없이 아래 제공된 역할 packet과 정확한 허용 자료만 검토하세요.
첫 의견에서는 다른 검토자의 의견을 보지 못합니다. 반박/최종에서는 packet에 공개된 의견만 참고하세요.
노드별 검토 목적을 판단하세요. scope/questions/search는 연구 계획의 적합성이지 실험 입증이 아닙니다.
합의나 통과를 강요하지 않습니다. 동의는 제공 근거로 설명하고 부족한 정보는 그대로 남기세요.
초기 과학 가설도 사실로 확정한 표현이면 지적하세요. 자료가 없다는 이유만으로 모든 계획을 거부하지 마세요.
한국어 rationale 약 150단어 이내. final에서만 recommendation을 선택하고 다른 단계는 null로 하세요.
issues에는 새로 발견한 구체적 쟁점만, 이미 공개되거나 본인이 제기한 동일 쟁점은 rationale에서 추적하세요.
중요도를 스스로 판단하세요. 선택적 개선은 optional, 현재 노드 진행을 막는 문제는 major/blocking입니다.
구조화된 JSON으로 응답하세요.
PACKET:\n{json.dumps(packet, ensure_ascii=False)}
MATERIALS:\n{json.dumps(materials, ensure_ascii=False)}'''
    (run / 'prompt.txt').write_text(prompt)
    process = subprocess.run([str(HOST), 'exec', '--ephemeral', '--sandbox', 'read-only',
                              '--skip-git-repo-check', '--json', '--output-schema', str(run / 'schema.json'),
                              '--output-last-message', str(run / 'answer.json'), '-'],
                             input=prompt, cwd='/tmp', capture_output=True, text=True)
    (run / 'events.jsonl').write_text(process.stdout)
    (run / 'stderr.txt').write_text(process.stderr)
    if process.returncode:
        raise RuntimeError(f'Host failed: {run}; {process.stderr[-500:]}')
    events = [json.loads(line) for line in process.stdout.splitlines() if line.startswith('{')]
    if any(e.get('item', {}).get('type') in ('command_execution', 'mcp_tool_call') for e in events):
        raise RuntimeError(f'Unexpected role tool access: {run}')
    thread = next(e['thread_id'] for e in events if e['type'] == 'thread.started')
    answer = json.loads((run / 'answer.json').read_text())
    return answer, f'codex-exec:{thread}'


def council(artifact):
    binding = node_ref(artifact['node'])
    project = head()['state']['project_id']
    author = dict(id=uid(), project_id=project, actor_id='case-author', role='owner', milestone='M1', active=True)
    reviewers = [dict(id=uid(), project_id=project, actor_id=f'live-{role}', role='resolver', milestone='M1', active=True)
                 for role in ROLES]
    session = dict(id=uid(), project_id=project, input_binding=binding,
                   participant_assignment_ids=[actor['id'] for actor in reviewers], frozen=True)
    record = {**envelope('coordinator'), 'session_id': session['id'], 'milestone': 'M1',
              'node': artifact['node'], 'attempt': artifact['attempt'],
              'author_assignment_ids': [author['id']],
              'required_roles': dict(zip(ROLES, [a['id'] for a in reviewers])),
              'allowed_evidence_refs': [], 'issue_ids': list(head()['state'].get('issues', {}))}
    apply('council.prepare', {'assignments': [author, *reviewers], 'review_session': session, 'council': record})
    published = []
    for phase in ('initial', 'response', 'final'):
        jobs = []
        # Freeze every participant's input before any submission in this phase.
        for role, actor in zip(ROLES, reviewers):
            packet = cli('packet', ROOT, '--assignment', actor['id'])
            objects = snap()['_issue_context']['objects']
            materials = [{'ref': r, 'text': objects[r['sha256']].decode('utf-8')}
                         for r in packet['allowed_evidence_refs']]
            jobs.append((role, actor, packet, materials))
        label = f"{artifact['node']}-{artifact['attempt']}-{phase}"
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            futures = [pool.submit(host_review, label, role, packet, materials)
                       for role, _, packet, materials in jobs]
            answers = [future.result() for future in futures]
        proposals = []
        for (role, actor, packet, _), (answer, host_id) in zip(jobs, answers):
            issues = []
            for item in answer['issues']:
                issue = {**envelope(actor['actor_id']), **item,
                         'origin': {'milestone': 'M1', 'node': artifact['node'],
                                    'attempt': artifact['attempt'], 'local_issue_id': uid()},
                         'target_refs': [binding], 'blocking_scope': [{'kind': 'node', 'milestone': 'M1', 'target_id': artifact['node']}],
                         'owner_assignment_id': author['id']}
                issues.append(issue)
                proposals.append((issue, actor))
            prior = packet['disclosed_initials'] if phase == 'response' else packet['disclosed_responses']
            submission = {**envelope(actor['actor_id']), 'session_id': session['id'], 'assignment_id': actor['id'],
                          'input_binding': binding, 'phase': phase, 'rationale': answer['rationale'],
                          'evidence_refs': [binding], 'positions': [], 'retained_position_refs': [],
                          'response_refs': [row['submission_ref'] for row in prior] if phase != 'initial' else [],
                          'issue_proposals': issues, 'recommendation': answer['recommendation'],
                          'host_id': host_id, 'model_id': 'codex-cli-default-unverified'}
            apply('council.submit', {'submission': submission})
        # Publish only after the whole phase has disclosed. Publication is not resolution.
        for issue, actor in proposals:
            event = {**envelope(actor['actor_id']), 'issue_id': issue['id'], 'from_status': None, 'to_status': 'open',
                     'actor_assignment_id': actor['id'], 'rationale': '실제 검토자 제출의 공개된 쟁점을 원문 그대로 게시',
                     'verification_refs': [], 'successor_ids': []}
            apply('issue.event', {'issue': issue, 'event': event})
            published.append(issue)
        print(json.dumps({'node': artifact['node'], 'phase': phase, 'new_issues': len(proposals),
                          'head_id': head()['id']}, ensure_ascii=False), flush=True)
    return published
