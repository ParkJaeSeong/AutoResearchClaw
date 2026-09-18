"""Explicit local project catalog. Research roots remain authoritative."""
from __future__ import annotations
import fcntl
import json
import os
from contextlib import contextmanager
from pathlib import Path
from uuid import UUID, uuid5, NAMESPACE_URL
from urllib.parse import quote
from researchclaw.core.research_graph import commands, store

PUBLIC_FOLDERS = {'documents', 'materials', 'outputs'}

class Workspace:
    def __init__(self, path):
        self.path = store._checked_path(Path(path))
        self.path.mkdir(parents=True, exist_ok=True)
        self._identities = {}

    @contextmanager
    def locked(self):
        with store._checked_path(self.path / 'catalog.lock').open('a+b') as stream:
            fcntl.flock(stream, fcntl.LOCK_EX)
            yield

    def read(self):
        path = store._checked_path(self.path / 'catalog.json')
        if not path.exists():
            return {'projects': [], 'requests': {}}
        data = json.loads(path.read_text(), object_pairs_hook=store._unique_pairs)
        if type(data) is not dict or set(data) != {'projects', 'requests'}:
            raise ValueError('workspace_catalog_invalid')
        return data

    def write(self, data):
        target = store._checked_path(self.path / 'catalog.json')
        temporary = store._checked_path(self.path / 'catalog.json.tmp')
        with temporary.open('w') as stream:
            json.dump(data, stream, ensure_ascii=False, allow_nan=False)
            stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, target)
        fd = os.open(self.path, os.O_RDONLY)
        try: os.fsync(fd)
        finally: os.close(fd)

    def register(self, root, *, name, layout='linked'):
        root = store._checked_path(Path(root))
        head = store.read_head(root)
        entry = dict(id=head['state']['project_id'], name=name, topic=head['state']['topic'],
                     storage_path=str(root), layout=layout)
        with self.locked():
            data = self.read()
            existing = next((p for p in data['projects'] if p['id'] == entry['id']), None)
            if existing:
                if any(existing.get(k) != v for k, v in entry.items()): raise ValueError('workspace_project_conflict')
                return existing
            data['projects'].append(entry); self.write(data)
        return entry

    def set_archived(self, project_id, archived):
        """Organizational label only: retain the root, history and explicit access."""
        if type(archived) is not bool:
            raise ValueError('workspace_payload_invalid')
        with self.locked():
            data = self.read()
            entry = next((p for p in data['projects'] if p['id'] == project_id), None)
            if entry is None:
                raise ValueError('workspace_project_unknown')
            entry['archived'] = archived
            self.write(data)
            return dict(entry)

    def resolve(self, project_id):
        try:
            if str(UUID(project_id)) != project_id: raise ValueError()
        except (ValueError, TypeError, AttributeError):
            raise ValueError('workspace_project_unknown') from None
        entry = next((p for p in self.read()['projects'] if p['id'] == project_id), None)
        if entry is None: raise ValueError('workspace_project_unknown')
        root = store._checked_path(Path(entry['storage_path']))
        marker = store._checked_path(store._store_path(root) / 'HEAD.json')
        # Read the small head marker every time; verify full history only when it changes.
        stat = marker.stat()
        key = (str(root), stat.st_dev, stat.st_ino, stat.st_mtime_ns, stat.st_size, marker.read_bytes())
        identity = self._identities.get(key)
        if identity is None:
            identity = store.read_head(root)['state']['project_id']
            self._identities = {k: v for k, v in self._identities.items() if k[0] != str(root)}
            self._identities[key] = identity
        if identity != project_id:
            raise ValueError('workspace_project_mismatch')
        return root

    def create(self, payload):
        if (type(payload) is not dict or set(payload) != {'name', 'topic', 'request_id'}
                or any(type(payload[k]) is not str or not payload[k].strip() for k in payload)
                or len(payload['name']) > 200 or len(payload['topic']) > 10000
                or len(payload['request_id']) > 200):
            raise ValueError('workspace_payload_invalid')
        with self.locked():
            data = self.read(); request_id = payload['request_id']
            previous = data['requests'].get(request_id)
            if previous:
                if previous['payload'] != payload: raise ValueError('workspace_request_conflict')
                if previous['project_id'] is not None:
                    return next(p for p in data['projects'] if p['id'] == previous['project_id'])
            else:
                # Durable request binding survives a crash before the project is published.
                data['requests'][request_id] = {'payload': payload, 'project_id': None}
                self.write(data)
            folder = str(uuid5(NAMESPACE_URL, str(self.path) + ':' + request_id))
            root = store._checked_path(self.path / 'projects' / folder)
            head = commands.init_project(root, topic=payload['topic'], content_origin='real')
            head = commands.apply_command(root, operation='work.return_policy.set',
                payload=dict(mode='evidence_driven', rationale='Revisit decisions when evidence changes; record the gap and next action.',
                             authorization_basis='Pilot project creation defaults defined by AGENTS.md; no scientific or execution approval.'),
                expected_head=head['id'], command_id='workspace-return-policy')
            entry = dict(id=head['state']['project_id'], name=payload['name'], topic=payload['topic'], storage_path=str(root), layout='managed')
            for folder in ('documents', 'materials', 'outputs/M1', 'outputs/M2', 'outputs/M3', 'runs'):
                store._checked_path(root / folder).mkdir(parents=True, exist_ok=True)
            store._checked_path(root / 'project.json').write_text(json.dumps(entry, ensure_ascii=False, indent=2) + '\n')
            data['projects'].append(entry)
            data['requests'][request_id] = {'payload': payload, 'project_id': entry['id']}
            self.write(data)
            return entry


def public_file(root, relative):
    parts = relative.split('/')
    if (not parts or parts[0] not in PUBLIC_FOLDERS or any(p in ('', '.', '..') or p.startswith('.') for p in parts)
            or '\\' in relative or '\x00' in relative):
        raise ValueError('workspace_file_unavailable')
    path = store._checked_path(root / relative)
    if not path.is_file(): raise ValueError('workspace_file_unavailable')
    return path


def public_files(root, project_id):
    files = []
    for folder in sorted(PUBLIC_FOLDERS):
        base = root / folder
        if base.is_symlink() or not base.is_dir(): continue
        for path in sorted(base.rglob('*')):
            relative = path.relative_to(root).as_posix()
            try: checked = public_file(root, relative)
            except (ValueError, OSError): continue
            files.append(dict(path=relative, size=checked.stat().st_size,
                              url='/api/project-files/' + quote(relative, safe='/') + '?project=' + quote(project_id)))
    return dict(files=files, storage_path=str(root))
