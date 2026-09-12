"""Closed structural contracts for research-graph-v1.

This module checks shape only: success proves neither reference existence nor
scientific validity, approval authority, independence, readiness, or a legal
transition. Those require a verified graph snapshot in subsequent policies.

All fields in the declarative contracts below are required unless wrapped in
``optional``. Nullable required fields explicitly represent absence. References
are exact four-field SnapshotRefs; standalone SnapshotRef records additionally
carry the common envelope. New global IDs/project IDs are canonical UUIDs;
head_id is an immutable SHA256 digest; artifact_id, producer_id, node and legacy
local_issue_id remain opaque strings. Legacy project identities belong in the
migration mapping, never silently relabelled as new project UUIDs. Attempts
are global UUID identities, not display ordinals. Issue ownership is required
but nullable to preserve explicitly unassigned imports; transfer ownership is
non-null. SnapshotRefs may name other mapped source projects.

Confidence is optional, uncalibrated 0..100 metadata on Position only. It has no
readiness semantics. Empty lists are allowed unless a structural discriminator
requires content. Open-world identifiers (node/category-specific targets etc.)
are strings; policy-dependent reference resolution belongs to later tasks.
"""
from math import isfinite
import re
from uuid import UUID

SCHEMA_VERSION = 1
WORKFLOW_VERSION = 'research-graph-v1'


def enum(*values):
    return ('enum', values)


def array(item):
    return ('array', item)


def nullable(item):
    return ('nullable', item)


def optional(item):
    return ('optional', item)


_MILESTONE = enum('M1', 'M2', 'M3')
_STATUS = enum('open', 'checking', 'resolved', 'deferred', 'transferred', 'reopened', 'superseded')
_REF = dict(project_id='uuid', head_id='sha256', artifact_id='text', sha256='sha256')
_REFS = array(_REF)
_IDS = array('uuid')
_TEXTS = array('text')
_COMMON = dict(schema_version=('literal', 1), workflow_version=('literal', WORKFLOW_VERSION),
    project_id='uuid', id='uuid', event_id='uuid', producer_id='text',
    content_origin=enum('real', 'synthetic', 'mixed'),
    provenance_status=enum('declared_only', 'host_observed'), observation_refs=_REFS)
_GATE = dict(ready='bool', reason_codes=_TEXTS, required_actions=_TEXTS, unresolved_issue_ids=_IDS)
_TRANSFER = dict(issue_id='uuid', to_milestone=_MILESTONE, owner_assignment_id='uuid',
                 verification_id='uuid', resolution_condition='text', acceptance_event_id=nullable('uuid'))

# Required/optional fields and every nested closed shape are frozen here.
_CONTRACTS = {
    'SnapshotRef': dict(head_id='sha256', artifact_id='text', sha256='sha256'),
    'Issue': dict(origin=dict(milestone=_MILESTONE, node='text', attempt='uuid', local_issue_id='text'),
        question='text', category=enum('source', 'logic', 'methodology', 'empirical', 'integrity', 'scope', 'reporting', 'other'),
        target_refs=_REFS, severity=enum('blocking', 'major', 'minor', 'optional'),
        blocking_scope=array(dict(kind=enum('node', 'handoff', 'finalization'), milestone=_MILESTONE, target_id='text')),
        resolution_condition='text', owner_assignment_id=nullable('uuid')),
    'IssueEvent': dict(issue_id='uuid', from_status=nullable(_STATUS), to_status=_STATUS,
        actor_assignment_id='uuid', rationale='text', verification_refs=_REFS, successor_ids=_IDS,
        to_milestone=optional(_MILESTONE), owner_assignment_id=optional('uuid'),
        verification_id=optional('uuid'), acceptance_event_id=optional('uuid')),
    'VerificationBudget': dict(owner_assignment_id='uuid', scope='text', resource_limits=_TEXTS, input_refs=_REFS),
    'Verification': dict(issue_ids=_IDS, method=enum('source_check', 'logic_check', 'calculation', 'experiment', 'human_decision'),
        question='text', input_refs=_REFS, acceptance_rule='text', owner_assignment_id='uuid', budget_ref=_REF),
    'VerificationResult': dict(verification_id='uuid', output_refs=_REFS,
        outcome=enum('supported', 'refuted', 'inconclusive', 'failed'), checked_scope=_TEXTS, limitations=_TEXTS),
    'Position': dict(assignment_id='uuid', session_id='uuid', input_binding=_REF, issue_id='uuid',
        stance=enum('support', 'oppose', 'conditional', 'abstain', 'uncertain'), rationale='text', evidence_refs=_REFS,
        changed_from=nullable(_REF), change_kind=nullable(enum('evidence_added', 'reinterpretation', 'logic_correction', 'scope_changed')),
        confidence=optional('confidence')),
    'Decision': dict(issue_ids=_IDS, position_refs=_REFS,
        claim_dispositions=array(dict(claim_ref=_REF, disposition=enum('supported', 'refuted', 'inconclusive', 'limited', 'withdrawn'), rationale='text')),
        rationale_links=array(dict(claim_ref=_REF, position_refs=_REFS, verification_refs=_REFS, acknowledgement_refs=_REFS)),
        dissent=array(dict(position_ref=_REF, issue_ids=_IDS, rationale='text')),
        next_action=dict(kind=enum('verify', 'revise', 'handoff', 'awaiting_input', 'blocked_budget', 'stop', 'finalize'),
                         milestone=_MILESTONE, node='text', attempt='uuid', rationale='text'), gate_result=_GATE),
    'Handoff': dict(from_milestone=_MILESTONE, to_milestone=_MILESTONE, source_head='sha256', artifact_refs=_REFS,
        unresolved_issue_ids=_IDS, transfer_proposals=array(_TRANSFER), limitations=_TEXTS, acceptance_ref=nullable(_REF)),
    'Dependency': dict(from_ref=_REF, to_ref=_REF, relation=enum('supports', 'derived_from', 'tests', 'reports'),
        origin_group_id='text'),  # Explicit literal "unknown" is a valid, non-independent origin.
    'ApprovalBinding': dict(existing_receipt_ref=_REF, scope_refs=_REFS, binding=_REF,
        validity=enum('valid', 'needs_revalidation', 'expired', 'revoked', 'unknown')),
}


