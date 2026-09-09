"""Freeze each original criterion, then obtain actual independent judgments.

An inconclusive answer leaves the issue checking. A revision never resolves it
by itself. Inputs and mutations all use native registered records/commands.
"""
import concurrent.futures
import json
from live_host import BASE, apply, envelope, head, host_review, node_ref, ref, save, snap, uid
from researchclaw.core.research_graph.gates import _status
from researchclaw.core.research_graph.issues import _Inputs
from researchclaw.core.research_graph.councils import _record_ref
from researchclaw.core.research_graph.m1_nodes import review_node


def judge(job, role, stage):
    issue, verification, verification_ref, material = job
    packet = {'phase': 'final', 'node': 'hypothesize',
              'purpose': '기존 쟁점의 고정 resolution_condition을 현재 수정본이 충족하는지 독립 논리 검증한다. open/checking 상태 자체는 내용 불충족의 이유가 아니다. 실험 결과를 요구하는 조건이라면 자료 없이 통과시키지 않는다.',
              'acceptance_rule': issue['resolution_condition'], 'shared_issues': [issue],
              'input_binding': node_ref('hypothesize'), 'isolation_level': 'instructions_only'}
    return host_review(f'logic-{stage}-{issue["id"]}-{uid()}', role, packet, material)


if __name__ == '__main__':
    inputs = _Inputs(snap())
    issues = [issue for issue in inputs.state['issues'].values()
              if issue['origin']['node'] == 'hypothesize' and issue['severity'] != 'optional'
              and _status(inputs, issue)[0] == 'open']
    owner = next(a for a in inputs.state['assignments'].values() if a['actor_id'] == 'live-source-checker-extract')
    resolver = next(a for a in inputs.state['assignments'].values() if a['actor_id'] == 'live-source-resolver-extract')
    budget = next(v['budget_ref'] for v in inputs.state['verifications'].values() if v['owner_assignment_id'] == owner['id'])
    current = inputs.state['m1_node_revisions'][inputs.state['m1_node_heads']['hypothesize']]
    council = next(c for c in inputs.state['councils'].values() if c['node'] == 'hypothesize' and c['attempt'] == current['attempt'])
    finals = [s for s in inputs.state['council_submissions'].values() if s['session_id'] == council['session_id'] and s['phase'] == 'final']
    assert len(finals) == 3, 'Complete actual re-review before verification'
    outputs = [node_ref('hypothesize'), *[_record_ref(inputs, 'council_submissions', s) for s in finals]]
    jobs = []
    for issue in issues:
        verification = {**envelope(owner['actor_id']), 'issue_ids': [issue['id']], 'method': 'logic_check',
                        'question': issue['question'], 'input_refs': [node_ref('hypothesize')],
                        'acceptance_rule': issue['resolution_condition'], 'owner_assignment_id': owner['id'], 'budget_ref': budget}
        apply('verification.prepare', {'verification': verification})
        verification_ref = ref(verification)
        event = {**envelope(owner['actor_id']), 'issue_id': issue['id'], 'from_status': 'open', 'to_status': 'checking',
                 'actor_assignment_id': owner['id'], 'owner_assignment_id': owner['id'],
                 'rationale': '고정된 기존 해소 조건에 따라 수정본을 독립 논리 검증한다.',
                 'verification_refs': [verification_ref], 'successor_ids': []}
        apply('issue.event', {'issue': None, 'event': event})
        material = {'original_issue': issue, 'current_hypothesis': current, 'actual_final_reviews': finals,
                    'scope': inputs.state['m1_node_revisions'][inputs.state['m1_node_heads']['scope']]}
        jobs.append((issue, verification, verification_ref, material))
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        judgments = list(pool.map(lambda j: judge(j, 'methodology', 'checker'), jobs))
    resolution_jobs = []
    for job, (answer, host) in zip(jobs, judgments):
        issue, verification, verification_ref, material = job
        supported = answer['recommendation'] in ('ready', 'ready_with_limits') and not answer['issues']
        result = {**envelope(owner['actor_id']), 'verification_id': verification['id'],
                  'output_refs': outputs if supported else [], 'outcome': 'supported' if supported else 'inconclusive',
                  'checked_scope': [issue['resolution_condition']] if supported else [],
                  'limitations': [f'합성 논리 검토; 실증 검증 아님. {host}', answer['rationale']]}
        apply('verification.result', {'verification_ref': verification_ref, 'result': result})
        result_ref = ref(result)
        if supported:
            material = {**material, 'verification': verification, 'result': result,
                        'resolver_task': '검증자의 판정과 원문을 독립적으로 비교하여 원래 해소 조건 충족 여부를 결정한다.'}
            resolution_jobs.append(((issue, verification, verification_ref, material), result_ref))
        else:
            print(json.dumps({'issue': issue['id'], 'status': 'checking', 'outcome': 'inconclusive'}), flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        decisions = list(pool.map(lambda j: judge(j[0], 'critical', 'resolver'), resolution_jobs))
    for (job, result_ref), (answer, host) in zip(resolution_jobs, decisions):
        issue = job[0]
        if answer['recommendation'] not in ('ready', 'ready_with_limits') or answer['issues']:
            print(json.dumps({'issue': issue['id'], 'status': 'checking', 'independent_resolution': 'not_accepted'}), flush=True)
            continue
        event = {**envelope(resolver['actor_id']), 'issue_id': issue['id'], 'from_status': 'checking', 'to_status': 'resolved',
                 'actor_assignment_id': resolver['id'], 'rationale': f'{answer["rationale"]} [{host}]',
                 'verification_refs': [result_ref], 'successor_ids': []}
        apply('issue.event', {'issue': None, 'event': event})
        print(json.dumps({'issue': issue['id'], 'status': 'resolved'}), flush=True)
    status = review_node(snap(), 'hypothesize')
    save(BASE / 'hypothesize-after-checks.json', status)
    print(json.dumps({'hypothesis_ready': status['ready'], 'reasons': status['reason_codes']}, ensure_ascii=False), flush=True)
