"""Pure policies for public, executor-declared work episode reports.

Episode conclusions and local reviews describe workflow state only. They do not
grant execution authority or approve scientific claims.
"""
from copy import deepcopy

from . import store


_START_FIELDS = ("id", "stage", "title", "purpose", "depends_on", "return_to", "return_reason", "review_required")
_NOTE_FIELDS = ("id", "kind", "author", "text")
_CONCLUSION_FIELDS = ("id", "execution_status", "judgment", "remaining", "next_action", "next_reason")
_REVIEW_FIELDS = ("id", "decision", "reviewer", "feedback")
_ROW_FIELDS = (*_START_FIELDS, "sequence", "execution_status", "notes", "conclusion", "review_status", "review")


def _require(condition, reason):
    if not condition:
        raise ValueError(reason)


def _text(value):
    return type(value) is str and bool(value.strip())


def _closed(payload, fields):
    _require(type(payload) is dict and set(payload) == set(fields), "episode_payload_invalid")


def _episodes(snapshot):
    episodes = snapshot["state"].get("work_episodes", {})
    _require(type(episodes) is dict, "episode_state_invalid")
    return episodes


def _existing(snapshot, identity):
    episodes = _episodes(snapshot)
    _require(_text(identity) and type(episodes.get(identity)) is dict, "episode_missing")
    return episodes, episodes[identity]


def _plan(snapshot, record, event_type, payload):
    episodes = deepcopy(_episodes(snapshot))
    episodes[record["id"]] = record
    return dict(
        state_patch={"work_episodes": episodes},
        event={**store._VERSION, "type": event_type, "payload": deepcopy(payload)},
        object_inputs={},
    )


def start_episode(snapshot, payload):
    _closed(payload, _START_FIELDS)
    identity, stage, title, purpose = (payload[key] for key in _START_FIELDS[:4])
    depends_on, return_to, return_reason, review_required = (payload[key] for key in _START_FIELDS[4:])
    _require(all(_text(value) for value in (identity, stage, title, purpose)), "episode_payload_invalid")
    _require(type(depends_on) is list and all(_text(value) for value in depends_on)
             and len(depends_on) == len(set(depends_on)) and identity not in depends_on,
             "episode_payload_invalid")
    _require(type(review_required) is bool, "episode_payload_invalid")
    _require_return = ((return_to is None and return_reason is None)
                       or (_text(return_to) and _text(return_reason)))
    if not _require_return:
        raise ValueError("episode_payload_invalid")
    episodes = _episodes(snapshot)
    _require(identity not in episodes, "episode_exists")
    for dependency_id in depends_on:
        dependency = episodes.get(dependency_id)
        _require(type(dependency) is dict, "episode_dependency_missing")
        _require(dependency.get("execution_status") == "finished", "episode_dependency_unfinished")
        if dependency.get("review_required"):
            if dependency.get("review") is None:
                raise ValueError("episode_dependency_review_pending")
            _require(dependency["review"].get("decision") == "continue",
                     "episode_dependency_revision_requested")
    if return_to is not None:
        _require(return_to in episodes, "episode_return_context_missing")
    record = {key: deepcopy(payload[key]) for key in _START_FIELDS}
    record.update(sequence=len(episodes) + 1, execution_status="running", notes=[], conclusion=None,
                  review_status="pending" if review_required else "not_required", review=None)
    return _plan(snapshot, record, "work_episode_started", payload)


def note_episode(snapshot, payload):
    _closed(payload, _NOTE_FIELDS)
    _require(_text(payload["id"]) and payload["kind"] in ("dialogue", "tool", "output")
             and _text(payload["author"]) and _text(payload["text"]), "episode_payload_invalid")
    _, episode = _existing(snapshot, payload["id"])
    _require(episode["conclusion"] is None, "episode_finished_immutable")
    record = deepcopy(episode)
    record["notes"].append({key: payload[key] for key in ("kind", "author", "text")})
    return _plan(snapshot, record, "work_episode_note_recorded", payload)


