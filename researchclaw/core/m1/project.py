"""New-project-only M1 lifecycle; no legacy migration or research approvals.

Initial state v1: schema_version, workflow_version, project_id, topic, profile,
max_returns, returns_used (0), current_node_id (scope), attempts ([]), and
content_origin (research or synthetic). Later engines extend state with records.
Identical init reopens current HEAD using genesis configuration for comparison.
"""
from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

from ..profiles import load_profile
from ..transactions import project_transaction
from .contracts import NODE_IDS
from . import store


def _check_new_root(root: Path) -> None:
    if root.exists() and not root.is_dir():
        raise ValueError('m1_path_invalid')
    if root.exists() and any(path.name != '.researchclaw' for path in root.iterdir()):
        raise ValueError('m1_project_root_not_empty')
    metadata = store._checked_path(root / '.researchclaw')
    if metadata.exists():
        for path in metadata.iterdir():
            if path.name == 'm1':
                # Another initializer may publish between the preflight checks.
                # Configuration is still compared under the shared lock.
                store._history(store._checked_path(path))
                continue
            if path.name != 'project-transaction.lock' and not path.name.startswith('.m1-init-'):
                raise ValueError('m1_project_root_not_empty')
            store._checked_path(path)


def _mkdir_durable(path: Path) -> None:
    if path.exists():
        # It may exist because an earlier create succeeded but its parent
        # fsync failed. Retry that publication before creating descendants.
        store._fsync_directory(path.parent)
        return
    _mkdir_durable(path.parent)
    path.mkdir(exist_ok=True)
    store._fsync_directory(path.parent)


def init_project(root: Path, *, topic: str, profile: str, max_returns: int,
                 content_origin: str = 'research') -> dict:
    """Create or safely reopen an M1 project with the same original config."""
    if (not isinstance(topic, str) or not topic.strip()
            or type(max_returns) is not int or max_returns < 0
            or content_origin not in ('research', 'synthetic')):
        raise ValueError('m1_project_config_invalid')
    try:
        load_profile(profile)
    except ValueError as exc:
        raise ValueError('m1_project_config_invalid') from exc
    config = {'topic': topic, 'profile': profile, 'max_returns': max_returns,
              'content_origin': content_origin}
    store._canonical(config)
    root = store._checked_path(root)
    base = store._store_path(root)
    if not base.exists():
        _check_new_root(root)
    else:
        store._history(base)
    _mkdir_durable(root)
    _mkdir_durable(base.parent)
    store._checked_path(base.parent / 'project-transaction.lock')
    with project_transaction(root):
        base = store._store_path(root)
        if base.exists():
            history = store._history(base)
            original = history[0][1]['state']
            if any(original.get(key) != value for key, value in config.items()):
                raise ValueError('m1_project_config_conflict')
            store._sync_publication(base)
            return store._receipt(*history[-1])
        _check_new_root(root)
        # Only a fully durable staged store becomes visible as m1/. Crashed
        # staging directories are neither receipts nor a reason to reset state.
        staging = base.parent / f'.m1-init-{uuid4().hex}'
        staging.mkdir()
        (staging / 'objects').mkdir()
        (staging / 'commits').mkdir()
        state = {**store._VERSION, 'project_id': f'm1-{uuid4().hex}', **config,
                 'returns_used': 0, 'current_node_id': NODE_IDS[0], 'attempts': []}
        event = {**store._VERSION, 'type': 'project_initialized', 'payload': config}
        result = store._publish(staging, parent=None, command_id='init', state=state,
                                event=event, objects={}, inputs={})
        store._history(staging)
        os.replace(staging, base)
        store._fsync_directory(base.parent)
        return result
