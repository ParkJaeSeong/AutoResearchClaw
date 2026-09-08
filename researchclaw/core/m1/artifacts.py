"""Structural allowlisting, immutable input snapshots, and node content adapters."""
from __future__ import annotations

import json
from pathlib import Path

import yaml

from . import store
from .contracts import NODE_IDS
from .roles import describe_roles


def validate_outputs(packet: dict, files: dict[str, bytes]) -> tuple[dict, ...]:
    """Reject undeclared paths before inspecting content, then check structure."""
    allowed = packet.get('allowed_outputs', [])
    unexpected = []
    for path in files:
        try:
            store._logical_name(path)
        except ValueError:
            unexpected.append(path)
            continue
        if path not in allowed:
            unexpected.append(path)
    if unexpected:
        return ({'code': 'm1_undeclared_output', 'paths': sorted(unexpected)},)
    return validate_declared_contents(packet, files)


def validate_declared_contents(packet: dict, files: dict[str, bytes]) -> tuple[dict, ...]:
    """Require node outputs and UTF-8/JSON/JSONL/safe YAML syntax, not science."""
    node_id = packet.get('node_id')
    if node_id not in NODE_IDS:
        return ({'code': 'm1_node_unknown'},)
    required = describe_roles(node_id)['outputs']
    issues = []
    missing = sorted(set(required) - set(files))
    if missing:
        issues.append({'code': 'm1_required_output_missing', 'paths': missing})
    for path, data in sorted(files.items()):
        try:
            text = data.decode('utf-8')
        except (AttributeError, UnicodeError):
            issues.append({'code': 'm1_output_utf8_invalid', 'path': path})
            continue
        try:
            if path.endswith('.json'):
                store._canonical(json.loads(text, object_pairs_hook=store._unique_pairs))
            elif path.endswith('.jsonl'):
                for line in text.splitlines():
                    if line.strip():
                        store._canonical(json.loads(line, object_pairs_hook=store._unique_pairs))
            elif path.endswith(('.yaml', '.yml')):
                yaml.safe_load(text)
        except (ValueError, TypeError, RecursionError, yaml.YAMLError):
            issues.append({'code': 'm1_output_format_invalid', 'path': path})
    return tuple(issues)


def validate_node_contents(packet: dict, files: dict[str, bytes], inputs: dict[str, bytes]) -> tuple[dict, ...]:
    """Node content checks on snapshots, separate from structural allowlisting."""
    from .literature import validate_literature
    if packet['node_id'] == 'hypothesize':
        from .hypotheses import validate_hypothesis_contents
        return validate_hypothesis_contents(files, inputs)
    if packet['node_id'] == 'synthesize':
        from .synthesis import validate_synthesis_contents
        return validate_synthesis_contents(files, inputs)
    return validate_literature(packet['node_id'], files, inputs)


def read_registered_inputs(root: Path, refs: list[dict]) -> dict[str, bytes]:
    """Read each immutable input once and verify those exact bytes before use."""
    files = {}
    base = store._store_path(root)
    for ref in refs:
        data = store._read_file(base / 'objects' / ref['sha256'])
        if len(data) != ref['size'] or store._hash(data) != ref['sha256']:
            raise ValueError('m1_input_content_changed')
        files[ref['logical_path']] = data
    return files
