"""Synthetic A06 fixtures; validators do no registration or research work."""
from copy import deepcopy
from uuid import uuid4

from researchclaw.core.research_graph import commands, store
from researchclaw.core.research_graph.positions import (
    validate_position_change,
    validate_rationale_links,
)


def uid():
    return str(uuid4())


def envelope(project, producer="reviewer"):
    return {
        **store._VERSION,
        "project_id": project,
        "id": uid(),
        "event_id": uid(),
        "producer_id": producer,
        "content_origin": "synthetic",
        "provenance_status": "declared_only",
        "observation_refs": [],
    }


class Fixture:
    def __init__(self, root):
        self.root = root
        self.head = commands.init_project(
            root, topic="A06 synthetic", content_origin="synthetic"
        )
        self.project = self.head["state"]["project_id"]
        self.assignment = {
            "id": uid(),
            "project_id": self.project,
            "actor_id": "reviewer",
            "role": "resolver",
            "milestone": "M1",
            "active": True,
        }
        self.register("assignments", self.assignment)
        self.input_ref = self.register(
            "fixture_inputs", {**envelope(self.project), "text": "frozen review packet"}
        )[0]
        self.session = {
            "id": uid(),
            "project_id": self.project,
            "input_binding": self.input_ref,
            "participant_assignment_ids": [self.assignment["id"]],
            "frozen": True,
        }
        self.register("review_sessions", self.session)
        self.evidence_ref = self.register(
            "fixture_evidence", {**envelope(self.project), "text": "source passage A"}
        )[0]
        self.issue_id = uid()
        self.issue = {
            **envelope(self.project),
            "id": self.issue_id,
            "origin": {
                "milestone": "M1",
                "node": "review",
                "attempt": uid(),
                "local_issue_id": "q1",
            },
            "question": "Does source A cover the target population?",
            "category": "source",
            "target_refs": [self.evidence_ref],
            "severity": "blocking",
            "blocking_scope": [
                {"kind": "finalization", "milestone": "M1", "target_id": "report"}
            ],
            "resolution_condition": "Source A covers the target population",
            "owner_assignment_id": self.assignment["id"],
        }
        self.register("issues", self.issue)

    def register(self, collection, *records):
        state = deepcopy(self.head["state"])
        state.setdefault(collection, {}).update({record["id"]: record for record in records})
        self.head = store.commit_record(
            self.root,
            expected_head=self.head["id"],
            command_id=uid(),
            state=state,
            event={**store._VERSION, "type": "synthetic_fixture_registered", "payload": {}},
            objects={record["id"]: store._canonical(record) for record in records},
        )
        return [self.ref(record) for record in records]

    def ref(self, record):
        return {
            "project_id": self.project,
            "head_id": self.head["id"],
            "artifact_id": record["id"],
            "sha256": store._hash(store._canonical(record)),
        }

    def snapshot(self):
        return commands.read_policy_snapshot(self.root)

    def position(self, **changes):
        record = {
            **envelope(self.project),
            "assignment_id": self.assignment["id"],
            "session_id": self.session["id"],
            "input_binding": self.input_ref,
            "issue_id": self.issue_id,
            "stance": "conditional",
            "rationale": "Support only if source A covers the target population.",
            "evidence_refs": [self.evidence_ref],
            "changed_from": None,
            "change_kind": None,
        }
        record.update(changes)
        return record

    def verification_result(self):
        output_ref = self.register(
            "fixture_outputs", {**envelope(self.project), "text": "source check output"}
        )[0]
        result = {
            **envelope(self.project),
            "verification_id": uid(),
            "output_refs": [output_ref],
            "outcome": "supported",
            "checked_scope": ["source A covers the target population"],
            "limitations": ["synthetic fixture"],
        }
        return result, self.register("verification_results", result)[0]

    def decision(self, position_ref, claim_ref, verification_ref, ack_refs=(), **changes):
        summary = "Reviewer supports the claim."
        decision = {
            **envelope(self.project, "coordinator"),
            "issue_ids": [self.issue_id],
            "position_refs": [position_ref],
            "claim_dispositions": [
                {"claim_ref": claim_ref, "disposition": "supported", "rationale": summary}
            ],
            "rationale_links": [
                {
                    "claim_ref": claim_ref,
                    "position_refs": [position_ref],
                    "verification_refs": [verification_ref],
                    "acknowledgement_refs": list(ack_refs),
                }
            ],
            "dissent": [],
            "next_action": {
                "kind": "finalize",
                "milestone": "M1",
                "node": "review",
                "attempt": uid(),
                "rationale": "Synthetic decision fixture",
            },
            "gate_result": {
                "ready": True,
                "reason_codes": [],
                "required_actions": [],
                "unresolved_issue_ids": [],
            },
        }
        decision.update(changes)
        return decision


