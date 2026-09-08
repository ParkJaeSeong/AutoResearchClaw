# Task 07 — literature approval and extraction integrity

Implemented against base `386cdd77b0575397331547eed367f15a3c4f37a2` in the existing isolated M1 worktree. Scope is Task 07; packet/project integration was explicitly authorized by the coordinator. No legacy validator, lifecycle, store implementation, dependency, general advancement, council, UI, or later-task engine changes. No subagents, external source retrieval, actual research approval, push, or merge.

## Verification and TDD

- Initial RED: `.venv/bin/python -m pytest tests/codex_native/m1/test_literature.py tests/codex_native/m1/test_approvals.py -q` — **31 failed**, with explicit missing-implementation assertions before production modules existed.
- Initial integration exposed the actual legacy limitation behavior: empty limitations were accepted for abstract claims. M1's explicit non-full-text limitation requirement was implemented around the unchanged legacy adapter. An additional RED demonstrated that changing both a manifest and its claim to full_text bypassed the original access declaration; the M1 adapter now compares manifest access with the approved shortlist.
- Initial CLI fixture invoked the package without a `__main__`; corrected the test invocation to the actual `researchclaw.codex.cli` entrypoint, without changing product behavior. Preserved the existing two-argument `validate_outputs` contract when integration exposed an existing snapshot regression's wrapper; content validation now has a separate adapter.
- First complete integration run: `.venv/bin/python -m pytest tests/codex_native/m1 tests/codex_native/test_knowledge_extraction.py tests/codex_native/test_approval.py tests/codex_native/test_task_packets.py -q` — **336 passed in 22.64s**.
- Self-review RED: modified registered bytes supplied after HEAD verification could previously be approved under their old digest. Added exact-read hash/size verification. Additional REDs showed that boolean approval schema versions and candidate attribution exceeding logged result counts were accepted; both now reject. These failures were observed before their fixes.
- Additional regression coverage checks malformed registered corpus, forged actor, content failures/corrections without publishing artifacts, and historical prepare/register receipt replay after a newer rejection.
- Final scoped command: `.venv/bin/python -m pytest tests/codex_native/m1 tests/codex_native/test_knowledge_extraction.py tests/codex_native/test_approval.py tests/codex_native/test_task_packets.py -q` — **343 passed in 23.30s**, zero failures/skips. Includes **39 Task 07 tests**.
- `git diff --check` and `.venv/bin/python -m compileall -q researchclaw/core/m1 researchclaw/codex/m1_cli.py` — exit 0, no output.
- Full legacy suite deliberately not run: coordinator reported an unrelated SSL hang. The existing relevant knowledge-extraction/approval/task-packet regressions above all ran.
- Self-review checked the brief against the final source: durable decisions preserve all old records, current binding and latest decision gate extraction, current valid artifacts rather than failed drafts form the corpus, registration uses validated snapshots, screen/extract remain review_pending, and helper execution/data attribution stays synthetic/declaration-only. The coordinator separately reported a passing process-level CLI acceptance run; its driver and verification documents are outside this implementation commit and require final coordinator rerun if desired.

## Public and integration APIs

- `validate_literature(node_id: str, files: dict[str, bytes], inputs: dict[str, bytes]) -> tuple[dict, ...]` in `literature.py`. Content-only checks for search/collect/screen/extract; other node IDs have no Task 07 content checks. Malformed/missing relevant contents return `m1_literature_invalid` issues with node_id/message. Existing extraction issues retain `code,path,message`. No filesystem/network access or lifecycle mutation.
- `record_corpus_approval(root: Path, *, corpus_binding: str, decision: str, note: str, command_id: str) -> {receipt, approval}` in `approvals.py`.
- `approval_covers(record: dict, corpus_binding: str) -> bool`: exactly `decision == 'approve'` and exact binding equality. This is intentionally content-only; registration/gates validate the full current record schema and authority declaration.
- `current_corpus(root: Path) -> {corpus_binding, corpus_refs}`: read-only verified HEAD, registered object references, exact byte snapshots, and search/collection/screen validation. Missing corpus raises `m1_corpus_inputs_missing`; invalid content raises `m1_corpus_invalid`; foreign/malformed references raise `m1_input_ref_invalid`; changed snapshotted bytes raise `m1_input_content_changed`.
- Engine helpers `corpus_status(root, head)` add `approval` (latest matching full record or null) and `approved`; `require_corpus_approval(root, head)` returns this or raises `m1_corpus_approval_required`. Malformed matching records raise `m1_approval_record_invalid`.
- `artifacts.validate_outputs(packet, files)` remains the Task 06 structural two-argument API. New `validate_node_contents(packet, files, inputs)` dispatches content validation after structural success. `read_registered_inputs(root, refs)` reads each descriptor-guarded immutable object once and checks the consumed bytes against its registered digest and size.
- `prepare_node` and `register_outputs` retain their Task 06 request/return contracts. Extract input_refs now bind all corpus/context artifacts below. Every new extraction prepare/register checks the latest current approval before any alias submission is accepted. New approval never refreshes a stale packet: a changed input binding still requires a later authorized new attempt.
- `resume_project` adds `corpus`: null outside screen/extract, or `{corpus_binding,corpus_refs,approval,approved}`; invalid/incomplete corpus becomes `{approved:false,error}`. At extract, absent/rejected/invalid approval overrides authoring/review actions with `await_approval`. Status and stored attempts remain unchanged. At screen, approval is visible while `await_review` remains the council gate. Resume uses no lock, write, fsync, normalization, or advancement.

