"""Persisted, input-bound drafts and atomic output registration.

Submission v1 is closed: {schema_version: 1, files: {logical_path:
{path: 'm1/work/<attempt_id>/<logical_path>', sha256: hex, size: int}}}.
Paths are exact packet-owned outputs. Invalid manifests, unsafe paths and hash
mismatches fail before validation and consume no correction budget. Each distinct
safe submission is snapshotted once; syntax failures consume the initial attempt
plus at most two corrections. Identical submissions never consume another slot.
Command receipts bind the complete request, and replay uses committed objects,
never mutable drafts. No research approval or graph advancement happens here.
"""
from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
import json
import os
from pathlib import Path
import stat
from uuid import uuid4

from ..transactions import project_transaction
from . import store
from .artifacts import read_registered_inputs, validate_node_contents, validate_outputs
from .contracts import NODE_IDS
from .roles import describe_roles

PACKET_VERSION = 1
DRAFT_CORRECTIONS = 2
_DRAFT_STATUSES = {'prepared', 'draft_invalid'}


def _request(command_id: str, value: dict) -> dict:
    if not isinstance(command_id, str) or not command_id.strip():
        raise ValueError('m1_command_invalid')
    return json.loads(store._canonical(value))


@contextmanager
def _mutation(root: Path):
    root = store._checked_path(root)
    store.read_head(root)  # Fail before any lock creation for invalid stores.
    store._checked_path(root / '.researchclaw/project-transaction.lock')
    with project_transaction(root):
        yield root


def _replay(root: Path, command_id: str, request: dict) -> dict | None:
    """Re-publish durability using Task05's exact original payload contract."""
    base = store._store_path(root)
    for commit_id, record in store._history(base):
        if record['command_id'] != command_id:
            continue
        payload = record['events'][-1]['payload']
        if store._canonical(payload.get('request')) != store._canonical(request) or 'result' not in payload:
            raise ValueError('m1_command_conflict')
        objects = {name: store._read_file(base / 'objects' / digest)
                   for name, digest in record['object_inputs'].items()}
        receipt = store.commit_record(root, expected_head=commit_id,
                                      command_id=command_id, state=record['state'],
                                      event=record['events'][-1], objects=objects)
        return {'receipt': receipt, **deepcopy(payload['result'])}
    return None


def _commit(root: Path, head: dict, command_id: str, request: dict,
            result: dict, *, event_type: str, objects: dict[str, bytes]) -> dict:
    event = {**store._VERSION, 'type': event_type,
             'payload': {'request': request, 'result': deepcopy(result)}}
    receipt = store.commit_record(root, expected_head=head['id'], command_id=command_id,
                                  state=head['state'], event=event, objects=objects)
    return {'receipt': receipt, **result}


def _current_attempt(state: dict) -> dict | None:
    candidates = [attempt for attempt in state['attempts']
                  if attempt['node_id'] == state['current_node_id']]
    return candidates[-1] if candidates else None


def _inputs(state: dict, node_id: str, objects: dict) -> tuple[dict, list[str]]:
    """Bind consumed logical artifacts and scope configuration, not HEAD churn."""
    role = describe_roles(node_id)
    paths = [path for path in role['inputs'] if '/' in path]
    if node_id == 'extract':
        from .approvals import CORPUS_PATHS
        paths = list(CORPUS_PATHS)
    if node_id != 'scope':
        paths = sorted(set(paths) | {'scope/goal.md', 'scope/constraints.json'})
    latest = {ref['logical_path']: ref for ref in state.get('artifacts', [])}
    missing = [path for path in paths if path not in latest]
    refs = [deepcopy(latest[path]) for path in paths if path in latest]
    if node_id == 'hypothesize' and 'knowledge/synthesis.json' in latest:
        # A synthesis consumes an exact extraction version, not whichever
        # extraction happened to be registered most recently at authoring time.
        synthesis = latest['knowledge/synthesis.json']
        producers = [attempt for attempt in state['attempts']
                     if attempt['id'] == synthesis['producer_attempt_id']
                     and attempt['node_id'] == 'synthesize'
                     and synthesis in attempt.get('output_refs', [])]
        if len(producers) != 1:
            raise ValueError('m1_hypothesis_synthesis_producer_missing')
        extractions = [ref for ref in producers[0]['input_refs']
                       if ref['logical_path'] == 'knowledge/extractions.jsonl']
        if len(extractions) != 1 or extractions[0] not in state.get('artifacts', []):
            raise ValueError('m1_hypothesis_extraction_ref_missing')
        refs.append(deepcopy(extractions[0]))
        previous = latest.get('hypotheses/hypotheses.json')
        if previous is not None:
            refs.append(deepcopy(previous))
    for ref in refs:
        if (not isinstance(ref.get('id'), str) or not ref['id'].strip()
                or not store._is_digest(ref.get('sha256'))
                or type(ref.get('size')) is not int
                or objects.get(ref['sha256']) != {'sha256': ref['sha256'], 'size': ref['size']}):
            raise ValueError('m1_input_ref_invalid')
    if len({ref['id'] for ref in refs}) != len(refs):
        raise ValueError('m1_input_ref_invalid')
    refs.sort(key=lambda ref: (ref['id'], ref['sha256']))
    config = {key: state[key] for key in ('topic', 'profile', 'content_origin')}
    return {'objects': refs, 'configuration': config}, missing


