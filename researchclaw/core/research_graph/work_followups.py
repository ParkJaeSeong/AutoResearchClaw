"""Stored plans derived from episode reviews, without execution authority.

Bindings use canonical hashes of the immutable conclusion and review in the
selected snapshot. Plans never allocate episode sequences or start work.
"""
from copy import deepcopy

from . import store
from .work_episodes import public_episodes


def _require(condition):
    if not condition:
        raise ValueError('followup_state_invalid')


def _derive(project_id, episode):
    conclusion, review = episode['conclusion'], episode['review']
    _require(conclusion is not None and review is not None)
    binding = dict(project_id=project_id, source_episode_id=episode['id'],
                   source_conclusion_sha256=store._hash(store._canonical(conclusion)),
                   source_review_sha256=store._hash(store._canonical(review)))
    revision = review['decision'] == 'revise'
    return dict(
        id='followup-' + store._hash(store._canonical(binding)),
        **{key: value for key, value in binding.items() if key != 'project_id'},
        kind='revision' if revision else 'followup',
        title='재검토: ' + episode['title'] if revision else conclusion['next_action'],
        purpose=review['feedback'] if revision else conclusion['next_reason'],
        depends_on=[] if revision else [episode['id']],
        return_to=episode['id'] if revision else None,
        return_reason=review['feedback'] if revision else None,
        status='planned' if revision or conclusion['execution_status'] == 'finished' else 'blocked',
    )


def public_followups(snapshot):
    """Project only stored plans, rejecting source or derivation mismatches."""
    episodes = {row['id']: row for row in public_episodes(snapshot)}
    records = snapshot['state'].get('work_followups', {})
    _require(type(records) is dict)
    rows = []
    for identity, record in records.items():
        _require(type(record) is dict and type(record.get('source_episode_id')) is str)
        source = episodes.get(record['source_episode_id'])
        _require(source is not None)
        expected = _derive(snapshot['state']['project_id'], source)
        _require(identity == expected['id'] and record == expected)
        rows.append(deepcopy(expected))
    rows.sort(key=lambda row: episodes[row['source_episode_id']]['sequence'])
    return rows


def plan_for_review(snapshot, episode_id):
    """Extend the validated collection for a snapshot with its new review."""
    records = {row['id']: row for row in public_followups(snapshot)}
    episodes = {row['id']: row for row in public_episodes(snapshot)}
    _require(episode_id in episodes)
    record = _derive(snapshot['state']['project_id'], episodes[episode_id])
    _require(record['id'] not in records)
    records[record['id']] = record
    return records
