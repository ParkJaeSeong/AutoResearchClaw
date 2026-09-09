"""Pure position-change and decision-rationale linkage validation.

The validators establish structural and immutable-reference bindings only. They
do not register positions, infer scientific support, or mutate a project.
"""
from uuid import UUID

from .contracts import validate_record
from .issues import _Inputs


def _error(code, path, message):
    return {"code": code, "path": path, "message": message}


def _ref_key(ref):
    if type(ref) is not dict:
        return None
    return (ref.get("project_id"), ref.get("artifact_id"), ref.get("sha256"))


class _Context:
    def __init__(self, snapshot):
        try:
            self.inputs = _Inputs(snapshot)
            self.state = self.inputs.state
            self.project = self.inputs.project
            self.valid = True
        except (KeyError, TypeError, ValueError):
            self.inputs, self.state, self.project, self.valid = None, {}, None, False

    def registered(self, collection, identity):
        try:
            return self.inputs.registered(collection, identity)
        except (KeyError, TypeError, ValueError):
            return None

    def reference(self, ref, collection=None):
        try:
            return self.inputs.reference(ref, collection)
        except (KeyError, TypeError, ValueError):
            return None


def _assignment(context, identity):
    assignment = context.registered("assignments", identity)
    if (
        type(assignment) is not dict
        or set(assignment) != {"id", "project_id", "actor_id", "role", "milestone", "active"}
        or type(assignment.get("actor_id")) is not str
        or not assignment["actor_id"].strip()
        or assignment.get("role") not in ("owner", "resolver")
        or assignment.get("milestone") not in ("M1", "M2", "M3")
        or assignment.get("active") is not True
    ):
        return None
    return assignment


def _session(context, identity):
    session = context.registered("review_sessions", identity)
    if (
        type(session) is not dict
        or set(session)
        != {"id", "project_id", "input_binding", "participant_assignment_ids", "frozen"}
        or session.get("frozen") is not True
        or type(session.get("participant_assignment_ids")) is not list
        or not session["participant_assignment_ids"]
        or len(set(session["participant_assignment_ids"]))
        != len(session["participant_assignment_ids"])
        or context.reference(session.get("input_binding")) is None
    ):
        return None
    return session


def _position_policy_errors(context, position, *, require_new):
    errors = []
    if position["project_id"] != context.project:
        errors.append(_error("position_project_mismatch", "$.project_id", "Position belongs to another project."))
    if require_new and position["id"] in context.state.get("positions", {}):
        errors.append(_error("position_exists", "$.id", "Position identity is already registered."))
    if require_new and any(
        item.get("event_id") == position["event_id"]
        for item in context.state.get("positions", {}).values()
        if type(item) is dict
    ):
        errors.append(_error("position_event_exists", "$.event_id", "Position event identity is already registered."))

    issue = context.registered("issues", position["issue_id"])
    if issue is None or validate_record("Issue", issue):
        errors.append(_error("position_issue_missing", "$.issue_id", "Exact registered issue is required."))

    assignment = _assignment(context, position["assignment_id"])
    if assignment is None:
        errors.append(_error("position_assignment_missing", "$.assignment_id", "Active position assignment is not registered."))
    elif position["producer_id"] != assignment["actor_id"]:
        errors.append(_error("position_actor_mismatch", "$.producer_id", "Position producer is not the assigned actor."))

    session = _session(context, position["session_id"])
    if session is None:
        errors.append(_error("position_session_missing", "$.session_id", "Frozen review session is not registered."))
    elif (
        position["assignment_id"] not in session["participant_assignment_ids"]
        or position["input_binding"] != session["input_binding"]
    ):
        errors.append(_error("position_session_mismatch", "$.session_id", "Position is not bound to its actor's frozen session input."))

    for path, ref in [
        ("$.input_binding", position["input_binding"]),
        *[(f"$.evidence_refs[{index}]", ref) for index, ref in enumerate(position["evidence_refs"])],
        *[(f"$.observation_refs[{index}]", ref) for index, ref in enumerate(position["observation_refs"])],
    ]:
        if context.reference(ref) is None:
            errors.append(_error("ref_unknown", path, "Reference is not exact, current, and verified."))

    changed_from, change_kind = position["changed_from"], position["change_kind"]
    if (changed_from is None) != (change_kind is None):
        errors.append(_error("position_change_binding_invalid", "$.changed_from", "Changed position requires both prior position and change kind."))
    elif changed_from is not None:
        previous = context.reference(changed_from, "positions")
        if previous is None or validate_record("Position", previous):
            errors.append(_error("ref_unknown", "$.changed_from", "Prior position reference is not exact and verified."))
        else:
            if (
                previous.get("id") == position["id"]
                or previous.get("issue_id") != position["issue_id"]
                or previous.get("assignment_id") != position["assignment_id"]
                or assignment is None
                or previous.get("producer_id") != assignment["actor_id"]
            ):
                errors.append(_error("position_change_binding_invalid", "$.changed_from", "Prior position must be a distinct position by the same issue author."))
            previous_evidence = {_ref_key(ref) for ref in previous.get("evidence_refs", [])}
            current_evidence = {_ref_key(ref) for ref in position["evidence_refs"]}
            if change_kind == "evidence_added" and not current_evidence - previous_evidence:
                errors.append(_error("position_change_source_missing", "$.evidence_refs", "Evidence-added change requires newly referenced evidence bytes."))
            elif change_kind == "reinterpretation" and not current_evidence & previous_evidence:
                errors.append(_error("position_change_source_missing", "$.evidence_refs", "Reinterpretation requires an exact retained evidence source."))
            elif change_kind in ("logic_correction", "scope_changed") and not current_evidence:
                errors.append(_error("position_change_source_missing", "$.evidence_refs", "Logic or scope change requires an explicit source link."))
    return errors


