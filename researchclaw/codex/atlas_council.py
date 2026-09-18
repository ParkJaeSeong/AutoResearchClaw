"""Durable Atlas evidence councils using the existing phase and provenance rules."""
import fcntl
import json
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from researchclaw.core.research_graph import commands, store
from researchclaw.core.research_graph.councils import reviewer_packet
from .atlas_advance import advance_request
from .atlas_client import AtlasError
from .atlas_episode import CouncilEpisode

ROLES = ('domain', 'methodology', 'critical')


def _saved(path, make):
    if path.exists():
        return json.loads(path.read_text())
    value = make()
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2))
    temporary.replace(path)
    return value


def run_council(session, key, reviewer):
    """reviewer(role, phase, packet, frozen_materials, run_dir) supplies real answers."""
    row = session._get(key)
    if not row.get('research_context'):
        raise AtlasError('atlas_research_context_required')
    base = store._checked_path(session.base / ('council-' + store._hash(key.encode())))
    base.mkdir(exist_ok=True)
    with (base/'run.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise AtlasError('atlas_council_busy', retryable=True) from None
        return _run(session, key, reviewer, base)


def _run(session, key, reviewer, base):
    result_path = base/'result.json'
    if result_path.exists():
        return json.loads(result_path.read_text())
    shared = advance_request(session, key)
    if shared['stage'] != 'review_input_ready':
        return shared
    material = shared['packet']
    if material.get('schema_version') != 2 or not material.get('research_context'):
        raise AtlasError('atlas_review_input_version_unsupported')
    project = session.project_id
    origin = store.read_head(session.root)['state']['content_origin']

    def envelope(actor='pilot-coordinator'):
        return {**store._VERSION, 'project_id':project, 'id':str(uuid4()), 'event_id':str(uuid4()),
                'producer_id':actor, 'content_origin':origin, 'provenance_status':'declared_only', 'observation_refs':[]}

    def apply(name, operation, make):
        payload = _saved(base/(name+'-payload.json'), make)
        receipt = _saved(base/(name+'-receipt.json'), lambda: commands.apply_command(session.root,
            operation=operation, payload=payload, expected_head=store.read_head(session.root)['id'],
            command_id='atlas-council:'+store._hash((key+':'+name).encode())))
        return payload, receipt

    episode = CouncilEpisode(key, apply)
    episode.start(shared)
    context = material['research_context']
    _, receipt = apply('review', 'external.review.record', lambda: dict(
        evidence_ref=material['evidence_ref'], question_ref=context['question_ref'], status='limited',
        allowed_uses=['보유 자료의 공백과 적용 범위를 교차 검토하는 입력'],
        held_uses=['원문 직접 검증 완료 또는 실험 조건 확정의 근거'],
        limitations=['Atlas 제공 해석이다. 원문 수신과 Pilot의 직접 원문 읽기는 다르다.',
                     '이 등록은 검토 입력의 용도 선언이며 검토 결론은 후속 협의에서 기록한다.'],
        rationale='정식 후속 질문과 Atlas 답변을 연결해 검토한다. 고정 입력 해시: '+shared['packet_sha256'],
        producer_id='pilot-coordinator'))
    record_id = receipt['events'][-1]['payload']['record_id']
    review = receipt['state']['external_reviews'][record_id]
    review_ref = dict(project_id=project, head_id=receipt['id'], artifact_id=record_id,
                      sha256=store._hash(store._canonical(review)))

    def setup():
        owner = dict(id=str(uuid4()), project_id=project, actor_id='pilot-coordinator', role='owner', milestone='M1', active=True)
        actors = [dict(id=str(uuid4()), project_id=project, actor_id='atlas-loop-'+r+'-'+str(uuid4()), role='resolver', milestone='M1', active=True) for r in ROLES]
        review_session = dict(id=str(uuid4()), project_id=project, input_binding=review_ref,
                             participant_assignment_ids=[a['id'] for a in actors], frozen=True)
        council = {**envelope(), 'session_id':review_session['id'], 'milestone':'M1', 'node':'atlas-evidence-review',
                   'attempt':str(uuid4()), 'author_assignment_ids':[owner['id']],
                   'required_roles':dict(zip(ROLES,[a['id'] for a in actors])),
                   'allowed_evidence_refs':[material['evidence_ref'],context['question_ref']], 'issue_ids':[]}
        return dict(assignments=[owner,*actors], review_session=review_session, council=council)
    setup_payload, _ = apply('prepare','council.prepare',setup)
    council = setup_payload['council']; actors = setup_payload['assignments'][1:]
    for phase in ('initial','response','final'):
        # Snapshot all participants before running or publishing any opinion.
        snapshot = commands.read_policy_snapshot(session.root)
        packets = [_saved(base/(phase+'-'+role+'-packet.json'), lambda a=a: reviewer_packet(snapshot,a['id'])) for role,a in zip(ROLES,actors)]
        def invoke(pair):
            role, packet = pair
            run = base/(phase+'-'+role); run.mkdir(exist_ok=True)
            return _saved(run/'verified.json', lambda: reviewer(role,phase,packet,shared,run))
        with ThreadPoolExecutor(max_workers=3) as pool:
            results = list(pool.map(invoke,zip(ROLES,packets)))
        for role, actor, packet, result in zip(ROLES,actors,packets,results):
            answer = result['answer']
            prior = packet['disclosed_initials'] if phase=='response' else packet['disclosed_responses']
            def submit():
                return dict(submission={**envelope(actor['actor_id']), 'session_id':council['session_id'],
                    'assignment_id':actor['id'], 'input_binding':review_ref, 'phase':phase,
                    'rationale':answer['rationale'], 'evidence_refs':[review_ref,material['evidence_ref'],context['question_ref']],
                    'positions':[], 'retained_position_refs':[],
                    'response_refs':[r['submission_ref'] for r in prior] if phase!='initial' else [],
                    'issue_proposals':[], 'recommendation':answer['recommendation'],
                    'host_id':result['host_id'], 'model_id':result['model_id']})
            apply(phase+'-'+role, 'council.submit',submit)
        episode.phase(phase, ROLES, results)
    packet = reviewer_packet(commands.read_policy_snapshot(session.root), actors[0]['id'])
    result = dict(stage='council_complete', review_ref=review_ref, council_id=council['id'],
                  packet_sha256=shared['packet_sha256'], submission_refs=[r['submission_ref'] for r in packet['disclosed_finals']],
                  finals=[r['submission'] for r in packet['disclosed_finals']])
    episode.finish(result)
    return _saved(result_path,lambda:result)