def codes(errors):
    return [error["code"] for error in errors]


def test_position_change_accepts_exact_previous_bytes_and_preserves_inputs(tmp_path):
    f = Fixture(tmp_path / "p")
    previous = f.position()
    previous_ref = f.register("positions", previous)[0]
    referenced_path = store._store_path(f.root) / "objects" / previous_ref["sha256"]
    previous_bytes = referenced_path.read_bytes()
    added_ref = f.register(
        "fixture_evidence", {**envelope(f.project), "text": "source passage B"}
    )[0]
    changed = f.position(
        id=uid(),
        event_id=uid(),
        stance="support",
        rationale="Source B adds the missing population evidence.",
        evidence_refs=[f.evidence_ref, added_ref],
        changed_from=previous_ref,
        change_kind="evidence_added",
    )
    snapshot = f.snapshot()
    before_snapshot, before_payload = deepcopy(snapshot), deepcopy(changed)

    assert validate_position_change(snapshot, changed) == ()
    assert snapshot == before_snapshot and changed == before_payload
    assert store.read_head(f.root)["id"] == f.head["id"]
    assert referenced_path.read_bytes() == previous_bytes


def test_position_change_rejects_wrong_author_issue_or_reused_identity(tmp_path):
    f = Fixture(tmp_path / "p")
    previous = f.position()
    previous_ref = f.register("positions", previous)[0]

    wrong_issue = f.position(
        changed_from=previous_ref,
        change_kind="logic_correction",
        issue_id=uid(),
    )
    wrong_author = f.position(
        changed_from=previous_ref,
        change_kind="scope_changed",
        assignment_id=uid(),
    )
    reused = f.position(
        id=previous["id"],
        changed_from=previous_ref,
        change_kind="reinterpretation",
    )

    assert "position_change_binding_invalid" in codes(
        validate_position_change(f.snapshot(), wrong_issue)
    )
    assert "position_issue_missing" in codes(
        validate_position_change(f.snapshot(), wrong_issue)
    )
    assert "position_assignment_missing" in codes(
        validate_position_change(f.snapshot(), wrong_author)
    )
    assert "position_exists" in codes(validate_position_change(f.snapshot(), reused))


def test_position_change_rejects_missing_session_and_false_evidence_novelty(tmp_path):
    f = Fixture(tmp_path / "p")
    previous = f.position()
    previous_ref = f.register("positions", previous)[0]
    relabelled_ref = {**f.evidence_ref, "head_id": f.head["id"]}
    changed = f.position(
        changed_from=previous_ref,
        change_kind="evidence_added",
        evidence_refs=[relabelled_ref],
    )
    missing_session = f.position(session_id=uid())

    assert "position_change_source_missing" in codes(
        validate_position_change(f.snapshot(), changed)
    )
    assert "position_session_missing" in codes(
        validate_position_change(f.snapshot(), missing_session)
    )


def test_conditional_position_summarized_as_support_without_ack_is_position_ack_missing_and_unknown_ref(tmp_path):
    f = Fixture(tmp_path / "p")
    position = f.position()
    position_ref = f.register("positions", position)[0]
    claim_ref = f.register(
        "fixture_claims", {**envelope(f.project), "text": "The effect applies to everyone."}
    )[0]
    _, verification_ref = f.verification_result()
    unknown = {**verification_ref, "artifact_id": uid()}
    decision = f.decision(position_ref, claim_ref, unknown)
    snapshot, before = f.snapshot(), store.read_head(f.root)

    errors = validate_rationale_links(snapshot, decision)

    assert codes(errors).count("position_ack_missing") == 1
    assert codes(errors).count("ref_unknown") == 1
    assert len(decision["rationale_links"][0]["position_refs"]) == 1
    assert store.read_head(f.root) == before