def validate_position_change(snapshot: dict, payload: dict) -> tuple[dict, ...]:
    """Validate one unregistered Position against a verified policy snapshot."""
    structural = validate_record("Position", payload)
    if structural:
        return structural
    context = _Context(snapshot)
    if not context.valid:
        return (_error("position_context_missing", "$", "Verified policy snapshot context is required."),)
    return tuple(_position_policy_errors(context, payload, require_new=True))


def _valid_ack(ack, context, position, position_ref, claim_ref, disposition):
    expected_keys = {
        "id",
        "project_id",
        "assignment_id",
        "producer_id",
        "position_ref",
        "claim_ref",
        "summary",
        "disposition",
        "acknowledged",
    }
    try:
        UUID(ack["id"])
    except (KeyError, ValueError, TypeError, AttributeError):
        return False
    assignment = _assignment(context, position["assignment_id"])
    return (
        set(ack) == expected_keys
        and ack["project_id"] == context.project
        and ack["assignment_id"] == position["assignment_id"]
        and assignment is not None
        and ack["producer_id"] == assignment["actor_id"] == position["producer_id"]
        and ack["position_ref"] == position_ref
        and ack["claim_ref"] == claim_ref
        and type(ack["summary"]) is str
        and bool(ack["summary"].strip())
        and ack["disposition"] == disposition["disposition"]
        and ack["summary"] == disposition["rationale"]
        and ack["acknowledged"] is True
    )


