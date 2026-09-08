# Task 09 — M1 hypothesis records and reviewer separation

Implemented in the isolated M1 worktree from coordinator bookkeeping base `bf65d7c` (Task 08 source review base `d13684c`). Scope is Task 09 only. No store schema, legacy hypothesis rules, graph advancement, council engine, host authentication, external retrieval, M2 execution, or dependency changes. No subagents, push, or merge.

## Verification

- TDD RED: `.venv/bin/python -m pytest tests/codex_native/m1/test_hypotheses.py -q` — **34 failed, 1 passed in 1.47s**. Failures showed the missing hypothesis module, content adapter, exact extraction input and prior hypotheses binding. The existing no-op adapter already accepted the gap-only positive case; negative cases demonstrated the missing validation.
- Initial GREEN: the same command — **35 passed in 2.02s**.
- Additional adverse integration coverage and helper cleanup: **41 passed in 3.75s**. Covered a newer extraction present before preparation, newer extraction after preparation, mutable extraction draft, missing synthesis producer/extraction binding, canonical old revision preservation, changed historical evidence, and rejection without artifact publication. Synthetic new-attempt checkpoints preserve prior attempts and explicitly declare `declared_only`; they do not claim real review or public graph advancement.
- Final scoped command: `.venv/bin/python -m pytest tests/codex_native/m1 tests/codex_native/test_hypothesis_generation.py -q` — **245 passed in 12.50s**, zero failures/skips.
- `.venv/bin/python -m compileall -q researchclaw/core/m1/hypotheses.py researchclaw/core/m1/artifacts.py researchclaw/core/m1/packets.py researchclaw/core/m1/roles.py tests/codex_native/m1/test_hypotheses.py` and `git diff --check` — exit 0, no diagnostics.
- Coordinator separately reported its live synthetic H1/r1 registration through public prepare/register passed and stayed `review_pending`. This report does not claim to have independently performed the coordinator's check or any actual council review.
- The full legacy suite was intentionally not run; only the requested unchanged hypothesis-generation regression ran alongside all M1 tests.

## Stable JSON and Python contract

Authoritative output `hypotheses/hypotheses.json`:

```json
{
  "schema_version": 1,
  "hypotheses": [
    {
      "id": "H1",
      "revision": 1,
      "parent_revision": null,
      "author_assignment_id": "author-one",
      "change_reason": null,
      "statement": "The observed difference depends on context.",
      "claim_refs": ["claim-one"],
      "gap_refs": [],
      "predicted_observation": "The difference diminishes in a shared context.",
      "falsification_condition": "The difference persists under comparable conditions.",
      "alternatives": ["Selection effects explain the observed difference."],
      "feasibility_notes": "Comparable observations appear accessible; access is unverified.",
      "open_design_questions": ["Which conditions and measurements should M2 use?"],
      "disposition": "draft"
    }
  ]
}
```

`hypotheses/hypotheses.md` is the accompanying readable output, subject to existing structural/UTF-8 checks. The JSON determines structured content validation. Descriptive extra metadata is accepted and never executed.

- `validate_hypothesis(record: dict, *, claim_ids: set[str], gap_ids: set[str]) -> tuple[dict, ...]` is pure single-record validation. All example fields are required. Text fields are nonempty strings; alternatives and open design questions are string lists and may be empty. Reference lists are unique nonempty ID strings; at least one claim or gap reference is required per candidate. IDs resolve against the caller-provided exact evidence sets. The pure function cannot prove prior artifact registration; the node adapter performs that check.
- `hypothesis_key(record: dict) -> tuple[str, int]` returns `(id, revision)` with no normalization. The validator requires a positive integer revision and rejects booleans.
- `can_review(*, author_assignment_id: str, reviewer_assignment_id: str) -> bool` returns inequality only. Author IDs must be nonempty in records, but distinct strings do not establish authenticated identity, host execution, authority, or independence. Task 10 must check real assignment provenance separately.
- `validate_hypothesis_contents(files, inputs)` is the node content adapter. `artifacts.validate_node_contents` dispatches `hypothesize` to it before successful artifact publication.
- Allowed disposition values are `draft`, `revise`, `selected`, `rejected`, `deferred`. These labels do not create review decisions or graph authorization.
- An empty initial envelope requires a nonempty `no_hypotheses_reason`: `{"schema_version":1,"hypotheses":[],"no_hypotheses_reason":"Current evidence does not support a testable proposal."}`. It records a valid no-candidate outcome without authorizing an M1 handoff.