def _binding(inputs: dict) -> str:
    refs = [{'id': ref['id'], 'sha256': ref['sha256']} for ref in inputs['objects']]
    return store._hash(store._canonical({'packet_version': PACKET_VERSION,
                                        'objects': refs, 'configuration': inputs['configuration']}))


def _packet(state: dict, attempt: dict) -> dict:
    packet = state.get('packets', {}).get(attempt['packet_id'])
    if packet is None:
        raise ValueError('m1_packet_unknown')
    return packet


@contextmanager
def _directory(path: Path, *, create: bool = False):
    """Open each directory relative to its checked parent descriptor."""
    path = Path(path).absolute()
    descriptor = os.open(path.anchor, os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:]:
            if part in ('.', '..'):
                raise ValueError('m1_submission_path_invalid')
            if create:
                try:
                    os.mkdir(part, mode=0o700, dir_fd=descriptor)
                except FileExistsError:
                    pass
            next_descriptor = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                                      dir_fd=descriptor)
            os.close(descriptor)
            descriptor = next_descriptor
        yield descriptor
    except OSError as exc:
        raise ValueError('m1_submission_path_invalid') from exc
    finally:
        os.close(descriptor)


def _work_directory(root: Path, packet: dict) -> None:
    with _directory(root / packet['work_dir'], create=True):
        pass


def prepare_node(root: Path, node_id: str, *, command_id: str) -> dict:
    """Prepare only the eligible current draft or record an active-draft alias."""
    request = _request(command_id, {'operation': 'prepare_node', 'node_id': node_id})
    with _mutation(root) as root:
        replay = _replay(root, command_id, request)
        if replay is not None:
            _work_directory(root, replay['packet'])
            return replay
        if node_id not in NODE_IDS:
            raise ValueError('m1_node_unknown')
        head = store.read_head(root)
        state = head['state']
        if node_id != state['current_node_id']:
            raise ValueError('m1_node_not_eligible')
        if node_id in ('review', 'handoff'):
            raise ValueError('m1_node_engine_unavailable')
        inputs, missing = _inputs(state, node_id, head['objects'])
        if missing:
            raise ValueError('m1_inputs_missing: ' + ', '.join(missing))
        if node_id == 'extract':
            from .approvals import require_corpus_approval
            require_corpus_approval(root, head)
        attempt = _current_attempt(state)
        if attempt is not None:
            if attempt['status'] not in _DRAFT_STATUSES:
                raise ValueError('m1_node_waiting: ' + attempt['status'])
            packet = _packet(state, attempt)
            if packet['packet_version'] != PACKET_VERSION or packet['input_binding'] != _binding(inputs):
                raise ValueError('m1_input_binding_changed')
        else:
            attempt_id = f'attempt-{uuid4().hex}'
            packet_id = f'packet-{uuid4().hex}'
            roles = describe_roles(node_id)
            packet = {**store._VERSION, 'id': packet_id, 'packet_version': PACKET_VERSION,
                      'attempt_id': attempt_id, 'node_id': node_id, 'inputs': inputs,
                      'input_binding': _binding(inputs), 'allowed_outputs': roles['outputs'],
                      'required_outputs': roles['outputs'], 'roles': roles['roles'],
                      'work_dir': f'm1/work/{attempt_id}',
                      'tool_scope': {'read': 'declared_inputs', 'write': f'm1/work/{attempt_id}',
                                     'execute_agents': False},
                      'requirements': {'structural_validation': True,
                                       'independent_check': node_id in ('collect', 'extract'),
                                       'council': node_id in ('scope', 'questions', 'search', 'screen', 'synthesize'),
                                       'scientific_validation': 'not_performed'},
                      'max_draft_corrections': DRAFT_CORRECTIONS,
                      'content_origin': state['content_origin']}
            attempt = {**store._VERSION, 'id': attempt_id, 'node_id': node_id, 'revision': 1,
                       'parent_attempt_id': None, 'packet_id': packet_id,
                       'input_refs': inputs['objects'], 'status': 'prepared', 'output_refs': [],
                       'validation_history': [], 'structural_validation': 'not_performed',
                       'scientific_validation': 'not_performed'}
            state['attempts'].append(attempt)
            state.setdefault('packets', {})[packet_id] = packet
        _work_directory(root, packet)
        return _commit(root, head, command_id, request,
                       {'packet': deepcopy(packet), 'attempt': deepcopy(attempt)},
                       event_type='node_prepared', objects={f"packets/{packet['id']}.json": store._canonical(packet)})


