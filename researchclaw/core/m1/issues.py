"""Response validation and immutable issue discussion projections."""
from __future__ import annotations

from copy import deepcopy


RESPONSE_FIELDS = {'id', 'issue_id', 'assignment_id', 'stance', 'rationale', 'evidence_refs'}
RESPONSE_STANCES = ('accept', 'partly_accept', 'challenge', 'insufficient_evidence')


def _text(value) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _strings(value) -> bool:
    return type(value) is list and all(_text(item) for item in value) and len(set(value)) == len(value)


def _problem(code: str, path: str, message: str) -> dict:
    return {'code': code, 'path': path, 'message': message}


def validate_response(response: dict, *, issue_ids: set[str],
                      assignment_ids: set[str]) -> tuple[dict, ...]:
    """Return structural and reference problems for one issue-linked response."""
    if type(response) is not dict:
        return (_problem('m1_response_invalid', '$', 'response must be an object'),)
    problems = []
    if set(response) != RESPONSE_FIELDS:
        problems.append(_problem('m1_response_invalid', '$',
                                 'response fields must exactly match the response contract'))
    if not _text(response.get('id')):
        problems.append(_problem('m1_response_invalid', 'id', 'id must be a nonempty string'))
    issue_id = response.get('issue_id')
    if not _text(issue_id):
        problems.append(_problem('m1_response_invalid', 'issue_id',
                                 'issue_id must be a nonempty string'))
    elif issue_id not in issue_ids:
        problems.append(_problem('m1_unknown_issue', 'issue_id',
                                 'issue_id must identify a disclosed issue'))
    assignment_id = response.get('assignment_id')
    if not _text(assignment_id):
        problems.append(_problem('m1_response_invalid', 'assignment_id',
                                 'assignment_id must be a nonempty string'))
    elif assignment_id not in assignment_ids:
        problems.append(_problem('m1_unknown_assignment', 'assignment_id',
                                 'assignment_id must identify an active assignment'))
    if response.get('stance') not in RESPONSE_STANCES:
        problems.append(_problem('m1_response_invalid', 'stance',
                                 'stance must be one of the declared response stances'))
    if not _text(response.get('rationale')):
        problems.append(_problem('m1_response_invalid', 'rationale',
                                 'rationale must be a nonempty string'))
    if not _strings(response.get('evidence_refs')):
        problems.append(_problem('m1_response_invalid', 'evidence_refs',
                                 'evidence_refs must be a unique list of nonempty strings'))
    return tuple(problems)


def _by_assignment(values) -> list[dict]:
    if type(values) is dict:
        return [values[key] for key in sorted(values)]
    if type(values) is list:
        return values
    return []


def collect_issues(session: dict) -> tuple[dict, ...]:
    """Collect preserved initial and response-round issues in publication order."""
    collected = []
    initials = session.get('disclosed_initials') or _by_assignment(session.get('initials', {}))
    for position in initials:
        for issue in position.get('open_issues', []):
            collected.append({'origin_phase': 'initial', 'issue': deepcopy(issue)})
    for bundle in _by_assignment(session.get('responses', {})):
        for issue in bundle.get('new_issues', []):
            collected.append({'origin_phase': 'response', 'issue': deepcopy(issue)})
    return tuple(collected)


def build_issue_threads(session: dict) -> tuple[dict, ...]:
    """Project issues to their responses and per-role final dispositions.

    The original issue and response records are copied, never coalesced or
    rewritten. Related issues remain explicit links. A response-round issue
    additionally needs one other role to confirm resolution; every issue needs
    its raiser's confirmation, including blockers.
    """
    responses = _by_assignment(session.get('responses', {}))
    positions = _by_assignment(session.get('final_positions', {}))
    threads = []
    for source in collect_issues(session):
        issue = source['issue']
        issue_id = issue['id']
        replies = [deepcopy(reply) for bundle in responses
                   for reply in bundle.get('responses', []) if reply.get('issue_id') == issue_id]
        dispositions = []
        for position in positions:
            match = next((d for d in position.get('issue_dispositions', [])
                          if d.get('issue_id') == issue_id), None)
            if match is not None:
                dispositions.append({'assignment_id': position['assignment_id'], **deepcopy(match)})
        confirmed = sorted(d['assignment_id'] for d in dispositions if d['status'] == 'resolved')
        raiser_confirmed = issue['raised_by'] in confirmed
        requires_other = source['origin_phase'] == 'response'
        other_confirmed = any(assignment_id != issue['raised_by'] for assignment_id in confirmed)
        resolved = raiser_confirmed and (not requires_other or other_confirmed)
        threads.append({'issue': deepcopy(issue), 'origin_phase': source['origin_phase'],
                        'responses': replies, 'final_dispositions': dispositions,
                        'status': 'resolved' if resolved else 'open',
                        'resolution_confirmed_by': confirmed,
                        'raiser_confirmed': raiser_confirmed,
                        'requires_other_role_confirmation': requires_other})
    return tuple(threads)
