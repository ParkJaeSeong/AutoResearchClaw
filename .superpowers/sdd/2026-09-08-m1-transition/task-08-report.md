# Task 08 — M1 synthesis and exact evidence lineage

Implemented from base `43bd23d` in the isolated M1 worktree. Scope is Task 08 and the coordinator-approved read-only trace adapter/CLI. No store schema, legacy validator, graph advancement, council, external source retrieval, UI, or dependency changes. No subagents, real research approvals, push, or merge.

## Verification and TDD

- Initial RED: `.venv/bin/python -m pytest tests/codex_native/m1/test_synthesis.py -q` — **19 failed**. Missing module assertions, missing node reference validation, missing synthesis helper output, and missing CLI command demonstrated feature absence before production edits.
- Initial GREEN: the same command — **19 passed in 2.04s**.
- Added adverse lineage/version regressions. RED: **2 failed, 24 passed**. A gap referencing registered evidence but an empty top-level claim summary incorrectly reported no hypothesis evidence; and approving a different newer corpus incorrectly reported current authorization for an older trace. Fixed status to consider references across sections and gated current authorization by equality to the traced corpus binding.
- Additional coverage: retain unresolved conflicts, explicit historical synthesis selection, mutated extraction draft, newer extraction bytes with the same claim ID, later revocation, unknown claim, missing hydration/bytes/producer/registration/approval, corrupt hydrated bytes, structural failures stay out of registered artifacts, and one-value CLI JSON/stderr-only exit-2 errors.
- Final scoped run: `.venv/bin/python -m pytest tests/codex_native/m1 tests/codex_native/test_synthesis.py tests/codex_native/test_knowledge_extraction.py -q` — **292 passed in 8.76s**, zero failures/skips. Includes **26 Task 08 tests**.
- `.venv/bin/python -m compileall -q researchclaw/core/m1/synthesis.py researchclaw/core/m1/artifacts.py researchclaw/codex/m1_cli.py tests/codex_native/m1/test_synthesis.py` and `git diff --check` — exit 0, no diagnostics.
- The coordinator separately reported a process-level CLI/read-only acceptance pass using its own `task-08-acceptance.py`; the driver and verification/progress documents remain coordinator-owned.
- Full legacy suite was intentionally not run because of the coordinator-reported unrelated SSL hang. The relevant legacy synthesis and knowledge-extraction regressions above ran unchanged.

## APIs and content contract

`validate_synthesis_record(record: dict, *, known_claim_ids: set[str]) -> tuple[dict, ...]` is content-only, never mutates the input, and has no filesystem/network access. Required lists:

```json
{
  "claims": ["registered-extraction-claim-id"],
  "agreements": [{"id": "A1", "claim_refs": ["claim-id"], "summary": "Shared observation"}],
  "conflicts": [{"id": "X1", "claim_refs": ["claim-id"], "interpretations": ["Possible explanation"], "open_questions": ["Unresolved question"]}],
  "gaps": [{"id": "G1", "question": "Which condition remains unknown?", "claim_refs": ["claim-id"]}],
  "limitations": ["Access and interpretation limitations"]
}
```

IDs are unique across agreement/conflict/gap items. Claims and each claim_refs list contain unique, nonempty string IDs that resolve against the exact extraction input. Unknown IDs produce `m1_unknown_claim`; malformed shapes produce `m1_synthesis_invalid`. Descriptive additional metadata is allowed and is never executed. Agreements require evidence. An unreferenced gap or conflict requires `status: "unverified_question"` and a nonempty `reason`; it cannot claim a verified gap through another status. Zero gaps and zero conflicts are structurally valid. No fabricated quantity, fixed legacy Markdown sections, or legacy two-gap requirement is imposed.

`validate_synthesis_contents(files, inputs)` checks `knowledge/synthesis.json` against claim IDs parsed from the bound `knowledge/extractions.jsonl` bytes. `artifacts.validate_node_contents` dispatches synthesize to this adapter, so normal prepare/register rejects invalid references before artifacts are published. `knowledge/synthesis.md` remains a human-readable accompanying output subject to the existing structural/UTF-8 checks; the JSON is the authoritative structured synthesis record.

`synthesis_status(record)` is a separate informational result after validation:

```json
{
  "hypothesis_possible": true,
  "reasons": ["no_verified_gaps"],
  "scientific_validation": "not_performed",
  "handoff_readiness": "not_assessed"
}
```

