"""Content-only literature validation; no source access, approval, or advancement.

Search plan: queries/sources/inclusion_criteria/exclusion_criteria string lists.
Search log: search_id/query/source/searched_at/result_count. Candidates:
source_id/title, at least one doi/arxiv_id/url, access_status, search_ids.
Screening decisions: source_id/decision(include|exclude)/reason for every
candidate. Shortlist preserves every candidate's identity and access declaration
and matches its screening decision/reason. Extraction uses the legacy closed
claim/manifest schema through content-only adapters. project.json is a trusted
in-memory input supplied by registration, never a caller-authored output.
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
import json

import yaml

from ..knowledge_extraction import (ACCESS_STATUSES, validate_extraction_shortlist,
                                    validate_knowledge_extraction)
from . import store

SEARCH = 'literature/search_plan.yaml'
CANDIDATES = 'literature/candidates.jsonl'
LOG = 'literature/search_log.jsonl'
SHORTLIST = 'literature/shortlist.jsonl'
DECISIONS = 'literature/screening_decisions.jsonl'


def _text(files, path):
    return files[path].decode('utf-8')


def _json(text):
    value = json.loads(text, object_pairs_hook=store._unique_pairs)
    store._canonical(value)
    return value


def _rows(files, path):
    rows = [_json(line) for line in _text(files, path).splitlines() if line.strip()]
    if not rows or any(type(row) is not dict for row in rows):
        raise ValueError(f'{path} requires non-empty JSON objects')
    return rows


def _string(value):
    return isinstance(value, str) and bool(value.strip())


def _strings(value):
    return isinstance(value, list) and bool(value) and all(_string(item) for item in value)


def _indexed(rows, key):
    result = {}
    for row in rows:
        value = row.get(key)
        if not _string(value) or value in result:
            raise ValueError(f'missing or duplicate {key}')
        result[value] = row
    return result


def _plan(files):
    plan = yaml.safe_load(_text(files, SEARCH))
    store._canonical(plan)
    if type(plan) is not dict or any(not _strings(plan.get(key)) for key in (
            'queries', 'sources', 'inclusion_criteria', 'exclusion_criteria')):
        raise ValueError('search plan requires queries, sources, inclusion_criteria and exclusion_criteria')
    return plan


def _collect(files, inputs):
    plan = _plan(inputs)
    logs = _indexed(_rows(files, LOG), 'search_id')
    candidates = _indexed(_rows(files, CANDIDATES), 'source_id')
    for row in logs.values():
        if (row.get('query') not in plan['queries'] or row.get('source') not in plan['sources']
                or type(row.get('result_count')) is not int or row['result_count'] < 0
                or not _string(row.get('searched_at'))):
            raise ValueError('search log requires declared query/source, timestamp and nonnegative result_count')
        datetime.fromisoformat(row['searched_at'].replace('Z', '+00:00'))
    for row in candidates.values():
        if (not _string(row.get('title')) or not any(_string(row.get(key)) for key in ('doi', 'arxiv_id', 'url'))
                or row.get('access_status') not in ACCESS_STATUSES
                or not _strings(row.get('search_ids')) or not set(row['search_ids']) <= logs.keys()):
            raise ValueError('candidate requires title, source identifier, access_status and known search_ids')
    for search_id, row in logs.items():
        attributed = sum(search_id in source['search_ids'] for source in candidates.values())
        if attributed > row['result_count']:
            raise ValueError('candidate search provenance exceeds logged result_count')
    return candidates


def _screen(files, inputs):
    candidates = _indexed(_rows(inputs, CANDIDATES), 'source_id')
    shortlist = _indexed(_rows(files, SHORTLIST), 'source_id')
    decisions = _indexed(_rows(files, DECISIONS), 'source_id')
    if candidates.keys() != shortlist.keys() or candidates.keys() != decisions.keys():
        raise ValueError('shortlist and decisions must account for every candidate exactly once')
    for source_id, source in shortlist.items():
        decision = decisions[source_id]
        if (decision.get('decision') not in ('include', 'exclude') or not _string(decision.get('reason'))
                or any(source.get(key) != decision.get(key) for key in ('decision', 'reason'))):
            raise ValueError('shortlist requires matching explicit screening decision and reason')
        if any(source.get(key) != candidates[source_id].get(key) for key in (
                'title', 'doi', 'arxiv_id', 'url', 'source_type', 'access_status', 'search_ids')):
            raise ValueError('shortlist must preserve candidate identity, access and search provenance')
    return tuple(asdict(issue) for issue in validate_extraction_shortlist(_text(files, SHORTLIST)))


def validate_literature(node_id: str, files: dict[str, bytes], inputs: dict[str, bytes]) -> tuple[dict, ...]:
    """Return structural/content issues; never infer scientific correctness."""
    try:
        if node_id == 'search':
            _plan(files)
        elif node_id == 'collect':
            _collect(files, inputs)
        elif node_id == 'screen':
            return _screen(files, inputs)
        elif node_id == 'extract':
            project = _json(_text(inputs, 'project.json'))
            if type(project) is not dict or not _string(project.get('project_id')):
                raise ValueError('trusted project identity is required')
            # Strict parsing supplements the legacy adapter without changing it.
            for path in ('knowledge/extractions.jsonl',):
                for line in _text(files, path).splitlines():
                    if line.strip(): _json(line)
            manifest = _json(_text(files, 'knowledge/extraction_manifest.json'))
            issues = tuple(asdict(issue) for issue in validate_knowledge_extraction(
                _text(inputs, SHORTLIST), _text(files, 'knowledge/extractions.jsonl'),
                _text(files, 'knowledge/extraction_manifest.json'), project['project_id']))
            if issues:
                return issues
            sources = _indexed(_rows(inputs, SHORTLIST), 'source_id')
            access_rank = {'unavailable': 0, 'metadata_only': 1, 'abstract': 2, 'full_text': 3}
            for source in manifest['sources']:
                approved_access = sources[source['source_id']].get('access_status')
                if approved_access not in access_rank or access_rank[source['access_status']] > access_rank[approved_access]:
                    raise ValueError('extraction access exceeds approved corpus declaration; update corpus and obtain approval')
            for line in _text(files, 'knowledge/extractions.jsonl').splitlines():
                if not line.strip():
                    continue
                claim = _json(line)
                if claim['evidence_level'] != 'full_text' and not claim['limitations']:
                    raise ValueError('non-full-text claims require explicit access limitations')
    except (KeyError, ValueError, TypeError, UnicodeError, AttributeError, RecursionError, yaml.YAMLError) as exc:
        return ({'code': 'm1_literature_invalid', 'node_id': node_id, 'message': str(exc)},)
    return ()