def _check(spec, value, path, errors):
    def fail(code, message):
        errors.append(dict(code=code, path=path, message=message))

    if isinstance(spec, dict):
        if type(value) is not dict:
            fail('invalid_type', 'Expected an object.')
            return
        for key in value:
            if key not in spec:
                errors.append(dict(code='unknown_field', path=f'{path}.{key}', message='Field is not permitted.'))
        for key, child in spec.items():
            is_optional = isinstance(child, tuple) and child[0] == 'optional'
            if key not in value:
                if not is_optional:
                    errors.append(dict(code='required_field_missing', path=f'{path}.{key}', message='Required field is missing.'))
            else:
                _check(child[1] if is_optional else child, value[key], f'{path}.{key}', errors)
        return
    if isinstance(spec, tuple):
        tag, argument = spec
        if tag == 'nullable':
            if value is not None:
                _check(argument, value, path, errors)
        elif tag == 'array':
            if type(value) is not list:
                fail('invalid_type', 'Expected an array.')
            else:
                for index, item in enumerate(value):
                    _check(argument, item, f'{path}[{index}]', errors)
        elif tag == 'literal':
            if type(value) is not type(argument) or value != argument:
                fail('invalid_version', 'Unsupported version.')
        elif type(value) is not str or value not in argument:
            fail('invalid_enum', 'Value is not in the permitted enumeration.')
        return
    if spec == 'bool':
        valid = type(value) is bool
    elif spec == 'confidence':
        valid = type(value) in (int, float) and 0 <= value <= 100 and isfinite(value)
    else:
        valid = type(value) is str and bool(value.strip())
        if valid and spec == 'sha256':
            valid = re.fullmatch(r'[0-9a-f]{64}', value) is not None
        if valid and spec == 'uuid':
            try:
                valid = str(UUID(value)) == value
            except ValueError:
                valid = False
    if not valid:
        fail('invalid_type' if type(value) not in (str, int, float, bool) else 'invalid_value', f'Expected {spec}.')


def validate_record(kind: str, payload: dict) -> tuple[dict, ...]:
    """Return ordered ``{code,path,message}`` errors without mutating input.

    No I/O, graph lookup, status transition, or confidence-to-ready inference
    occurs. JSON-shaped malformed values, including nested containers, return
    errors rather than raising exceptions.
    """
    if type(kind) is not str or kind not in _CONTRACTS:
        return (dict(code='unknown_kind', path='$', message='Unknown record kind.'),)
    errors = []
    _check({**_COMMON, **_CONTRACTS[kind]}, payload, '$', errors)
    if type(payload) is dict:
        if payload.get('provenance_status') == 'host_observed' and not payload.get('observation_refs'):
            errors.append(dict(code='observation_refs_missing', path='$.observation_refs', message='Host observation requires evidence references.'))
        if kind == 'IssueEvent' and payload.get('to_status') == 'transferred':
            for field in ('to_milestone', 'owner_assignment_id', 'verification_id', 'acceptance_event_id'):
                if not payload.get(field):
                    errors.append(dict(code='transfer_acceptance_missing', path=f'$.{field}', message='Transfer requires destination, owner, verification and acceptance identifiers.'))
        if kind == 'IssueEvent' and payload.get('to_status') == 'superseded' and not payload.get('successor_ids'):
            errors.append(dict(code='successor_ids_missing', path='$.successor_ids', message='Supersession requires successor identifiers.'))
    return tuple(errors)