Evidence referenced anywhere in the synthesis can motivate hypothesis work even with no asserted gap. With no referenced claims, `hypothesis_possible` is false and reasons additionally contains `no_claims`. `no_verified_gaps` records the lack of evidence-linked asserted gaps; it neither scientifically verifies any gap nor universally blocks a hypothesis based directly on claims. No council readiness or handoff completion is inferred from this result. Registration stays `review_pending` and retains scientific validation `not_performed`.

## Trace contract and version guarantees

The coordinator approved the minimal integration needed by the original two-argument interface: existing `store.read_head` has descriptors but no root or bytes. Its public shape remains unchanged.

- `read_trace_head(root: Path, *, synthesis_ref_id: str | None = None) -> dict` reads verified HEAD and adds transient `trace_synthesis_ref`, `trace_object_bytes` keyed by SHA256, and `trace_current_authorization`. By default it selects the newest registered synthesis artifact. A supplied artifact ID pins an older registered synthesis exactly. Unknown selections raise `m1_trace_synthesis_missing`. The hydrated context contains bytes and is an internal Python input, not the CLI JSON output or a new persisted schema.
- `trace_claim(head: dict, claim_id: str) -> dict` requires that hydrated context. Plain receipts raise `m1_trace_context_missing`. No mutable drafts, logical-path latest-evidence fallback, or network/source-file access occurs.
- The selected synthesis producer's exact input_refs select extraction bytes; the extraction producer's exact input_refs select all eight approved corpus/context artifacts. Registered descriptor identity, digest and size are checked when consuming bytes. Missing or changed exact objects fail explicitly.
- The extraction's `node_outputs_registered` event fixes the historical time boundary. Only corpus decisions preceding that event can authorize it; the latest valid matching decision at that boundary must be approve. Later approvals cannot backfill missing authorization. The included source is resolved from that exact shortlist.
- `approval_at_extraction` contains the historical authorizing record. `current_authorization` exposes the current corpus/decision and `traced_corpus_is_current`; its `approved` is true only when the currently approved corpus binding equals the traced binding. A newer approved corpus does not authorize the old trace, and a later rejection does not erase its historical approval.
- The trace includes version fields, head_id, data_origin=`registered`, project content_origin, claim, synthesis_ref, extraction_ref, extraction_attempt_id, corpus, source, historical/current approval information, original locator/URL/access declaration, claim/synthesis limitations, claim-related synthesis conflicts, and synthesis_status. Returned structures are copied.

CLI:

```text
researchclaw-codex m1 trace ROOT --claim CLAIM_ID [--synthesis SYNTHESIS_ARTIFACT_ID] --json
```

Success writes exactly one JSON trace to stdout. Invalid claim/context/lineage requests follow existing stderr/exit-2 behavior. Read-only operations do not register, normalize, approve, advance, or write project data.

The current collection contract does not register original full-text files. Consequently the original source output reports `file_available: false`, `full_text_verified: false`, and `verification_status: "not_performed"`, while retaining the actual declared evidence level and locator/URL. It never treats an abstract, a URL, a supporting excerpt, or a declared full_text level as proof of original-text retrieval/verification. Actual full-text artifact registration/linkage remains outside Task 08's existing source contracts.

## Synthetic helper and ownership

`build_evidence_case(root)` now retains its existing root/head_id/artifact_refs/corpus_binding/corpus_refs return keys and registers both synthesis JSON and Markdown. The added transition is an explicit synthetic, declared-only test checkpoint; extraction and synthesis still preserve their review gates, and scientific validation remains not_performed. The single earlier helper expectation in test_approvals now expects current node synthesize; no legacy validator test changed.

Owned files:

```text
researchclaw/core/m1/synthesis.py
researchclaw/core/m1/artifacts.py
researchclaw/codex/m1_cli.py
tests/codex_native/m1/test_synthesis.py
tests/codex_native/m1/helpers.py
tests/codex_native/m1/test_approvals.py
.superpowers/sdd/2026-09-08-m1-transition/task-08-report.md
```

Limitations: validation checks structure and exact references, not scientific correctness; approval authority remains declared_only; source locators/access are declarations; the helper is synthetic and supplies no completed real research/council evidence. There is no unresolved implementation blocker within Task 08 scope.
