# Atlas File Evidence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Import an Atlas QA file, preserve evidence versions, link usage/review/decision and follow-up questions, and expose the workflow in the existing Pilot UI.

**Architecture:** Pure QA format parsing feeds immutable graph operations. CLI and same-origin HTTP share the parser and dispatcher. Existing node-neutral councils bind to a frozen usage review; existing workflow gates remain unchanged.

**Tech Stack:** Python, PyYAML, existing research_graph store, stdlib HTTP server, vanilla JavaScript, pytest and existing Node UI tests.

**Spec:** ../specs/2026-09-12-atlas-file-evidence-design.md

## Global Constraints

- Atlas owns collection/extraction. No Atlas writes or autonomous outbound messages.
- QA input ≤10 MiB, UTF-8 schema 1, duplicate YAML keys and unsupported versions rejected.
- No automatic source reading, attribution inference, approvals, issue resolution, stage completion or fake council submissions.
- Original QA bytes and exact references are immutable. Shared source does not become multiple independent papers.
- Existing worktree feature/m1-research-graph; preserve unrelated research changes.

## A1: Parse a QA file

Files: core/research_graph/atlas_format.py; tests/codex_native/research_graph/test_atlas_intake.py.
Interface: `parse_atlas_qa(data: bytes) -> dict` returns schema_version/id/question/answer/project/consulted_pages/candidates/file_sha256/missing_fields. Required ID/question/answer nonblank, project nullable, omitted lists empty. Preserve JSON-compatible source metadata. CLI owns file reads, core revalidates supplied bytes.

- [x] Write tests with an Atlas-style YAML header containing a Markdown table in its quoted answer, optional missing sources and null project. Assert exact answer and hash.
- [x] Run `.venv/bin/python -m pytest tests/codex_native/research_graph/test_atlas_intake.py -q` and observe missing parser failure.
- [x] Implement closed supported version/field validation, duplicate-key/alias/resource protection, bytes limit and delimiter handling without reading referenced paths.
- [x] Test malformed metadata, unsupported version, aliases, invalid UTF-8 and size boundary; rerun focused suite.

## A2: Immutable external evidence

Files: core/research_graph/external_evidence.py, commands.py, views.py; test_external_evidence.py.
Operation `external.evidence.import`: `{content_base64,sha256,filename,producer_id}`. Reparse bytes and verify sha. Store original blob and record with qa metadata, previous_ref. Identity is project+QA ID+raw hash. View entries `{record,ref,artifact_id,latest,newer_ref}` in `external_evidence`.

- [x] Write public dispatcher tests asserting saved bytes, unchanged original policy collections, idempotent import, changed contents create new version, historical view remains old.
- [x] Observe `unknown_operation` before registration.
- [x] Implement strict payload and verified history validation, operation registration and hydrated snapshot.
- [x] Verify stale HEAD, wrong hash, forged stored record and malformed input cannot mutate current HEAD.

## A3: Usage, councils and decisions

Files: same external core and tests; existing councils reused.
Operation `external.review.record`: `{evidence_ref,question_ref,status,allowed_uses,held_uses,limitations,rationale,producer_id}`. Status use/limited/hold/exclude. Question ref is an actual question revision or the external QA evidence itself.
Operation `external.decision.record`: `{review_ref,title,conclusion,rationale,limitations,submission_refs,prior_ref,producer_id}`. Empty submissions mean coordinator-only. Nonempty references must match the disclosed final submissions bound to the exact review.
Operation `external.question.record`: `{decision_ref,question,missing_evidence,decision_impact,scope,producer_id}`. Saved draft only.

- [x] Tests: foreign or missing refs rejected atomically; real question and evidence refs accepted; old evidence retained after new QA; no council authority granted by decision alone.
- [x] Implement immutable usage, decision, question records and native view projections.
- [x] Prepare existing generic council with usage review as input_binding; test initial privacy and real final-ref checking. Reject partial/hidden/unrelated submissions.
- [x] Verify retained limitations and follow-up draft reference back to exact decision.

## A4: CLI and HTTP adapters

Files: codex/atlas_intake.py, research_cli.py, atlas_http.py, research_viewer.py; test_atlas_adapters.py.
CLI `research atlas-import ROOT FILE --expected-head HEAD --command-id ID --json` and `--preview`. Public apply remains available for review/decision/question.
HTTP preview `{content_base64}`; import `{content_base64,sha256,filename,expected_head,command_id}`; review/decision/question accept their domain payload excluding producer_id plus expected_head/command_id. Producer is coordinator, not fabricated user/agent. Return `{head_id,record_id}` for mutations, parsed QA for preview.

- [x] Write HTTP server tests for preview/no mutation, import/display, malformed requests, same-origin denial, unsupported methods, 10 MiB decoded limit, replay and HEAD conflict.
- [x] Observe 405/missing CLI action failures.
- [x] Add only `/api/atlas/{preview,import,review,decision,question}` POST routes. Exact JSON and body-size checks, content-type requirement, no path reads. Other routes remain read-only.
- [x] Implement bounded CLI file read and shared helpers. Run adapter and existing viewer tests.

## A5: UI and update loop

Files: research_ui/atlas.js, app.js, styles.css, static allowlist; JS DOM tests.
Panel receives current view and refresh callback. Read external arrays as optional for backward compatibility; historical HEAD disables mutation. Preserve preview/form state during live updates.

- [x] DOM tests cover preview→import calls, invalid file/errors, historical disabled mutations, evidence→review→decision navigation, draft copy and version warning.
- [x] Implement file selector and persistent preview, usage/decision/question forms using safe text nodes and existing tokens. No local-path link browsing and no fake host execution controls.
- [x] Show actual councils bound to selected review using existing renderer; coordinator-only decisions clearly identified.
- [x] Run existing UI tests and adapter tests. Launch server and verify widths 1440/768/390 and dark/light plus keyboard/long text.

## Review and delivery

- [x] Review parser task against schema and actual QA.
- [x] Review core policies and references against spec; fix material findings.
- [x] Review UI against actual API and privacy/history behavior; fix material findings.
- [x] Run combined relevant tests once fixes land. Document actual tests and browser verification.
- [x] Import the current real QA once via public adapter into current research project. Preserve native gates/approvals/issues. Register genuine coordinator use/decision and label past collaboration transcripts as external records if displayed; do not fake a new council.
- [x] Preserve source byte/version binding, update research status and provide UI link. Commit only feature and its explicit documentation/tests, no unrelated research changes.
