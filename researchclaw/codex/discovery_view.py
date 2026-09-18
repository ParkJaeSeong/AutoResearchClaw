"""Read-only, allowlisted discovery projection separate from native evidence.

Only complete three-role rounds in the published reports file are disclosed.
Resume paths and aggregated sources are never followed or trusted. These reports
remain agent-declared exploration, not corpus approval or native verification.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urlsplit

from researchclaw.core.research_graph import store

_ROLES = ('domain', 'methodology', 'critical')
_SOURCE_TEXT = ('title', 'doi', 'url', 'query', 'access_status', 'reading_scope', 'finding', 'limitations')
_LIMITATIONS = [
    '후보 수는 같은 식별자를 묶어 센 보고 기록 수입니다. 논문 수나 검색 결과 수, 독립적으로 원문을 검증한 횟수와는 다릅니다.',
    '탐색 보고와 가설 초안만으로 근거 검증이나 문헌 사용 승인, M1 완료를 판단하지 않습니다.',
    '세 역할의 보고가 모두 모인 회차만 공개합니다. 자료에 접근한 범위, 읽은 범위와 해석은 에이전트가 보고한 내용입니다.',
]


def _read(root: Path, name: str, default=None):
    path = store._checked_path(root / name)
    try:
        value = json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=store._unique_pairs)
    except FileNotFoundError:
        if default is not None:
            return default
        raise
    store._json_value(value)
    return value


def _text(value):
    return value if isinstance(value, str) else ''


def _texts(value):
    return [item for item in value if isinstance(item, str)] if isinstance(value, list) else []


def _count(value, default=0):
    return value if type(value) is int and value >= 0 else default


def _source(value):
    if not isinstance(value, dict):
        raise ValueError('discovery_source_invalid')
    result = {key: _text(value.get(key)) for key in _SOURCE_TEXT}
    result['doi'] = result['doi'] or None
    # Keep only navigable web URLs; the browser also enforces this boundary.
    try:
        url = urlsplit(result['url'])
        if url.scheme not in ('http', 'https') or not url.netloc or url.username or url.password:
            result['url'] = ''
    except ValueError:
        result['url'] = ''
    if type(value.get('query_observed')) is bool:
        result['query_observed'] = value['query_observed']
    return result


def _key(source):
    doi = (source['doi'] or '').strip().lower()
    for prefix in ('https://doi.org/', 'http://doi.org/', 'doi:'):
        doi = doi.removeprefix(prefix)
    if doi:
        return 'doi:' + doi
    if source['url']:
        return 'url:' + source['url'].strip().rstrip('/')
    return 'title:' + source['title'].strip().lower()


def _selection(value, keys):
    if not isinstance(value, dict) or not value:
        return None
    if any(not isinstance(value.get(key, []), list) for key in ('groups', 'hypotheses', 'unresolved')):
        raise ValueError('discovery_selection_invalid')
    # Selection is always provisional, even when the external file claims approval.
    return {
        'status': 'draft', 'summary': _text(value.get('summary')),
        'groups': [{**{key: _text(group.get(key)) for key in ('id', 'title', 'reason')},
                    'source_keys': [key for key in _texts(group.get('source_keys')) if key in keys]}
                   for group in value.get('groups', []) if isinstance(group, dict)],
        'hypotheses': [{key: _text(item.get(key)) for key in ('id', 'statement', 'test', 'limits')}
                       for item in value.get('hypotheses', []) if isinstance(item, dict)],
        'unresolved': _texts(value.get('unresolved')),
        'reading_guide': _texts(value.get('reading_guide')),
    }


def build_discovery_view(project_root: Path, discovery_root: Path | None = None) -> dict:
    """Build a fresh discovery revision without changing native HEAD or run data."""
    result = dict(schema_version=1, available=discovery_root is not None, status='unconfigured',
                  round=0, max_rounds=0, completed_reports=0, unique_candidates=0,
                  candidate_records=0, m1_complete=False, roles=[], reports=[], sources=[],
                  limitations=list(_LIMITATIONS), selection=None)
    if discovery_root is None:
        return {**result, 'revision': store._hash(store._canonical(result))}
    root = store._checked_path(discovery_root)
    run = _read(root, 'run.json')
    head = store.read_head(project_root)
    if not isinstance(run, dict) or run.get('topic') != head['state']['topic']:
        raise ValueError('discovery_topic_mismatch')
    status = _read(root, 'status.json', {})
    reports = _read(root, 'reports.json', [])
    if not isinstance(status, dict) or not isinstance(reports, list):
        raise ValueError('discovery_record_invalid')
    result.update(status=_text(status.get('status')) or 'pending',
                  round=_count(status.get('round')), max_rounds=_count(run.get('max_rounds')))
    rounds = {}
    for report in reports:
        if not isinstance(report, dict):
            raise ValueError('discovery_report_invalid')
        number = report.get('round')
        if (type(number) is int and 1 <= number <= result['max_rounds']
                and report.get('role') in _ROLES and isinstance(report.get('summary'), str)
                and isinstance(report.get('sources'), list)):
            rounds.setdefault(number, []).append(report)
    # Infer progress from only known role folders and declared round bounds.
    # Never inspect report bodies, prompts, or error telemetry in worker folders.
    activities = {}
    for child in root.iterdir():
        match = re.fullmatch(r'round-([1-9][0-9]*)-(domain|methodology|critical)', child.name)
        if not match:
            continue
        number = int(match[1])
        if number > result['max_rounds']:
            continue
        activity = _read(root, f'round-{number}-{match[2]}/activity.json', {})
        if not isinstance(activity, dict):
            raise ValueError('discovery_activity_invalid')
        if activity:
            activities[number, match[2]] = activity
    if not 1 <= result['round'] <= result['max_rounds']:
        result['round'] = max([0, *rounds, *(number for number, _ in activities)])
    public = []
    for number, group in sorted(rounds.items()):
        if len(group) != 3 or sorted(_text(r.get('role')) for r in group) != sorted(_ROLES):
            continue
        if any(not isinstance(r.get('summary'), str) or not isinstance(r.get('sources'), list)
               for r in group):
            continue
        public.extend(group)
    sources = {}
    for report in public:
        projected = {key: _text(report.get(key)) for key in ('summary', 'reading_provenance')}
        projected.update(role=report['role'], round=report['round'],
                         sufficient=report.get('sufficient') is True,
                         sources=[_source(source) for source in report['sources']])
        projected.update({key: _texts(report.get(key)) for key in
                          ('queries', 'disagreements', 'gaps', 'next_queries')})
        result['reports'].append(projected)
        for source in projected['sources']:
            key = _key(source)
            entry = sources.setdefault(key, dict(key=key, title=source['title'], observations=[]))
            entry['observations'].append(dict(role=report['role'], round=report['round'], source=source))
    result.update(completed_reports=len(public), sources=list(sources.values()),
                  unique_candidates=len(sources), candidate_records=sum(len(r['sources']) for r in public))
    for role in _ROLES:
        own = [r for r in public if r['role'] == role]
        latest = max(own, key=lambda r: r['round']) if own else {}
        number = result['round']
        activity = activities.get((number, role), {})
        finished = any(r['role'] == role for r in rounds.get(number, []))
        failed = activity.get('status') in ('failed', 'timeout') or (
            activity.get('status') == 'exited' and type(activity.get('returncode')) is int
            and activity['returncode'] != 0)
        observed = latest.get('observed', {}) if latest.get('round') == number else {}
        result['roles'].append(dict(role=role, round=number,
            status='failed' if failed else 'running' if activity.get('status') == 'running'
                   else 'complete' if finished else 'pending',
            last_activity_at=_text(activity.get('checked_at')) or _text(latest.get('ended_at')) or None,
            web_calls=_count(observed.get('web_calls')) if isinstance(observed, dict) else 0))
    result['selection'] = _selection(_read(root, 'selection.json', {}), sources)
    return {**result, 'revision': store._hash(store._canonical(result))}