def validate_rationale_links(snapshot: dict, decision: dict) -> tuple[dict, ...]:
    """Validate that each decision rationale is traceable and author-acknowledged."""
    structural = validate_record("Decision", decision)
    if structural:
        return structural
    context = _Context(snapshot)
    if not context.valid:
        return (_error("position_context_missing", "$", "Verified policy snapshot context is required."),)
    errors = []
    if decision["project_id"] != context.project:
        errors.append(_error("position_project_mismatch", "$.project_id", "Decision belongs to another project."))
    declared_issues = set(decision["issue_ids"])
    for index, issue_id in enumerate(decision["issue_ids"]):
        issue = context.registered("issues", issue_id)
        if issue is None or validate_record("Issue", issue):
            errors.append(_error("ref_unknown", f"$.issue_ids[{index}]", "Decision issue is not exact and registered."))

    positions = {}
    for index, ref in enumerate(decision["position_refs"]):
        position = context.reference(ref, "positions")
        if position is None or validate_record("Position", position):
            errors.append(_error("ref_unknown", f"$.position_refs[{index}]", "Position reference is not exact and verified."))
        else:
            positions[tuple(sorted(ref.items()))] = position
            errors.extend(_position_policy_errors(context, position, require_new=False))

    dispositions = {}
    for index, disposition in enumerate(decision["claim_dispositions"]):
        ref = disposition["claim_ref"]
        if context.reference(ref) is None:
            errors.append(_error("ref_unknown", f"$.claim_dispositions[{index}].claim_ref", "Claim reference is not exact and verified."))
        dispositions[tuple(sorted(ref.items()))] = disposition

    linked_claims = set()
    linked_positions = set()
    for link_index, link in enumerate(decision["rationale_links"]):
        claim_key = tuple(sorted(link["claim_ref"].items()))
        disposition = dispositions.get(claim_key)
        if disposition is None:
            errors.append(_error("rationale_link_missing", f"$.rationale_links[{link_index}].claim_ref", "Rationale link has no exact claim disposition."))
            continue
        linked_claims.add(claim_key)
        if not link["position_refs"]:
            errors.append(_error("rationale_link_missing", f"$.rationale_links[{link_index}].position_refs", "Claim rationale requires an actual role position."))
        if not link["verification_refs"]:
            errors.append(_error("rationale_link_missing", f"$.rationale_links[{link_index}].verification_refs", "Claim rationale requires an actual verification result."))
        for index, ref in enumerate(link["verification_refs"]):
            result = context.reference(ref, "verification_results")
            if result is None or validate_record("VerificationResult", result):
                errors.append(_error("ref_unknown", f"$.rationale_links[{link_index}].verification_refs[{index}]", "Verification result reference is not exact and verified."))

        acknowledgements = []
        for index, ref in enumerate(link["acknowledgement_refs"]):
            ack = context.reference(ref, "position_acknowledgements")
            if ack is None:
                errors.append(_error("ref_unknown", f"$.rationale_links[{link_index}].acknowledgement_refs[{index}]", "Acknowledgement reference is not exact and verified."))
            else:
                acknowledgements.append(ack)
        for index, ref in enumerate(link["position_refs"]):
            key = tuple(sorted(ref.items()))
            position = positions.get(key)
            if position is None:
                errors.append(_error("ref_unknown", f"$.rationale_links[{link_index}].position_refs[{index}]", "Linked position reference is not declared and verified."))
                continue
            linked_positions.add(key)
            if not any(
                _valid_ack(ack, context, position, ref, link["claim_ref"], disposition)
                for ack in acknowledgements
            ):
                errors.append(_error("position_ack_missing", f"$.rationale_links[{link_index}].position_refs[{index}]", "Position author did not acknowledge this exact claim summary and disposition."))

    for key in dispositions.keys() - linked_claims:
        errors.append(_error("rationale_link_missing", "$.rationale_links", "Claim disposition has no rationale link."))
    for key in positions.keys() - linked_positions:
        errors.append(_error("rationale_link_missing", "$.rationale_links", "Decision position has no rationale link."))
    declared_position_refs = set(positions)
    for index, dissent in enumerate(decision["dissent"]):
        position_key = tuple(sorted(dissent["position_ref"].items()))
        if (
            position_key not in declared_position_refs
            or context.reference(dissent["position_ref"], "positions") is None
        ):
            errors.append(_error("ref_unknown", f"$.dissent[{index}].position_ref", "Dissent position is not exact and declared."))
        for issue_index, issue_id in enumerate(dissent["issue_ids"]):
            issue = context.registered("issues", issue_id)
            if issue_id not in declared_issues or issue is None or validate_record("Issue", issue):
                errors.append(_error("ref_unknown", f"$.dissent[{index}].issue_ids[{issue_index}]", "Dissent issue is not exact and declared."))
    for index, ref in enumerate(decision["observation_refs"]):
        if context.reference(ref) is None:
            errors.append(_error("ref_unknown", f"$.observation_refs[{index}]", "Observation reference is not exact and verified."))
    return tuple(errors)