CLI:

```text
researchclaw-codex m1 corpus decide ROOT --binding HASH --decision approve|reject --note TEXT --command-id ID --json
```

Success is one JSON `{receipt,approval}` on stdout. Invalid arguments, stale bindings, and invalid corpus follow existing stderr/exit-2 convention. Blank notes/command IDs and non-hex bindings reject. Approval records and decision event publish in one store commit. Existing prepare/register/resume CLI contracts stay available.

## Corpus binding and approval record schema

The binding is SHA256 of canonical UTF-8 JSON (sorted object keys, compact separators) with:

```json
{
  "schema_version": 1,
  "workflow_version": "m1-graph-v1",
  "project_id": "<current project ID>",
  "objects": [{"id": "<registered artifact ID>", "sha256": "<registered SHA256>"}]
}
```

`objects` sorts by `(id,sha256)` over the latest registered artifact at each of these **eight** paths:

```text
scope/goal.md
scope/constraints.json
scope/questions.json
literature/search_plan.yaml
literature/candidates.jsonl
literature/search_log.jsonl
literature/shortlist.jsonl
literature/screening_decisions.jsonl
```

This conservative approval scope covers search/screening provenance and context as well as selection. Identical bytes registered with a new artifact identity require a new decision. Unrelated HEAD changes, extraction outputs, and decision events do not change this binding. The same unchanged binding reuses its latest decision. `reject` explicitly revokes any earlier approval for that binding. The API does not implement a third `revoke` enum; rejection is the revocation operation.

`state.approvals` is an append-only ordered list of closed records:

```json
{
  "schema_version": 1,
  "workflow_version": "m1-graph-v1",
  "id": "approval-<uuid>",
  "project_id": "<current project ID>",
  "corpus_binding": "<64 lowercase hexadecimal characters>",
  "corpus_refs": ["<complete ArtifactRef objects sorted by id,sha256>"],
  "decision": "approve|reject",
  "note": "<non-empty string>",
  "actor": "user",
  "provenance_status": "declared_only",
  "content_origin": "research|synthetic"
}
```

The actual corpus_refs entries are full artifact objects, not strings: Task 05/06 schema_version, workflow_version, id, logical_path, sha256, size, producer_attempt_id, content_origin, plus any declared checkpoint provenance fields. Matching approvals must have the exact current refs, project ID, integer schema version, workflow version, content origin, non-empty ID/note, permitted decision, user actor and declared_only attribution. Each record is also registered as an immutable JSON object under `approvals/<id>.json`; cumulative event type is `corpus_decided` with the shared `{request,result}` payload.

`actor:user` is a CLI-declared authority attribution, not an authenticated identity or independent execution proof. `provenance_status:declared_only` is used for both synthetic and research user declarations. The host remains responsible for invoking this API only after an actual user decision. Synthetic tests provide declarations exclusively for test materials.

Exact command retries replay original immutable results with Task 06 `_replay` and Task 05 durability semantics, even after a later rejection or changed corpus. They cannot replace later HEAD or constitute current authorization. Historical prepare replay can recreate its draft directory; new registration still checks current corpus/decision. Fresh command IDs with an old binding raise `m1_corpus_binding_changed`. Interrupted pre/post-HEAD decision commits retry without duplicate visible records.

## Content schemas

Search/candidate/screen records are open to additional descriptive metadata. Required fields and relationships below are checked; unknown metadata is data, never executable instruction.