def test_ack_binds_exact_position_claim_summary_disposition_and_actual_actor(tmp_path):
    f = Fixture(tmp_path / "p")
    position = f.position()
    position_ref = f.register("positions", position)[0]
    claim_ref = f.register(
        "fixture_claims", {**envelope(f.project), "text": "The effect applies to everyone."}
    )[0]
    _, verification_ref = f.verification_result()
    summary = "Reviewer supports the claim."
    ack = {
        "id": uid(),
        "project_id": f.project,
        "assignment_id": f.assignment["id"],
        "producer_id": f.assignment["actor_id"],
        "position_ref": position_ref,
        "claim_ref": claim_ref,
        "summary": summary,
        "disposition": "supported",
        "acknowledged": True,
    }
    ack_ref = f.register("position_acknowledgements", ack)[0]

    assert validate_rationale_links(
        f.snapshot(), f.decision(position_ref, claim_ref, verification_ref, [ack_ref])
    ) == ()

    for field, value in (
        ("position_ref", {**position_ref, "artifact_id": uid()}),
        ("claim_ref", {**claim_ref, "artifact_id": uid()}),
        ("summary", "Reviewer conditionally supports the claim."),
        ("disposition", "limited"),
        ("producer_id", "coordinator"),
    ):
        unrelated = {**ack, "id": uid(), field: value}
        unrelated_ref = f.register("position_acknowledgements", unrelated)[0]
        errors = validate_rationale_links(
            f.snapshot(),
            f.decision(position_ref, claim_ref, verification_ref, [unrelated_ref]),
        )
        assert "position_ack_missing" in codes(errors)


def test_claim_rejects_empty_role_and_verification_links_and_unknown_dissent_issue(tmp_path):
    f = Fixture(tmp_path / "p")
    position = f.position()
    position_ref = f.register("positions", position)[0]
    claim_ref = f.register(
        "fixture_claims", {**envelope(f.project), "text": "The effect applies to everyone."}
    )[0]
    _, verification_ref = f.verification_result()
    decision = f.decision(position_ref, claim_ref, verification_ref)
    decision["rationale_links"][0].update(position_refs=[], verification_refs=[])
    decision["dissent"] = [
        {
            "position_ref": position_ref,
            "issue_ids": [uid()],
            "rationale": "Synthetic dissent fixture",
        }
    ]

    errors = validate_rationale_links(f.snapshot(), decision)

    assert codes(errors).count("rationale_link_missing") == 3
    assert codes(errors).count("ref_unknown") == 1


def test_duplicate_claim_disposition_is_closed_error_and_does_not_mutate(tmp_path):
    f = Fixture(tmp_path / "p")
    position = f.position()
    position_ref = f.register("positions", position)[0]
    claim_ref = f.register(
        "fixture_claims", {**envelope(f.project), "text": "The effect applies to everyone."}
    )[0]
    _, verification_ref = f.verification_result()
    decision = f.decision(position_ref, claim_ref, verification_ref)
    decision["claim_dispositions"].append(
        {
            "claim_ref": claim_ref,
            "disposition": "limited",
            "rationale": "The effect applies only to the sampled population.",
        }
    )
    snapshot = f.snapshot()
    before_snapshot, before_decision = deepcopy(snapshot), deepcopy(decision)
    before_head = store.read_head(f.root)

    errors = validate_rationale_links(snapshot, decision)

    assert [error for error in errors if error["code"] == "claim_disposition_duplicate"] == [
        {
            "code": "claim_disposition_duplicate",
            "path": "$.claim_dispositions[1].claim_ref",
            "message": "Claim disposition is duplicated.",
        }
    ]
    assert snapshot == before_snapshot and decision == before_decision
    assert store.read_head(f.root) == before_head


def test_malformed_frozen_session_participants_fail_closed_in_both_validators(tmp_path):
    f = Fixture(tmp_path / "p")
    position = f.position()
    position_ref = f.register("positions", position)[0]
    claim_ref = f.register(
        "fixture_claims", {**envelope(f.project), "text": "The effect applies to everyone."}
    )[0]
    _, verification_ref = f.verification_result()
    malformed = {
        **f.session,
        "participant_assignment_ids": [f.assignment["id"], {}],
    }
    f.register("review_sessions", malformed)
    snapshot = f.snapshot()

    assert "position_session_missing" in codes(
        validate_position_change(snapshot, f.position())
    )
    assert "position_session_missing" in codes(
        validate_rationale_links(
            snapshot, f.decision(position_ref, claim_ref, verification_ref)
        )
    )


def test_validators_are_pure_after_verified_snapshot_read(tmp_path, monkeypatch):
    f = Fixture(tmp_path / "p")
    position = f.position()
    snapshot = f.snapshot()
    before_snapshot, before_position = deepcopy(snapshot), deepcopy(position)

    def forbidden(*args, **kwargs):
        raise AssertionError("pure A06 validator performed I/O")

    monkeypatch.setattr(store, "_history", forbidden)
    monkeypatch.setattr(store, "_read_file", forbidden)
    assert validate_position_change(snapshot, position) == ()
    assert snapshot == before_snapshot and position == before_position
