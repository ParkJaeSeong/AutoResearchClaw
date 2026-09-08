"""M1 synthesis structure and read-only, version-pinned evidence lineage.

``claims`` contains extraction claim IDs. Agreements have id/claim_refs/summary;
conflicts have id/claim_refs/interpretations/open_questions; gaps have
id/question/claim_refs. Unreferenced gaps/conflicts must explicitly declare
status=unverified_question and a nonempty reason. No cardinality or scientific
truth is inferred. The legacy Markdown synthesis validator is unchanged.

trace_claim consumes a read_trace_head snapshot, not a plain store receipt.
Its object bytes are keyed by digest, never logical path, so older references
cannot accidentally resolve to newer evidence. This transient context is not
persisted and does not change the store's public receipt schema.
"""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

from . import store

SYNTHESIS = 'knowledge/synthesis.json'
EXTRACTIONS = 'knowledge/extractions.jsonl'


def _string(value):
    return isinstance(value, str) and bool(value.strip())


def _strings(value):
    return type(value) is list and all(_string(item) for item in value)


def validate_synthesis_record(record: dict, *, known_claim_ids: set[str]) -> tuple[dict, ...]:
    """Check reference/record structure only; retain unresolved contradictions."""
    issues = []

    def invalid(path, message):
        issues.append({'code': 'm1_synthesis_invalid', 'path': path, 'message': message})

    def references(refs, path):
        if not _strings(refs) or len(set(refs)) != len(refs):
            invalid(path, 'Expected unique nonempty claim ID strings')
            return False
        for ref in refs:
            if ref not in known_claim_ids:
                issues.append({'code': 'm1_unknown_claim', 'path': path, 'claim_id': ref})
        return True

    if type(record) is not dict:
        return ({'code': 'm1_synthesis_invalid', 'message': 'Expected an object'},)
    for key in ('claims', 'agreements', 'conflicts', 'gaps', 'limitations'):
        if type(record.get(key)) is not list:
            invalid(key, 'Required list')
    if issues:
        return tuple(issues)
    references(record['claims'], 'claims')
    if not _strings(record['limitations']):
        invalid('limitations', 'Expected nonempty strings')
    ids = set()
    for section in ('agreements', 'conflicts', 'gaps'):
        for index, item in enumerate(record[section]):
            path = f'{section}[{index}]'
            if type(item) is not dict:
                invalid(path, 'Expected an object')
                continue
            identifier = item.get('id')
            if not _string(identifier) or identifier in ids:
                invalid(path + '.id', 'Expected unique nonempty ID')
            else:
                ids.add(identifier)
            refs = item.get('claim_refs')
            if references(refs, path + '.claim_refs') and not refs:
                if (section == 'agreements' or item.get('status') != 'unverified_question'
                        or not _string(item.get('reason'))):
                    invalid(path, 'Unreferenced questions require unverified_question status and reason')
            if section == 'conflicts':
                for key in ('interpretations', 'open_questions'):
                    if not _strings(item.get(key)):
                        invalid(path + '.' + key, 'Required string list')
            else:
                key = 'question' if section == 'gaps' else 'summary'
                if not _string(item.get(key)):
                    invalid(path + '.' + key, 'Required nonempty string')
    return tuple(issues)


def synthesis_status(record: dict) -> dict:
    """Describe evidence limits separately from validation or council readiness.

Call after validation. Referenced gaps remain scientific review candidates;
the word 'verified' in the reason code does not certify their scientific truth.
Claims can motivate a hypothesis even without an asserted evidence gap.
"""
    reasons = []
    if not _used_claim_ids(record):
        reasons.append('no_claims')
    if not any(gap['claim_refs'] and gap.get('status') != 'unverified_question' for gap in record['gaps']):
        reasons.append('no_verified_gaps')
    return {'hypothesis_possible': bool(_used_claim_ids(record)), 'reasons': reasons,
            'scientific_validation': 'not_performed', 'handoff_readiness': 'not_assessed'}


def _used_claim_ids(record):
    used = set(record['claims'])
    for section in ('agreements', 'conflicts', 'gaps'):
        for item in record[section]:
            used.update(item['claim_refs'])
    return used


def _json(data):
    value = json.loads(data, object_pairs_hook=store._unique_pairs)
    store._canonical(value)
    return value


def _claims(data):
    rows = [_json(line) for line in data.splitlines() if line.strip()]
    if any(type(row) is not dict or not _string(row.get('claim_id')) for row in rows):
        raise ValueError('m1_synthesis_extractions_invalid')
    if len({row['claim_id'] for row in rows}) != len(rows):
        raise ValueError('m1_synthesis_extractions_invalid')
    return {row['claim_id']: row for row in rows}


def validate_synthesis_contents(files: dict[str, bytes], inputs: dict[str, bytes]) -> tuple[dict, ...]:
    try:
        return validate_synthesis_record(_json(files[SYNTHESIS]),
                                         known_claim_ids=set(_claims(inputs[EXTRACTIONS])))
    except (KeyError, ValueError, TypeError, UnicodeError, AttributeError, RecursionError) as exc:
        return ({'code': 'm1_synthesis_invalid', 'message': str(exc)},)


def read_trace_head(root: Path, *, synthesis_ref_id: str | None = None) -> dict:
    """Hydrate registered snapshots without mutation, network access or drafts."""
    from .artifacts import read_registered_inputs
    from .approvals import corpus_status

    head = store.read_head(root)
    refs = head['state'].get('artifacts', [])
    candidates = [ref for ref in refs if ref['logical_path'] == SYNTHESIS
                  and (synthesis_ref_id is None or ref['id'] == synthesis_ref_id)]
    if not candidates:
        raise ValueError('m1_trace_synthesis_missing')
    head['trace_synthesis_ref'] = deepcopy(candidates[-1])
    head['trace_object_bytes'] = {}
    # Read only committed artifacts, including retained versions. Each consumed
    # descriptor and byte snapshot is checked again below before tracing.
    for ref in refs:
        head['trace_object_bytes'][ref['sha256']] = read_registered_inputs(root, [ref])[ref['logical_path']]
    try:
        head['trace_current_authorization'] = corpus_status(root, head)
    except ValueError as exc:
        head['trace_current_authorization'] = {'approved': False, 'error': str(exc)}
    return head


