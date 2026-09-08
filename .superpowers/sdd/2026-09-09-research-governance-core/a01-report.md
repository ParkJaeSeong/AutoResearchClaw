# A01 implementation report

Commit: d82bce2 (feat(research-graph): A01 공통 기록·참조 계약).

Owned changes: contracts.py, package __init__.py, test_contracts.py, test package __init__.py (root-authorized collection fix), ten checked-in JSON examples under docs/superpowers/acceptance/research-graph-a01. Ignored docs examples explicitly force-added so a clean checkout has fixtures.

Validation: Initial RED failed importing the absent research_graph module. Attempt identity correction demonstrated two failing ordinal acceptance assertions, then GREEN. Nullable ownership correction demonstrated one failing assertion, then GREEN. Final `.venv/bin/python -m pytest tests/codex_native/research_graph/test_contracts.py tests/codex_native/m1/test_contracts.py tests/codex_native/test_contracts.py -q`: 107 passed. Initial combined collection exposed duplicate module basenames; package initializer resolves this under default import mode. git diff --check clean before final minor ownership amendment.

## Exact schema rulings

The complete closed field definitions, including every nested object, are `_COMMON`, `_REF`, `_TRANSFER`, `_GATE`, and `_CONTRACTS` in contracts.py. All fields are mandatory unless explicitly optional(); nullable() permits explicit null while retaining required presence. All ten kinds have synthetic JSON examples, which are structural examples only (references are deliberately not a valid research graph).

Common: schema_version exact int 1; workflow_version exact string research-graph-v1; project_id/id/event_id UUID; producer_id opaque nonblank string; content_origin real|synthetic|mixed; provenance_status declared_only|host_observed; observation_refs list of exact SnapshotRefs. host_observed requires nonempty observation refs, but this does not prove the host observation.

Embedded SnapshotRef: project_id UUID, head_id lowercase 64-hex digest, artifact_id opaque nonblank string, sha256 lowercase 64-hex digest. Standalone SnapshotRef additionally has common metadata. No same-project restriction: source projects can be deterministically namespace-mapped by A03. Historical source identifiers remain migration metadata, not fabricated new identities.

Issue: origin {milestone M1|M2|M3,node text,attempt UUID,local_issue_id opaque text}; question text; category source|logic|methodology|empirical|integrity|scope|reporting|other; target_refs; severity blocking|major|minor|optional; blocking_scope list {kind node|handoff|finalization,milestone,target_id text}; resolution_condition text; owner_assignment_id nullable UUID (explicit unassigned imports).

IssueEvent: issue_id; from_status nullable status; to_status status; actor_assignment_id; rationale text; verification_refs; successor_ids UUID list. Status open|checking|resolved|deferred|transferred|reopened|superseded. Optional to_milestone/owner_assignment_id/verification_id/acceptance_event_id all required nonempty on transferred, with transfer_acceptance_missing for absent references. superseded requires successor_ids. No transition legality or graph evidence check.

Verification: issue_ids UUID list; method source_check|logic_check|calculation|experiment|human_decision; question text; input_refs; acceptance_rule text; owner_assignment_id UUID; budget_ref SnapshotRef.

VerificationResult: verification_id UUID; output_refs; outcome supported|refuted|inconclusive|failed; checked_scope and limitations lists of nonblank text.

Position: assignment_id/session_id/issue_id UUID; input_binding SnapshotRef; stance support|oppose|conditional|abstain|uncertain; rationale text; evidence_refs; changed_from nullable SnapshotRef; change_kind nullable evidence_added|reinterpretation|logic_correction|scope_changed. Only optional field confidence: finite number 0..100, excluding bool; no ready field or readiness calculation.

Decision: issue_ids; position_refs; claim_dispositions list {claim_ref,disposition supported|refuted|inconclusive|limited|withdrawn,rationale}; rationale_links list {claim_ref,position_refs,verification_refs,acknowledgement_refs}; dissent list {position_ref,issue_ids,rationale}; next_action {kind verify|revise|handoff|awaiting_input|blocked_budget|stop|finalize,milestone,node text,attempt UUID,rationale}; gate_result {ready exact bool,reason_codes text list,required_actions text list,unresolved_issue_ids UUID list}. Gate result is a structurally checked assertion, not computed or accepted as scientifically valid.

Handoff: from_milestone/to_milestone; source_head digest; artifact_refs; unresolved_issue_ids; transfer_proposals list {issue_id,to_milestone,owner_assignment_id,verification_id,resolution_condition text,acceptance_event_id nullable UUID}; limitations text list; acceptance_ref nullable SnapshotRef. Proposal issuance can precede acceptance.

Dependency: from_ref/to_ref; relation supports|derived_from|tests|reports; origin_group_id nonblank opaque text, including literal unknown. No independence counting or DAG validation.

ApprovalBinding: existing_receipt_ref; scope_refs; binding SnapshotRef; validity valid|needs_revalidation|expired|revoked|unknown. No new approval authority.

General references are SnapshotRefs, direct record linkage IDs UUIDs. Lists may be empty except explicit structural discriminator requirements. No I/O, lifecycle mutation, ID lookup, approval lookup, independent resolver verification, science scoring, or confidence-to-ready inference. All malformed JSON-shaped nested values return ordered {code,path,message} errors, not exceptions. Imported legacy attempt IDs will need UUID mapping; display ordinals remain outside exact reference fields.