No minimum of two candidates, numerical magnitude, novelty threshold, mandatory opposite hypothesis, or evidence-gap count is imposed. Gaps may be absent. Gap-only references may motivate a proposal, but an unverified synthesis question is not promoted into scientific evidence or a verified gap by validation.

## Immutable revision and evidence binding

The hypotheses list is cumulative, retaining all registered records exactly, compared through canonical JSON. A duplicate `(id, revision)` is invalid. An existing key cannot be overwritten or omitted. A new ID starts at revision 1 with explicit null parent/reason. A subsequent revision must be the next integer after the latest bound registered version, point to that immediate parent, preserve the initial `author_assignment_id`, and include nonempty `change_reason`. Merely placing an unregistered parent in the same draft is insufficient. Each existing ID can add its next revision in a submission. Text/hash-only changes without a reason are rejected.

Historical records remain attached to their original registered artifact and producer input binding. They are compared for exact preservation, not reinterpreted using newer claim IDs. Newly added records are checked against the current exact evidence. This allows preservation of old references when a new revision uses changed evidence; it does not silently resolve an old claim to a newer extraction with the same ID.

The minimal packet integration adds:

1. The latest selected synthesis artifact's producer must be a matching `synthesize` attempt containing that exact output ref.
2. Its exact `knowledge/extractions.jsonl` input ref must resolve to a registered artifact. That ref, not the latest logical extraction path, enters the hypothesis packet binding and immutable input snapshot.
3. When present, the prior registered `hypotheses/hypotheses.json` artifact also enters the packet binding. Changes after preparation are detected by the existing complete input-binding check.

Missing producer/extraction lineage fails explicitly as `m1_hypothesis_synthesis_producer_missing` or `m1_hypothesis_extraction_ref_missing`. Existing digest/size checks validate consumed bytes. Unknown candidate claims/gaps report `m1_unknown_claim` / `m1_unknown_gap`; malformed records report `m1_hypothesis_invalid`; duplicate keys, changed history, missing registered parent and changed author have dedicated hypothesis issue codes. Envelope/JSON/input parsing failures are wrapped in `m1_hypotheses_input_invalid` with the underlying reason.

Existing registration behavior stays intact: invalid drafts consume the established correction budget, remain unpublished, and preserve prior artifacts; success remains `review_pending` and scientific validation `not_performed`. There is no automatic progression or reassessment of earlier approvals.

## Reviewer questions and example disposition

The review role contract explicitly asks domain reviewers about contribution and bound evidence; methodology reviewers about discriminating observations, falsification and open M2 design questions; and critical/reproducibility reviewers about competing explanations and conditions of failure. The coordinator remains nonvoting and may not write others' positions.

The synthetic example above is structurally eligible for independent review because it uses a registered claim, qualitative prediction, falsification condition, alternative explanation and feasibility/design uncertainty. Its scientific disposition remains unresolved: abstract-only source access and unverified comparability do not establish causal support or readiness for M2. A reference-free candidate, an unknown claim/gap, a missing falsification condition, or a changed revision without reason is held as an invalid draft with explicit issues. One valid candidate is sufficient to represent a proposal; no extra candidates or quantities are fabricated.

## Self-review and ownership

Self-review checked the task brief, common field and role constraints, exact input lineage, immutable revision behavior, invalid-draft publication boundary, legacy isolation, and the limits of assignment inequality. No unresolved Task 09 blocker remains. Task 10 still needs real assignment identity/provenance checks and council submission orchestration; future return/decision engines own actual graph movement and readiness.

Owned paths:

```text
researchclaw/core/m1/hypotheses.py
researchclaw/core/m1/artifacts.py
researchclaw/core/m1/packets.py
researchclaw/core/m1/roles.py
tests/codex_native/m1/test_hypotheses.py
skills/researchclaw/references/m1-hypotheses.md
.superpowers/sdd/2026-09-08-m1-transition/task-09-report.md
```

Coordinator plan, progress, acceptance fixtures and verification documents are outside this commit.