def conclude_episode(snapshot, payload):
    _closed(payload, _CONCLUSION_FIELDS)
    _require(_text(payload["id"]) and payload["execution_status"] in ("finished", "failed")
             and all(_text(payload[key]) for key in _CONCLUSION_FIELDS[2:]), "episode_payload_invalid")
    _, episode = _existing(snapshot, payload["id"])
    _require(episode["conclusion"] is None, "episode_finished_immutable")
    record = deepcopy(episode)
    record["execution_status"] = payload["execution_status"]
    record["conclusion"] = {key: payload[key] for key in _CONCLUSION_FIELDS[1:]}
    return _plan(snapshot, record, "work_episode_concluded", payload)


def review_episode(snapshot, payload):
    _closed(payload, _REVIEW_FIELDS)
    _require(_text(payload["id"]) and payload["decision"] in ("continue", "revise")
             and _text(payload["reviewer"]) and _text(payload["feedback"]), "episode_payload_invalid")
    _, episode = _existing(snapshot, payload["id"])
    _require(episode["conclusion"] is not None, "episode_review_before_conclusion")
    _require(episode["review_required"] is True, "episode_review_not_required")
    _require(episode["review"] is None, "episode_review_exists")
    record = deepcopy(episode)
    record["review"] = {key: payload[key] for key in _REVIEW_FIELDS[1:]}
    record["review_status"] = "continued" if payload["decision"] == "continue" else "revision_requested"
    from .work_followups import plan_for_review
    plan = _plan(snapshot, record, "work_episode_reviewed", payload)
    reviewed_snapshot = {**snapshot, "state": {**snapshot["state"], **plan["state_patch"]}}
    plan["state_patch"]["work_followups"] = plan_for_review(reviewed_snapshot, record["id"])
    return plan


def public_episodes(snapshot):
    """Return the closed public projection in stable start order."""
    rows = []
    for identity, value in _episodes(snapshot).items():
        _require(type(value) is dict and set(value) == set(_ROW_FIELDS) and value["id"] == identity,
                 "episode_state_invalid")
        _require(all(_text(value[key]) for key in _START_FIELDS[:4])
                 and type(value["depends_on"]) is list
                 and all(_text(item) for item in value["depends_on"])
                 and ((value["return_to"] is None and value["return_reason"] is None)
                      or (_text(value["return_to"]) and _text(value["return_reason"])))
                 and type(value["review_required"]) is bool
                 and type(value["sequence"]) is int and value["sequence"] > 0
                 and value["execution_status"] in ("running", "finished", "failed")
                 and type(value["notes"]) is list
                 and all(type(note) is dict and set(note) == {"kind", "author", "text"}
                         and note["kind"] in ("dialogue", "tool", "output")
                         and _text(note["author"]) and _text(note["text"])
                         for note in value["notes"]), "episode_state_invalid")
        conclusion = value["conclusion"]
        _require((conclusion is None and value["execution_status"] == "running")
                 or (type(conclusion) is dict
                     and set(conclusion) == set(_CONCLUSION_FIELDS[1:])
                     and conclusion["execution_status"] == value["execution_status"]
                     and value["execution_status"] in ("finished", "failed")
                     and all(_text(conclusion[key]) for key in _CONCLUSION_FIELDS[2:])),
                 "episode_state_invalid")
        review = value["review"]
        review_decision = review.get("decision") if type(review) is dict else None
        expected_review_status = ("not_required" if not value["review_required"] else
                                  "pending" if review is None else
                                  "continued" if review_decision == "continue" else
                                  "revision_requested")
        _require((review is None or
                  (type(review) is dict and set(review) == set(_REVIEW_FIELDS[1:])
                   and review["decision"] in ("continue", "revise")
                   and _text(review["reviewer"]) and _text(review["feedback"])
                   and conclusion is not None and value["review_required"]))
                 and value["review_status"] == expected_review_status,
                 "episode_state_invalid")
        rows.append({key: deepcopy(value[key]) for key in _ROW_FIELDS})
    rows.sort(key=lambda row: row["sequence"])
    _require([row["sequence"] for row in rows] == list(range(1, len(rows) + 1)), "episode_state_invalid")
    by_id = {row["id"]: row for row in rows}
    for row in rows:
        _require(len(row["depends_on"]) == len(set(row["depends_on"]))
                 and row["id"] not in row["depends_on"]
                 and all(identity in by_id for identity in row["depends_on"])
                 and (row["return_to"] is None or row["return_to"] in by_id),
                 "episode_state_invalid")
    return rows
