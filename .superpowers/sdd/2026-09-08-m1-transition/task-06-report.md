# Task 06 — packets, registration, and read-only resume

Implemented against base `1ba7678fef588360c61af63c3a438b3e106b63d7` in the existing isolated M1 worktree. Scope is Task 06 only. No store.py, legacy lifecycle, role catalog, UI, council engine, or later-task engine edits.

## Verification

- Initial red: 16 packet/artifact tests failed with explicit missing-implementation assertions before production modules existed.
- CLI red: 2 actual `researchclaw-codex` subprocess tests failed because `m1 node` was not a parser command.
- Further red/green regressions: unregistered input object references and obsolete packet versions were accepted by early implementation; dedicated failing tests preceded their fixes.
- Final: `.venv/bin/python -m pytest tests/codex_native/m1 tests/codex_native/test_task_packets.py -q` — **163 passed**, no failures or skips (2.72 seconds). Includes 32 new Task 06 tests.
- `git diff --check` passed.
- Crash tests inject failure before HEAD publication and after HEAD publication for both prepare and register. Retry preserves one visible attempt and one validation record. Process-level CLI tests verify fresh-process receipt replay after draft deletion. Tests also cover later-HEAD preservation, exact request conflicts, safe descriptor reads, parent/file symlinks, changed bytes, registration from the validated byte snapshot, stale node/packet/input bindings, strict JSON/JSONL and safe YAML, correction limits, and read-only resume.
- Existing full legacy suite intentionally not run (known unrelated SSL hang; scoped regression requested).

## Consumer contracts

`prepare_node(root, node_id, *, command_id) -> {receipt, packet, attempt}`. Receipt is unchanged Task 05 shape. Packet has `id`, `packet_version=1`, attempt/node IDs, input objects and configuration, input binding, allowlist and required outputs, role catalog, tool scope, work directory, structural/independent/council requirements, correction limit, and content origin. Packets are in `state.packets[packet_id]` and also registered as immutable JSON objects. Attempts use the master's required NodeAttempt fields plus packet ID and validation history.

`register_outputs(root, *, packet_id, submission, command_id) -> {receipt, packet_id, attempt_id, status, issues, artifacts}` lives in `packets.py`. `validate_outputs(packet, files)` and `validate_declared_contents(packet, files)` live in `artifacts.py` and return tuples of structural issues.

Closed submission v1 (no additional keys at either envelope level):

```json
{
  "schema_version": 1,
  "files": {
    "scope/goal.md": {
      "path": "m1/work/<attempt_id>/scope/goal.md",
      "sha256": "<64 lowercase hexadecimal characters>",
      "size": 123
    }
  }
}
```

All logical names must belong to the persisted packet allowlist; every path must exactly equal `<packet.work_dir>/<logical_name>`. Missing required logical files are structural failures. Paths must never point into `.researchclaw`. Caller-supplied packet replacements are not an API input. Each draft is read once through parent-relative no-follow directory/file descriptors, must be a regular single-link file, and must match declared hash and size. The validated byte snapshot is the object payload used at commit; mutable drafts are never reread for registration.

`resume_project(root) -> {schema_version, workflow_version, head_id, current_node_id, status, action, wait_reasons, inputs, current_attempt, content_origin}`. Actions include `prepare_node`, `write_outputs`, `correct_outputs`, `await_review`, `await_user`, `supply_inputs`, `await_engine`, and `await_approval`. This call validates HEAD/history/objects but takes no lock and makes no write or fsync.

CLI:

```text
researchclaw-codex m1 node prepare ROOT --node scope --command-id ID --json
researchclaw-codex m1 node register ROOT --packet ID --submission PATH --command-id ID --json
researchclaw-codex m1 resume ROOT --json
```

Successful CLI calls emit one JSON value on stdout. Structural failure is durably recorded and returned by the Python API. CLI surfaces it on stderr with `m1_output_validation_failed` plus the JSON result and exits 2, leaving stdout empty. Other rejection errors use the established stderr/exit-2 convention.

## Rulings and limits

- No Task 05 store extension was needed. Packet request/result envelopes are in cumulative event payloads. Replay matches the original request, reconstructs the original commit payload from immutable objects, then calls `commit_record`; this preserves payload checking, durability retry, and later HEAD. Active-draft prepares with a new command ID publish a durable alias receipt without adding an attempt. A same-command historical replay returns its original result even after subsequent commits.
- Input binding hashes sorted artifact ID+SHA pairs, packet version, and topic/profile/content_origin configuration. Node-declared file inputs plus current scope files are consumed. Their hash and size must resolve in this project's verified object registry. Binding excludes unrelated HEAD churn. Changes and obsolete versions cannot silently reuse a draft packet.
- Unsafe or malformed manifests, unsafe filesystem objects, and content/hash mismatches are rejected before structural validation and consume no correction slot or event. Safe distinct structural submissions record immutable submitted draft objects, issues, and validation history atomically. Initial submission plus at most two corrections is allowed; the third invalid submission sets `awaiting_user`. Exact duplicate submission manifests do not consume budget, even with a fresh command ID, and get their own durable alias receipt. `returns_used` is unchanged and budgets never increase automatically.
- All structurally accepted drafts remain `review_pending`; no file-only completion or graph advancement exists. Scientific validation is explicitly `not_performed`. This task creates no approval, agent position, independent-execution claim, council decision, or M2 handoff.
- `review`/`handoff` preparation requires later-task engines and is rejected; `extract` preparation waits for the corpus approval/literature engine. Safe syntax validation exists for all known node output formats, including those later engines will use. Scientific/literature/synthesis/hypothesis semantics remain Tasks 07–09, and upfront councils remain Task 17.
- A pre-publication crash can leave an unreferenced work directory or Task 05 orphan object/commit. Only HEAD ancestry is authoritative; retry cannot create a duplicate visible attempt. Work directories are drafts, not durable completion records.
- This is integrity checking and guarded filesystem access, not authentication against a malicious project owner.

Root coordinator independently ran its separate-process Task 06 acceptance driver successfully on the announced API/CLI contracts. Its acceptance artifacts and broader verification notes are outside this implementation commit's owned files. Separate code review follows this report/commit through the coordinator; no subagents were launched by the implementer.
