"""Pure exact-version downstream impact; see dependency-inputs.md.

Historical references remain historical. This produces an uncommitted event
descriptor, never rewrites objects, approval validity, or issue state.
"""
from collections import deque
from copy import deepcopy
import json

from . import store
from .contracts import validate_record
from .issues import _Inputs, _require


_FIELDS = {'project_id', 'head_id', 'artifact_id', 'sha256'}
_KINDS = {'issues': 'Issue', 'verifications': 'Verification',
          'verification_results': 'VerificationResult', 'positions': 'Position',
          'decisions': 'Decision', 'handoffs': 'Handoff',
          'dependencies': 'Dependency', 'approval_bindings': 'ApprovalBinding',
          'approval_receipts': None}


def _key(ref):
    return store._canonical(ref).decode()


def _node(ref):
    # A later ancestor containing the same immutable version is not a new node.
    return ref['project_id'], ref['artifact_id'], ref['sha256']


class _References:
    def __init__(self, inputs):
        self.inputs = inputs
        self.aliases = {}
        aliases = {}
        for head, record in inputs.history:
            _require(all(type(record['state'].get(name, {})) is dict for name in _KINDS),
                     'dependency_collection_invalid')
            aliases.update(record['object_inputs'])
            self.aliases[head] = dict(aliases)
        self.current_aliases = aliases

    def resolve(self, ref):
        inputs = self.inputs
        _require(type(ref) is dict and set(ref) == _FIELDS
                 and all(type(value) is str for value in ref.values())
                 and ref['project_id'] == inputs.project
                 and bool(ref['artifact_id'].strip()) and store._is_digest(ref['sha256'])
                 and ref['head_id'] in inputs.heads, 'dependency_reference_invalid')
        ancestor = inputs.heads[ref['head_id']]
        data = inputs.objects.get(ref['sha256'])
        _require(data is not None and store._hash(data) == ref['sha256']
                 and ref['sha256'] in ancestor['objects'], 'dependency_reference_invalid')
        # Typed UUIDs need not be raw object aliases (producers namespace them).
        matches = [(collection, ancestor['state'].get(collection, {})[ref['artifact_id']])
                   for collection in _KINDS if ref['artifact_id'] in ancestor['state'].get(collection, {})]
        if matches:
            _require(len(matches) == 1, 'dependency_reference_ambiguous')
            collection, record = matches[0]
            _require(type(record) is dict and record.get('id') == ref['artifact_id']
                     and record.get('project_id') == inputs.project and store._canonical(record) == data,
                     'dependency_reference_invalid')
            _require(_KINDS[collection] is None or not validate_record(_KINDS[collection], record),
                     'dependency_record_invalid')
            current_matches = [name for name in _KINDS
                               if ref['artifact_id'] in inputs.state.get(name, {})]
            _require(len(current_matches) <= 1, 'dependency_reference_ambiguous')
            return inputs.state.get(collection, {}).get(ref['artifact_id']) == record
        _require(self.aliases[ref['head_id']].get(ref['artifact_id']) == ref['sha256'],
                 'dependency_reference_invalid')
        return self.current_aliases.get(ref['artifact_id']) == ref['sha256']

    def registered_ref(self, collection, identity, kind):
        record = self.inputs.registered(collection, identity, kind)
        head = next(head for head, old in self.inputs.history
                    if old['state'].get(collection, {}).get(identity) == record)
        ref = dict(project_id=self.inputs.project, head_id=head, artifact_id=identity,
                   sha256=store._hash(store._canonical(record)))
        self.resolve(ref)
        return record, ref


def _receipt(inputs, refs, approval):
    """A07 receipt adapter semantics, allowing historical impacted scopes.

    gates._approval deliberately rejects historical scope and nonvalid status;
    impact planning must still inspect both without reviving either.
    """
    ref = approval['existing_receipt_ref']
    refs.resolve(ref)
    receipt = inputs.reference(ref, 'approval_receipts')
    _require(set(receipt) == {'id', 'project_id', 'producer_id', 'decision', 'binding', 'scope_refs'}
             and receipt['decision'] == 'approved' and type(receipt['producer_id']) is str
             and bool(receipt['producer_id'].strip()) and receipt['binding'] == approval['binding']
             and receipt['scope_refs'] == approval['scope_refs']
             and approval['binding'] in approval['scope_refs'], 'dependency_approval_invalid')
    receipt_index = next(i for i, (head, _) in enumerate(inputs.history) if head == ref['head_id'])
    approval_index = next(i for i, (_, old) in enumerate(inputs.history)
                          if approval['id'] in old['state'].get('approval_bindings', {}))
    _require(receipt_index < approval_index, 'dependency_approval_invalid')