- `literature/search_plan.yaml`: object with non-empty string lists `queries`, `sources`, `inclusion_criteria`, `exclusion_criteria`; safe YAML, JSON-compatible values.
- `literature/search_log.jsonl`: non-empty JSON objects with unique non-empty `search_id`, `query` present in plan.queries, `source` present in plan.sources, ISO timestamp `searched_at`, and nonnegative integer `result_count`. Attributed distinct candidates cannot exceed a log's result_count.
- `literature/candidates.jsonl`: non-empty objects with unique non-empty `source_id`, non-empty `title`, at least one non-empty `doi`, `arxiv_id`, or `url`, `access_status` in `full_text|abstract|metadata_only|unavailable`, and non-empty `search_ids` list resolving to search_log entries. Optional `source_type` is preserved.
- `literature/screening_decisions.jsonl`: every candidate exactly once, with non-empty `source_id`, `decision` in `include|exclude`, non-empty `reason`. Uncertainty is retained in descriptive reasons/metadata rather than an invented decision enum.
- `literature/shortlist.jsonl`: every candidate exactly once, preserving its `title,doi,arxiv_id,url,source_type,access_status,search_ids`, and matching its screening `decision,reason`. Calls unchanged `validate_extraction_shortlist(shortlist_text: str)` to require the existing source/selection contract, including at least one included source before extraction can be approved.
- `knowledge/extractions.jsonl` and `knowledge/extraction_manifest.json`: call unchanged `validate_knowledge_extraction(shortlist_text, claims_text, manifest_text, project_id)`. Trusted `inputs['project.json']` contains `{"project_id":"<actual project ID>"}` and is generated in memory by registration, never accepted as an output. Strict JSON parsing supplements legacy parsing. Manifest project identity comes from project state, never its own self-declaration.

Extraction claim closed allowed fields (legacy contract): `claim_id,source_id,claim,evidence_summary,evidence_level,locator,source_url,applicability,limitations,doi,arxiv_id,supporting_excerpt,quantitative_details,conflicts_with`. Required strings are claim_id/source_id/claim/evidence_summary/evidence_level/locator/source_url; applicability is a non-empty string list, limitations a string list. Optional quantitative_details is closed `{value,unit,condition}`; conflicts_with references other declared claims. Evidence levels are `full_text|abstract|metadata_only`. Unknown/excluded sources, contradicted source identifiers, missing locators, malformed details, repeated claims, forbidden full-source payloads, placeholders, and existing per-source upper limits reject through the unchanged adapter.

Extraction manifest closed shape is `schema_version,project_id,generated_at,sources,summary`. Each sources item has `source_id,decision,access_status,accessed_at,access_url,claim_count,failure_reason`; nullable fields must exist. Summary has `included_sources,processed_sources,claim_count,full_text_sources,abstract_sources,metadata_only_sources,unavailable_sources`, recomputed by the legacy validator. Unavailable sources require zero claims and failure reasons; empty extractions are allowed only when every included source is unavailable. Accessed sources must have timestamps/URLs; claims cannot exceed the manifest's access level. M1 additionally forbids upgrading manifest access above the approved shortlist declaration and requires a non-empty limitations list on non-full-text claims. It cannot judge whether prose truly describes limitations or whether locators/claims match real source text.

Content failures use the existing durable draft correction budget (initial submission plus two corrections); invalid drafts stay out of state.artifacts. Passing extraction remains `review_pending`, with scientific validation `not_performed`. No source access, independent verification, council outcome, research truth, or full graph progress is inferred from content validity.

## Synthetic helper and owned files

`tests/codex_native/m1/helpers.py` exposes:

- `corpus_files()` and `extraction_files(project_id)` for explicit example.org synthetic materials marked `합성 검사 자료`.
- `checkpoint(root, *, node=None, files=None)`: test-only commit_record injection, with synthetic declared_only artifacts/events. The initial checkpoint records scope/questions/search/collect completed attempts explicitly marked as injected declarations, with no council execution claim.
- `corpus_checkpoint(root)`: initializes `content_origin='synthetic'`, injects scope~collect checkpoints, then runs public screen prepare/register to `review_pending`; returns `root,head_id,artifact_refs,corpus_binding,corpus_refs` with no approval.
- `submission(root, packet, files)`: writes only test packet draft paths and creates the Task 06 manifest.
- Required `build_evidence_case(root: Path) -> dict`: obtains the synthetic checkpoint, runs public corpus decision, injects the test-only screen→extract checkpoint (Task 17 owns real advancement), runs public extraction prepare/register, and returns `root,head_id,artifact_refs,corpus_binding` plus corpus_refs. Extract remains review_pending. This is not a full public council/graph acceptance path and supplies no real research quality evidence.

Owned files in this commit:

```text
researchclaw/core/m1/literature.py
researchclaw/core/m1/approvals.py
researchclaw/core/m1/artifacts.py
researchclaw/core/m1/packets.py
researchclaw/core/m1/project.py
researchclaw/codex/m1_cli.py
tests/codex_native/m1/helpers.py
tests/codex_native/m1/test_literature.py
tests/codex_native/m1/test_approvals.py
.superpowers/sdd/2026-09-08-m1-transition/task-07-report.md
```

All material limitations are explicit above: declaration-only authority, deterministic content checks, conservative revision binding, no actual source retrieval/verification, no automatic graph advancement, and no full legacy-suite run. No unresolved implementation blocker remains within Task 07 scope; independent coordinator review and later Task 17 integration remain separate work.
