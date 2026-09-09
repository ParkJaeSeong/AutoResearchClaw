"""Pure declared M1 evidence-origin grouping, not an independence certificate."""
from collections import deque
from copy import deepcopy

from .contracts import validate_record
from .dependencies import _References, _key, _node
from .issues import _Inputs, _require


def group_origins(snapshot: dict) -> dict:
    """Separate unique cited source versions, declared origin groups and unknowns.

    Input prerequisites and limits are frozen in evidence-origin-inputs.md.
    No approval policy, filesystem mutation or research execution is performed.
    """
    inputs = _Inputs(snapshot)
    _require('evidence_sources' in inputs.state, 'evidence_sources_missing')
    sources = inputs.state['evidence_sources']
    _require(type(sources) is dict, 'evidence_sources_invalid')
    refs = _References(inputs)
    selected = {}
    for identity in sorted(sources):
        record = inputs.registered('evidence_sources', identity)
        _require('source_ref' in record and not set(record) & {'head_id', 'artifact_id', 'sha256'},
                 'evidence_source_invalid')
        ref = record['source_ref']
        current = refs.resolve(ref)
        # SnapshotRef's closed contract already defines the full common envelope.
        envelope = {key: value for key, value in record.items() if key != 'source_ref'}
        envelope.update({key: ref[key] for key in ('head_id', 'artifact_id', 'sha256')})
        _require(not validate_record('SnapshotRef', envelope), 'evidence_source_invalid')
        _require(current, 'evidence_source_stale')
        for observation in record['observation_refs']:
            _require(refs.resolve(observation), 'evidence_source_stale')
        node = _node(ref)
        if node not in selected or _key(ref) < _key(selected[node]):
            selected[node] = ref

    parents, children = {}, {}
    for identity in sorted(inputs.state.get('dependencies', {})):
        dependency = inputs.registered('dependencies', identity, 'Dependency')
        for ref in [dependency['from_ref'], dependency['to_ref'], *dependency['observation_refs']]:
            refs.resolve(ref)
        source, target = _node(dependency['from_ref']), _node(dependency['to_ref'])
        parents.setdefault(source, set())
        parents.setdefault(target, set()).add((source, dependency['origin_group_id']))
        children.setdefault(source, set()).add(target)
        children.setdefault(target, set())

    # Validate the whole dependency DAG without invoking approval impact policy.
    indegree = {node: len({source for source, _ in edges}) for node, edges in parents.items()}
    queue = deque(node for node, degree in indegree.items() if degree == 0)
    visited = 0
    while queue:
        visited += 1
        for target in children[queue.popleft()]:
            indegree[target] -= 1
            if indegree[target] == 0:
                queue.append(target)
    _require(visited == len(parents), 'dependency_cycle')

    groups, unknown = {}, set()
    for cited in selected:
        if not parents.get(cited):
            unknown.add(cited)
        visited, pending = set(), [cited]
        while pending:
            node = pending.pop()
            if node in visited:
                continue
            visited.add(node)
            for source, origin in parents.get(node, ()):
                if origin == 'unknown':
                    unknown.add(cited)
                else:
                    groups.setdefault(origin, set()).add(cited)
                pending.append(source)

    def project(nodes):
        return sorted((selected[node] for node in nodes), key=_key)

    return deepcopy(dict(source_count=len(selected), origin_group_count=len(groups),
        origin_groups=[dict(origin_group_id=origin, source_refs=project(groups[origin])) for origin in sorted(groups)],
        unknown_refs=project(unknown), reason_codes=['origin_unknown'] if unknown else []))