def _bytes(head, ref):
    if ref not in head['state'].get('artifacts', []):
        raise ValueError('m1_trace_reference_invalid')
    digest = ref.get('sha256')
    if head['objects'].get(digest) != {'sha256': digest, 'size': ref.get('size')}:
        raise ValueError('m1_trace_reference_invalid')
    data = head['trace_object_bytes'].get(digest)
    if data is None:
        raise ValueError('m1_trace_object_missing')
    if type(data) is not bytes or len(data) != ref['size'] or store._hash(data) != digest:
        raise ValueError('m1_input_content_changed')
    return data


def _one_ref(refs, path):
    matches = [ref for ref in refs if ref.get('logical_path') == path]
    if len(matches) != 1:
        raise ValueError('m1_trace_reference_missing_or_ambiguous')
    return matches[0]


def _producer(head, ref, node):
    matches = [attempt for attempt in head['state']['attempts']
               if attempt['id'] == ref['producer_attempt_id'] and attempt['node_id'] == node]
    if len(matches) != 1 or ref not in matches[0]['output_refs']:
        raise ValueError('m1_trace_producer_missing')
    return matches[0]


def trace_claim(head: dict, claim_id: str) -> dict:
    """Follow the selected synthesis's exact evidence and historical approval.

Original source files are not registered by the current collection contract.
Locators/URLs and access declarations are therefore reported as declarations,
never as proof that original full text was retrieved or checked.
"""
    from .approvals import CORPUS_PATHS, _current_approval

    if not all(key in head for key in ('trace_synthesis_ref', 'trace_object_bytes', 'trace_current_authorization')):
        raise ValueError('m1_trace_context_missing')
    synthesis_ref = head['trace_synthesis_ref']
    synthesis = _json(_bytes(head, synthesis_ref))
    synthesis_attempt = _producer(head, synthesis_ref, 'synthesize')
    extraction_ref = _one_ref(synthesis_attempt['input_refs'], EXTRACTIONS)
    claims = _claims(_bytes(head, extraction_ref))
    if validate_synthesis_record(synthesis, known_claim_ids=set(claims)):
        raise ValueError('m1_trace_synthesis_invalid')
    used_ids = _used_claim_ids(synthesis)
    if not _string(claim_id) or claim_id not in used_ids or claim_id not in claims:
        raise ValueError('m1_unknown_claim')
    claim = claims[claim_id]
    attempt = _producer(head, extraction_ref, 'extract')
    corpus_refs = [_one_ref(attempt['input_refs'], path) for path in CORPUS_PATHS]
    corpus_refs.sort(key=lambda ref: (ref['id'], ref['sha256']))
    for ref in corpus_refs:
        _bytes(head, ref)
    corpus = {'corpus_refs': corpus_refs, 'corpus_binding': store._hash(store._canonical({
        **store._VERSION, 'project_id': head['state']['project_id'],
        'objects': [{'id': ref['id'], 'sha256': ref['sha256']} for ref in corpus_refs]}))}
    # Registration events capture immutable successful output refs. Decisions
    # after that event cannot retroactively authorize the extraction.
    decisions = []
    found_registration = False
    for event in head['events']:
        result = event.get('payload', {}).get('result', {})
        if event['type'] == 'corpus_decided':
            decisions.append(result['approval'])
        if (event['type'] == 'node_outputs_registered' and result.get('attempt_id') == attempt['id']
                and extraction_ref in result.get('artifacts', [])):
            found_registration = True
            break
    if not found_registration:
        raise ValueError('m1_trace_registration_missing')
    approval = _current_approval({**head['state'], 'approvals': decisions}, corpus)
    if approval is None or approval['decision'] != 'approve':
        raise ValueError('m1_trace_approval_missing')
    shortlist_ref = _one_ref(corpus_refs, 'literature/shortlist.jsonl')
    sources = [_json(line) for line in _bytes(head, shortlist_ref).splitlines() if line.strip()]
    sources = [row for row in sources if row.get('source_id') == claim['source_id'] and row.get('decision') == 'include']
    if len(sources) != 1:
        raise ValueError('m1_trace_source_missing')
    current = deepcopy(head['trace_current_authorization'])
    current['traced_corpus_is_current'] = current.get('corpus_binding') == corpus['corpus_binding']
    current['approved'] = current['approved'] and current['traced_corpus_is_current']
    return deepcopy({**store._VERSION, 'head_id': head['id'], 'data_origin': 'registered',
        'content_origin': head['state']['content_origin'], 'claim': claim,
        'synthesis_ref': synthesis_ref, 'extraction_ref': extraction_ref,
        'extraction_attempt_id': attempt['id'], 'corpus': corpus, 'source': sources[0],
        'approval_at_extraction': approval, 'current_authorization': current,
        'original': {'locator': claim['locator'], 'url': claim['source_url'],
            'access_level': claim['evidence_level'], 'file_available': False,
            'full_text_verified': False, 'verification_status': 'not_performed'},
        'limitations': claim['limitations'], 'synthesis_limitations': synthesis['limitations'],
        'conflicts': [item for item in synthesis['conflicts'] if claim_id in item['claim_refs']],
        'synthesis_status': synthesis_status(synthesis)})