def _manifest(packet: dict, submission: dict) -> None:
    if (type(submission) is not dict or set(submission) != {'schema_version', 'files'}
            or type(submission['schema_version']) is not int or submission['schema_version'] != 1
            or type(submission['files']) is not dict):
        raise ValueError('m1_submission_invalid')
    for logical, ref in submission['files'].items():
        if (logical not in packet['allowed_outputs'] or type(ref) is not dict
                or set(ref) != {'path', 'sha256', 'size'}
                or ref['path'] != f"{packet['work_dir']}/{logical}"
                or not store._is_digest(ref['sha256'])
                or type(ref['size']) is not int or ref['size'] < 0):
            raise ValueError('m1_submission_invalid')


def _snapshot(root: Path, submission: dict) -> dict[str, bytes]:
    files = {}
    for logical, ref in submission['files'].items():
        target = root / ref['path']
        with _directory(target.parent) as parent_fd:
            descriptor = os.open(target.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                                 dir_fd=parent_fd)
            with os.fdopen(descriptor, 'rb') as stream:
                before = os.fstat(stream.fileno())
                if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
                    raise ValueError('m1_submission_path_invalid')
                if before.st_size != ref['size']:
                    raise ValueError('m1_submission_content_changed')
                data = stream.read(ref['size'] + 1)
                after = os.fstat(stream.fileno())
                if (len(data) != ref['size'] or store._hash(data) != ref['sha256']
                        or (before.st_size, before.st_mtime_ns, before.st_ctime_ns)
                        != (after.st_size, after.st_mtime_ns, after.st_ctime_ns)):
                    raise ValueError('m1_submission_content_changed')
                files[logical] = data
    return files


def register_outputs(root: Path, *, packet_id: str, submission: dict,
                     command_id: str) -> dict:
    """Register a structural result atomically; invalid drafts return issues."""
    request = _request(command_id, {'operation': 'register_outputs', 'packet_id': packet_id,
                                    'submission': submission})
    submission = request['submission']
    with _mutation(root) as root:
        replay = _replay(root, command_id, request)
        if replay is not None:
            return replay
        head = store.read_head(root)
        state = head['state']
        packet = state.get('packets', {}).get(packet_id)
        if packet is None:
            raise ValueError('m1_packet_unknown')
        _manifest(packet, submission)  # Closed, owned paths before any draft reads.
        attempt = _current_attempt(state)
        if (attempt is None or packet['node_id'] != state['current_node_id']
                or attempt['packet_id'] != packet_id):
            raise ValueError('m1_packet_stale')
        if packet['node_id'] == 'extract':
            from .approvals import require_corpus_approval
            require_corpus_approval(root, head)
        inputs, missing = _inputs(state, packet['node_id'], head['objects'])
        if missing or packet['packet_version'] != PACKET_VERSION or packet['input_binding'] != _binding(inputs):
            raise ValueError('m1_input_binding_changed')
        submission_hash = store._hash(store._canonical(submission))
        for prior in attempt['validation_history']:
            if prior['submission_sha256'] == submission_hash:
                result = {'packet_id': packet_id, 'attempt_id': attempt['id'],
                          'status': attempt['status'], 'issues': prior['issues'],
                          'artifacts': deepcopy(attempt['output_refs'])}
                return _commit(root, head, command_id, request, result,
                               event_type='node_submission_replayed', objects={})
        if attempt['status'] == 'awaiting_user':
            raise ValueError('m1_draft_budget_exhausted')
        if attempt['status'] not in _DRAFT_STATUSES:
            raise ValueError('m1_node_waiting: ' + attempt['status'])
        files = _snapshot(root, submission)
        input_files = read_registered_inputs(root, inputs['objects'])
        input_files['project.json'] = store._canonical({'project_id': state['project_id']})
        issues = list(validate_outputs(packet, files))
        if not issues:
            issues.extend(validate_node_contents(packet, files, input_files))
        refs = [{**store._VERSION, 'id': f'artifact-{uuid4().hex}', 'logical_path': logical,
                 'sha256': store._hash(data), 'size': len(data),
                 'producer_attempt_id': attempt['id'], 'content_origin': state['content_origin']}
                for logical, data in sorted(files.items())]
        validation = {**store._VERSION, 'submission_sha256': submission_hash,
                      'submission': submission, 'issues': issues, 'draft_refs': refs}
        attempt['validation_history'].append(validation)
        if issues:
            attempt['status'] = ('awaiting_user' if len(attempt['validation_history']) >= 1 + DRAFT_CORRECTIONS
                                 else 'draft_invalid')
            attempt['structural_validation'] = 'failed'
        else:
            attempt['status'] = 'review_pending'
            attempt['structural_validation'] = 'passed'
            attempt['output_refs'] = refs
            state.setdefault('artifacts', []).extend(refs)
        result = {'packet_id': packet_id, 'attempt_id': attempt['id'], 'status': attempt['status'],
                  'issues': issues, 'artifacts': deepcopy(attempt['output_refs'])}
        return _commit(root, head, command_id, request, result,
                       event_type='node_outputs_invalid' if issues else 'node_outputs_registered',
                       objects={f"drafts/{attempt['id']}/{submission_hash}/{name}": data
                                for name, data in files.items()})