def plan_revalidation(snapshot: dict, *, changed_refs: list[str]) -> dict:
    """Return affected/reusable exact refs, approval checks and an event plan.

    changed_refs holds canonical JSON strings of four-field SnapshotRefs. All
    four relation labels use from_ref (input) → to_ref (dependent result).
    """
    inputs = _Inputs(snapshot)
    refs = _References(inputs)
    _require(type(changed_refs) is list and all(type(value) is str for value in changed_refs),
             'dependency_changed_refs_invalid')
    changed = []
    for value in changed_refs:
        try:
            ref = json.loads(value)
        except ValueError as error:
            raise ValueError('dependency_changed_refs_invalid') from error
        _require(type(ref) is dict and set(ref) == _FIELDS and _key(ref) == value,
                 'dependency_changed_refs_invalid')
        changed.append(ref)

    representatives, current, graph = {}, {}, {}

    def include(ref, graph_node=False):
        is_current = refs.resolve(ref)
        node = _node(ref)
        if node not in representatives or _key(ref) < _key(representatives[node]):
            representatives[node] = ref
        current[node] = is_current
        if graph_node:
            graph.setdefault(node, set())
        return node

    seeds = {include(ref, True) for ref in changed}
    for identity in sorted(inputs.state.get('dependencies', {})):
        dependency = inputs.registered('dependencies', identity, 'Dependency')
        source = include(dependency['from_ref'], True)
        target = include(dependency['to_ref'], True)
        graph[source].add(target)
        for ref in dependency['observation_refs']:
            refs.resolve(ref)

    # Check every component, including disconnected cycles, without recursion.
    indegree = dict.fromkeys(graph, 0)
    for targets in graph.values():
        for target in targets:
            indegree[target] += 1
    queue = deque(node for node, degree in indegree.items() if degree == 0)
    visited = 0
    while queue:
        visited += 1
        for target in graph[queue.popleft()]:
            indegree[target] -= 1
            if indegree[target] == 0:
                queue.append(target)
    _require(visited == len(graph), 'dependency_cycle')
    affected = set(seeds)
    queue = deque(seeds)
    while queue:
        for target in graph[queue.popleft()]:
            if target not in affected:
                affected.add(target)
                queue.append(target)

    checks, reusable_approvals, impacted_approvals, approval_nodes = [], [], [], set()
    for identity in sorted(inputs.state.get('approval_bindings', {})):
        approval, approval_ref = refs.registered_ref('approval_bindings', identity, 'ApprovalBinding')
        approval_nodes.add(_node(approval_ref))
        scope = {include(ref) for ref in [approval['binding'], *approval['scope_refs']]}
        observations_current = all([refs.resolve(ref) for ref in approval['observation_refs']])
        _receipt(inputs, refs, approval)
        reasons = []
        if scope & affected or _node(approval_ref) in affected:
            reasons.append('needs_revalidation')
            impacted_approvals.append(approval_ref)
        if approval['validity'] != 'valid' or not all(current[node] for node in scope) or not observations_current:
            reasons.append('approval_not_current')
        checks.append(dict(approval_ref=approval_ref, reason_codes=reasons, reusable=not reasons))
        if not reasons:
            reusable_approvals.append(approval_ref)

    def project(nodes):
        return sorted((representatives[node] for node in nodes), key=_key)

    affected_refs = project(affected)
    event = None
    if affected:
        event = {**store._VERSION, 'type': 'needs_revalidation', 'payload': {
            'changed_refs': project(seeds), 'affected_refs': affected_refs,
            'approval_refs': sorted(impacted_approvals, key=_key)}}
    return deepcopy(dict(affected_refs=affected_refs, approval_checks=checks,
        reusable_refs=sorted([*project(node for node in graph if node not in affected | approval_nodes and current[node]),
                              *reusable_approvals], key=_key), event_plan=event))
