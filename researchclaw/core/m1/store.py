"""Immutable M1 commits with one atomic, crash-durable HEAD publication.

Public receipts contain schema_version, workflow_version, id, state, events,
objects. Events are cumulative closed envelopes {schema_version,
workflow_version, type, payload}; payload and state are extensible JSON objects.
Objects are cumulative SHA256 -> {sha256, size} references. commit_record accepts
logical-name -> bytes; names are relative POSIX paths, never filesystem inputs.
The command fingerprint binds state, event and named object refs, excluding the
optimistic expected_head precondition. Only HEAD ancestry supplies receipts.

record.json contains the complete state/events/object registry plus parent and
command metadata. Its canonical JSON SHA256 is the commit id. HEAD.json is a
closed versioned {id} envelope. Unpublished temporary/orphan commits are ignored.
This detects corruption, but is not authentication against a malicious owner.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import stat
from uuid import uuid4

from ..transactions import project_transaction
from .contracts import SCHEMA_VERSION, WORKFLOW_VERSION

_VERSION = {'schema_version': SCHEMA_VERSION, 'workflow_version': WORKFLOW_VERSION}
_DIGEST = re.compile(r'[0-9a-f]{64}')
_RECORD_KEYS = set(_VERSION) | {'parent', 'command_id', 'payload_sha256', 'state', 'events', 'objects', 'object_inputs'}


def _checked_path(path: Path) -> Path:
    """Check original components before resolve can hide a symlink or link/.. ."""
    absolute = Path(path).absolute()
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        try:
            info = current.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode):
            raise ValueError('m1_path_invalid')
    return absolute.resolve()


def _store_path(root: Path) -> Path:
    root = _checked_path(root)
    metadata = _checked_path(root / '.researchclaw')
    if os.path.lexists(metadata / 'state.json'):
        raise ValueError('m1_legacy_project_requires_explicit_migration')
    return _checked_path(metadata / 'm1')


def _json_value(value: object) -> None:
    if value is None or type(value) in (str, bool, int):
        return
    if type(value) is float and math.isfinite(value):
        return
    if type(value) is list:
        for item in value:
            _json_value(item)
        return
    if type(value) is dict and all(type(key) is str for key in value):
        for item in value.values():
            _json_value(item)
        return
    raise ValueError('m1_record_invalid')


def _canonical(value: object) -> bytes:
    try:
        _json_value(value)
        return json.dumps(value, ensure_ascii=False, sort_keys=True,
                          separators=(',', ':'), allow_nan=False).encode('utf-8')
    except (RecursionError, UnicodeError) as exc:
        raise ValueError('m1_record_invalid') from exc


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _is_digest(value: object) -> bool:
    return isinstance(value, str) and _DIGEST.fullmatch(value) is not None


def _closed(value: object, keys: set[str]) -> None:
    if (type(value) is not dict or set(value) != keys
            or type(value.get('schema_version')) is not int
            or any(value.get(key) != expected for key, expected in _VERSION.items())):
        raise ValueError('m1_record_invalid')


def _validate_event(event: dict) -> None:
    _closed(event, set(_VERSION) | {'type', 'payload'})
    if not isinstance(event['type'], str) or not event['type'].strip() or type(event['payload']) is not dict:
        raise ValueError('m1_record_invalid')
    _canonical(event)


def _logical_name(name: str) -> None:
    if (not isinstance(name, str) or not name or '\\' in name or '\x00' in name
            or PurePosixPath(name).is_absolute()
            or any(part in ('', '.', '..') for part in name.split('/'))):
        raise ValueError('m1_record_invalid')


def _fingerprint(state: dict, event: dict, inputs: dict) -> str:
    return _hash(_canonical({'state': state, 'event': event, 'objects': inputs}))


def _fsync_directory(path: Path) -> None:
    # Directory-open and fsync errors must not be hidden as durable success.
    path = _checked_path(path)
    fd = os.open(path, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0) | getattr(os, 'O_NOFOLLOW', 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _sync_publication(base: Path) -> None:
    # A prior attempt may have replaced HEAD (or published m1/) and then
    # failed its directory fsync. A mutation retry must retry durability too.
    _fsync_directory(base)
    _fsync_directory(base.parent)


def _write_file(path: Path, data: bytes) -> None:
    path = _checked_path(path)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def _read_file(path: Path) -> bytes:
    path = _checked_path(path)
    fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0))
    with os.fdopen(fd, 'rb') as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ValueError('m1_store_corrupt')
        return stream.read()


def _unique_pairs(pairs: list) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('m1_store_corrupt')
        result[key] = value
    return result


def _read_json(path: Path) -> dict:
    return json.loads(_read_file(path), object_pairs_hook=_unique_pairs)


def _atomic_head(base: Path, commit_id: str) -> None:
    target = _checked_path(base / 'HEAD.json')
    temporary = base / f'.head-{uuid4().hex}.tmp'
    _write_file(temporary, _canonical({**_VERSION, 'id': commit_id}))
    os.replace(temporary, target)
    _fsync_directory(base)


def _validate_refs(refs: dict) -> None:
    if type(refs) is not dict:
        raise ValueError('m1_record_invalid')
    for digest, ref in refs.items():
        if (not _is_digest(digest) or type(ref) is not dict
                or set(ref) != {'sha256', 'size'} or ref['sha256'] != digest
                or type(ref['size']) is not int or ref['size'] < 0):
            raise ValueError('m1_record_invalid')


def _read_record(base: Path, commit_id: str) -> dict:
    if not _is_digest(commit_id):
        raise ValueError('m1_store_corrupt')
    record = _read_json(base / 'commits' / commit_id / 'record.json')
    _closed(record, _RECORD_KEYS)
    if _hash(_canonical(record)) != commit_id:
        raise ValueError('m1_store_corrupt')
    if record['parent'] is not None and not _is_digest(record['parent']):
        raise ValueError('m1_store_corrupt')
    if (not isinstance(record['command_id'], str) or not record['command_id'].strip()
            or type(record['state']) is not dict or type(record['events']) is not list
            or not record['events'] or type(record['object_inputs']) is not dict):
        raise ValueError('m1_store_corrupt')
    for event in record['events']:
        _validate_event(event)
    _validate_refs(record['objects'])
    for name, digest in record['object_inputs'].items():
        _logical_name(name)
        if not _is_digest(digest) or digest not in record['objects']:
            raise ValueError('m1_store_corrupt')
    if record['payload_sha256'] != _fingerprint(record['state'], record['events'][-1], record['object_inputs']):
        raise ValueError('m1_store_corrupt')
    return record


def _history(base: Path) -> list[tuple[str, dict]]:
    try:
        for directory in (base, base / 'commits', base / 'objects'):
            if not _checked_path(directory).is_dir():
                raise ValueError('m1_store_corrupt')
        head = _read_json(base / 'HEAD.json')
        _closed(head, set(_VERSION) | {'id'})
        history, seen, commands = [], set(), set()
        commit_id = head['id']
        if not _is_digest(commit_id):
            raise ValueError('m1_store_corrupt')
        while commit_id is not None:
            if commit_id in seen:
                raise ValueError('m1_store_corrupt')
            seen.add(commit_id)
            record = _read_record(base, commit_id)
            if record['command_id'] in commands:
                raise ValueError('m1_store_corrupt')
            commands.add(record['command_id'])
            history.append((commit_id, record))
            commit_id = record['parent']
        history.reverse()
        events, refs = [], {}
        for _, record in history:
            if record['events'][:-1] != events:
                raise ValueError('m1_store_corrupt')
            expected = dict(refs)
            expected.update({digest: record['objects'][digest] for digest in record['object_inputs'].values()})
            if record['objects'] != expected:
                raise ValueError('m1_store_corrupt')
            # A previously registered hash may never acquire different metadata.
            if any(record['objects'].get(digest) != ref for digest, ref in refs.items()):
                raise ValueError('m1_store_corrupt')
            events, refs = record['events'], record['objects']
        for digest, ref in refs.items():
            data = _read_file(base / 'objects' / digest)
            if len(data) != ref['size'] or _hash(data) != digest:
                raise ValueError('m1_store_corrupt')
        return history
    except (ValueError, TypeError, KeyError, UnicodeError, RecursionError, FileNotFoundError, NotADirectoryError, IsADirectoryError) as exc:
        if isinstance(exc, ValueError) and str(exc) == 'm1_path_invalid':
            raise
        raise ValueError('m1_store_corrupt') from exc


def _receipt(commit_id: str, record: dict) -> dict:
    return {**_VERSION, 'id': commit_id, 'state': record['state'],
            'events': record['events'], 'objects': record['objects']}


def read_head(root: Path) -> dict:
    """Validate committed ancestry and object bytes, without locks or writes."""
    base = _store_path(root)
    if not base.exists():
        raise ValueError('m1_project_not_found')
    return _receipt(*_history(base)[-1])


def _publish(base: Path, *, parent: tuple[str, dict] | None, command_id: str,
             state: dict, event: dict, objects: dict[str, bytes], inputs: dict) -> dict:
    refs = {} if parent is None else dict(parent[1]['objects'])
    for name, data in objects.items():
        digest = inputs[name]
        path = _checked_path(base / 'objects' / digest)
        if path.exists():
            if _read_file(path) != data:
                raise ValueError('m1_store_corrupt')
        else:
            temporary = base / 'objects' / f'.object-{uuid4().hex}.tmp'
            _write_file(temporary, data)
            if _read_file(temporary) != data:
                raise ValueError('m1_store_corrupt')
            os.replace(temporary, path)
        refs[digest] = {'sha256': digest, 'size': len(data)}
    _fsync_directory(base / 'objects')
    record = {**_VERSION, 'parent': None if parent is None else parent[0],
              'command_id': command_id, 'payload_sha256': _fingerprint(state, event, inputs),
              'state': state, 'events': ([] if parent is None else parent[1]['events']) + [event],
              'objects': refs, 'object_inputs': inputs}
    encoded = _canonical(record)
    commit_id = _hash(encoded)
    destination = _checked_path(base / 'commits' / commit_id)
    if destination.exists():
        if _read_record(base, commit_id) != record:
            raise ValueError('m1_store_corrupt')
    else:
        temporary = base / 'commits' / f'.commit-{uuid4().hex}.tmp'
        temporary.mkdir()
        _write_file(temporary / 'record.json', encoded)
        _fsync_directory(temporary)
        os.replace(temporary, destination)
    _fsync_directory(base / 'commits')
    _atomic_head(base, commit_id)
    return _receipt(commit_id, record)


def commit_record(root: Path, *, expected_head: str, command_id: str, state: dict,
                  event: dict, objects: dict[str, bytes]) -> dict:
    """Publish one complete command or return its original committed receipt."""
    if (not _is_digest(expected_head) or not isinstance(command_id, str)
            or not command_id.strip() or type(state) is not dict or type(objects) is not dict):
        raise ValueError('m1_record_invalid')
    _validate_event(event)
    # Snapshot mutable caller input before taking the mutation lock.
    state = json.loads(_canonical(state))
    event = json.loads(_canonical(event))
    objects = dict(objects)
    inputs = {}
    for name, data in objects.items():
        _logical_name(name)
        if type(data) is not bytes:
            raise ValueError('m1_record_invalid')
        inputs[name] = _hash(data)
    fingerprint = _fingerprint(state, event, inputs)
    base = _store_path(root)
    _history(base)  # Reject missing/corrupt stores before creating a lock.
    _checked_path(base.parent / 'project-transaction.lock')
    with project_transaction(base.parent.parent):
        base = _store_path(root)
        history = _history(base)
        for commit_id, record in history:
            if record['command_id'] == command_id:
                if record['payload_sha256'] != fingerprint:
                    raise ValueError('m1_command_conflict')
                _sync_publication(base)
                return _receipt(commit_id, record)
        if history[-1][0] != expected_head:
            raise ValueError('m1_head_conflict')
        return _publish(base, parent=history[-1], command_id=command_id,
                        state=state, event=event, objects=objects, inputs=inputs)
