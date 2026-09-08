"""M1 hypothesis structure and immutable revision history, never scientific approval.

The JSON envelope contains schema_version=1 and a cumulative hypotheses list.
An empty list requires no_hypotheses_reason. Historical records are retained
exactly; only new records are validated against the current bound evidence.
Author assignment IDs are declarations: inequality does not authenticate hosts.
"""
from __future__ import annotations

from . import store
from .synthesis import EXTRACTIONS, SYNTHESIS, _claims, _json, validate_synthesis_record

HYPOTHESES = 'hypotheses/hypotheses.json'
DISPOSITIONS = {'draft', 'revise', 'selected', 'rejected', 'deferred'}


def _string(value):
    return isinstance(value, str) and bool(value.strip())


def hypothesis_key(record: dict) -> tuple[str, int]:
    return record['id'], record['revision']


def can_review(*, author_assignment_id: str, reviewer_assignment_id: str) -> bool:
    """Pure assignment separation only; callers must verify assignment provenance."""
    return author_assignment_id != reviewer_assignment_id


def validate_hypothesis(record: dict, *, claim_ids: set[str], gap_ids: set[str]) -> tuple[dict, ...]:
    """Validate one candidate's fields and references, without judging its truth."""
    issues = []

    def invalid(path, message):
        issues.append({'code': 'm1_hypothesis_invalid', 'path': path, 'message': message})

    if type(record) is not dict:
        return ({'code': 'm1_hypothesis_invalid', 'message': 'Expected an object'},)
    for key in ('id', 'author_assignment_id', 'statement', 'predicted_observation',
                'falsification_condition', 'feasibility_notes'):
        if not _string(record.get(key)):
            invalid(key, 'Required nonempty string')
    revision = record.get('revision')
    if type(revision) is not int or revision < 1:
        invalid('revision', 'Required positive integer')
    elif revision == 1:
        for key in ('parent_revision', 'change_reason'):
            if key not in record or record[key] is not None:
                invalid(key, 'Initial revision requires explicit null')
    else:
        if type(record.get('parent_revision')) is not int or record['parent_revision'] != revision - 1:
            invalid('parent_revision', 'Required immediately preceding revision')
        if not _string(record.get('change_reason')):
            invalid('change_reason', 'A new revision requires an explicit change reason')
    for key in ('alternatives', 'open_design_questions'):
        if type(record.get(key)) is not list or not all(_string(item) for item in record[key]):
            invalid(key, 'Required list of nonempty strings')
    if not isinstance(record.get('disposition'), str) or record['disposition'] not in DISPOSITIONS:
        invalid('disposition', 'Unknown hypothesis disposition')
    for key, known, code in (('claim_refs', claim_ids, 'm1_unknown_claim'),
                              ('gap_refs', gap_ids, 'm1_unknown_gap')):
        refs = record.get(key)
        if (type(refs) is not list or not all(_string(ref) for ref in refs)
                or len(set(refs)) != len(refs)):
            invalid(key, 'Required unique nonempty reference strings')
            continue
        for ref in refs:
            if ref not in known:
                issues.append({'code': code, 'path': key, 'reference': ref})
    if record.get('claim_refs') == [] and record.get('gap_refs') == []:
        invalid('claim_refs', 'A candidate requires a bound claim or gap reference')
    return tuple(issues)


def _records(envelope):
    if (type(envelope) is not dict or type(envelope.get('schema_version')) is not int
            or envelope['schema_version'] != 1 or type(envelope.get('hypotheses')) is not list):
        raise ValueError('m1_hypotheses_envelope_invalid')
    if not envelope['hypotheses'] and not _string(envelope.get('no_hypotheses_reason')):
        raise ValueError('m1_no_hypotheses_reason_required')
    records = {}
    for record in envelope['hypotheses']:
        if (type(record) is not dict or not _string(record.get('id'))
                or type(record.get('revision')) is not int or record['revision'] < 1):
            raise ValueError('m1_hypothesis_invalid')
        key = hypothesis_key(record)
        if key in records:
            raise ValueError('m1_hypothesis_duplicate_revision')
        records[key] = record
    return records


def validate_hypothesis_contents(files: dict[str, bytes], inputs: dict[str, bytes]) -> tuple[dict, ...]:
    """Validate the authoritative JSON using immutable, packet-bound inputs.

Prior records resolve to their original registration and evidence binding; they
are compared byte-canonically instead of being reinterpreted with new evidence.
New revisions require a parent in the registered prior envelope, never merely
another record supplied in the same draft.
"""
    try:
        current = _records(_json(files[HYPOTHESES]))
        previous = _records(_json(inputs[HYPOTHESES])) if HYPOTHESES in inputs else {}
        claim_ids = set(_claims(inputs[EXTRACTIONS]))
        synthesis = _json(inputs[SYNTHESIS])
        synthesis_issues = validate_synthesis_record(synthesis, known_claim_ids=claim_ids)
        if synthesis_issues:
            return synthesis_issues
        gap_ids = {gap['id'] for gap in synthesis['gaps']}
    except (KeyError, ValueError, TypeError, UnicodeError) as exc:
        return ({'code': 'm1_hypotheses_input_invalid', 'message': str(exc)},)
    issues = []
    for key, prior in previous.items():
        if key not in current or store._canonical(current[key]) != store._canonical(prior):
            issues.append({'code': 'm1_hypothesis_history_changed', 'id': key[0], 'revision': key[1]})
    latest = {}
    for identifier, revision in previous:
        latest[identifier] = max(revision, latest.get(identifier, 0))
    for key, record in current.items():
        if key in previous:
            continue
        issues.extend({**issue, 'id': key[0], 'revision': key[1]} for issue in
                      validate_hypothesis(record, claim_ids=claim_ids, gap_ids=gap_ids))
        expected = latest.get(key[0], 0) + 1
        if key[1] != expected:
            issues.append({'code': 'm1_hypothesis_parent_missing', 'id': key[0], 'revision': key[1]})
        elif key[1] > 1:
            parent = previous[(key[0], key[1] - 1)]
            if record.get('author_assignment_id') != parent.get('author_assignment_id'):
                issues.append({'code': 'm1_hypothesis_author_changed', 'id': key[0], 'revision': key[1]})
    return tuple(issues)
