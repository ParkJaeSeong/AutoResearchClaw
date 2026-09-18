# Import review preparation implementation plan

> **For agentic workers:** Use superpowers:executing-plans inline. Steps use checkbox syntax.

**Goal:** Turn saved import results into durable, versioned review preparation tasks without changing research decisions.
**Architecture:** Reconcile already processed events (including ACKed events) into a project-local SQLite queue. Freeze page bytes with existing A1 authentication before marking an input ready. Keep failures as recovery tasks.
**Tech Stack:** Python, SQLite, existing AtlasClient and handoff journal.
**Spec:** ../specs/2026-09-17-atlas-triggered-research-review-design.md

## Global constraints

No remote submissions, no scientific completion or model execution in this slice. Existing QA council requires a separate import input adapter; this first independently testable delivery prepares its immutable inputs. Keep credentials outside stored tasks. Question revision and policy are explicit inputs. Preserve existing research HEAD. No new dependencies.

## Task 1: Durable reconciliation

Files: researchclaw/codex/import_review.py, tests/codex_native/test_import_review.py.
Interface: ImportReviewQueue(journal); reconcile(context) -> list of tasks. Context contains question_revision, question, purpose, policy_revision. Queue shares the journal database and transaction boundary; tasks have deterministic keys from instance/import/result/question/purpose/policy. Immutable context conflicts fail.

- [x] Write failing tests for repeated ACKed result reconciliation, new question revision, invalid result hash, failed diagnostic routing.
- [x] Run `.venv/bin/python -m pytest tests/codex_native/test_import_review.py -q` and verify missing module failure.
- [x] Implement reconciliation using `INSERT OR IGNORE`, canonical hash verification and fixed event/payload association. No normal scientific review for diagnostic events.
- [x] Run tests; inspect changed files.

## Task 2: Frozen page input

Same files. Interface: prepare(task_id, client) -> task. Read A1 instance before page requests. Request expected_sha256/include_raw. Decode with existing unpack_raw; store page bytes atomically in SQLite. Mark input_ready only when nonempty pages and read_scope exist. Error leaves awaiting_input and propagates; retry reuses original refs. No current-page replacement.

- [x] Write failing tests for wrong instance, changed page, restart after preparation, and altered saved input.
- [x] Implement and run the above test command.
- [x] Run existing handoff tests to check journal compatibility.

## Task 3: Explicit command and real saved-result preparation

Same module exposes `python -m researchclaw.codex.import_review ROOT --context FILE --atlas-connection FILE`. ROOT must be existing native project with matching journal identity. Command reconciles saved results and prepares pending inputs; never submits external jobs. It prints only IDs/status, not credentials.

- [x] Add CLI validation test for wrong project; implement entry point.
- [x] On saved PC/CNT result, freeze current question context and reconcile/prepare with existing A1 connection. Preserve HEAD and record result/limits in project materials.
- [x] Update plan completion status; report prepared input separately from council execution.

## Next separate slice

Adapt immutable import input to existing council provenance/episode commands; run independent initial/response/final and store decision under project writer lock. Add automatic runner hook only after explicit input preparation and council integration tests. Bundle synthesis and OS startup remain outside this delivery.

## Delivery evidence

2026-09-17: 9 new tests and 24 handoff regressions passed (33 total). Explicit preparation of the existing PC/CNT result succeeded twice with one task and one frozen page. Research HEAD unchanged. No model invocation, remote task submission, or automatic service activation. QA council adaptation remains the next separate slice.
