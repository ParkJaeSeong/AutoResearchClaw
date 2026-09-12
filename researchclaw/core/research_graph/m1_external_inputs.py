"""Explicit Atlas inputs for shared M1 reasoning; never handoff authority."""
from . import store
from .councils import _record_ref
from .dependencies import _node
from .external_evidence import _resolve_record
from .issues import _Inputs, _require

_PARENTS = {'synthesize': ('questions', 'evidence_basis'),
            'hypothesize': ('questions', 'evidence_basis', 'synthesize'),
            'review': ('questions', 'evidence_basis', 'synthesize', 'hypothesize')}


def external_parents(node):
    return _PARENTS.get(node, ())


def uses_external(artifact):
    return 'evidence_basis' in artifact.get('input_refs', {})


def external_evidence(snapshot, artifact):
    from .m1_evidence_basis import COLLECTION, basis_records, basis_status, _claim_objects
    from .m1_nodes import current_node
    inputs = _Inputs(snapshot)
    refs = artifact['input_refs']
    _require(artifact['node'] in _PARENTS and set(refs) == set(_PARENTS[artifact['node']]),
             'm1_external_inputs_invalid')
    records = basis_records(snapshot)
    basis = _resolve_record(inputs, refs['evidence_basis'], COLLECTION, 'm1_external_basis_invalid', current=True)
    _require(basis in records, 'm1_external_basis_invalid')
    canonical_ref = _record_ref(inputs, COLLECTION, basis)
    _require(not any(r['previous_ref'] == canonical_ref for r in records), 'evidence_basis_superseded')
    status = basis_status(snapshot, basis)
    _require(status['current'], status['reason_codes'][0] if status['reason_codes'] else 'm1_external_basis_invalid')
    _, question = current_node(inputs, 'questions')
    _require(_node(refs['questions']) == _node(question) == _node(basis['question_ref']),
             'm1_external_question_invalid')
    inputs.reference(refs['questions'])
    for parent in ('synthesize', 'hypothesize'):
        if parent not in refs:
            continue
        old, ref = current_node(inputs, parent)
        _require(_node(refs[parent]) == _node(ref) and uses_external(old)
                 and _node(old['input_refs']['evidence_basis']) == _node(canonical_ref)
                 and _node(old['input_refs']['questions']) == _node(question), 'm1_external_parent_mismatch')
        inputs.reference(refs[parent])
    claims = {}
    for index, (alias, data) in enumerate(_claim_objects(basis).items()):
        ref = {**canonical_ref, 'artifact_id': alias, 'sha256': store._hash(data)}
        inputs.reference(ref)
        claims[basis['claims'][index]['claim_id']] = ref
    limitations = [*basis['limitations'], basis['coverage']['missing'], basis['coverage']['decision_impact']]
    for claim in basis['claims']:
        limitations.extend(claim['limitations'])
        review = _resolve_record(inputs, claim['review_ref'], 'external_reviews', 'm1_external_review_invalid')
        limitations.extend(review['limitations'])
        limitations.extend(review['held_uses'])
    return dict(ready=True, reason_codes=[], route='external', basis_ref=canonical_ref,
        corpus_ref=None, source_groups=None, extraction_refs=claims,
        limitations=list(dict.fromkeys(limitations)))


def validate_parent_routes(inputs, artifact):
    """Do not silently combine native extraction with an external reasoning parent."""
    from .m1_nodes import current_node
    for parent in ('synthesize', 'hypothesize'):
        if parent in artifact['input_refs']:
            record, _ = current_node(inputs, parent)
            _require(uses_external(record) == uses_external(artifact), 'm1_review_route_mismatch')
