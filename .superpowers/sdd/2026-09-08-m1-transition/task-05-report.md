# Task 05 — M1 durable store, project lifecycle, CLI

Implemented in the assigned worktree from base `f68d2637bae1ef02e95a83f35ce42d8c14412684`. Scope is the new M1 store/project/CLI, small existing CLI parser/dispatch wiring, and their tests. No legacy lifecycle/product refactor, UI, network, LLM, approvals, migration, or later-task implementation.

## Behavior and consumer contract

- `init_project(root, *, topic, profile, max_returns, content_origin='research')` creates only a new project or reopens one with identical original configuration. `content_origin` is `research` or `synthetic`; the optional argument and CLI flag implement the parent ruling. Initial state: `schema_version=1`, `workflow_version='m1-graph-v1'`, generated `project_id`, `topic`, `profile`, `max_returns`, `content_origin`, `returns_used=0`, `current_node_id='scope'`, `attempts=[]`. No approval or completed work is invented.
- `read_head(root)` is strictly read-only: no lock acquisition/creation, fsync, repair, or writes. It validates all committed ancestry and all registered object bytes. Missing project is `m1_project_not_found`; corrupt HEAD/history/object data is `m1_store_corrupt`; original root/parent or used metadata/object symlinks are `m1_path_invalid`.
- Public HEAD/commit receipts: `schema_version, workflow_version, id, state, events, objects`. `state` is an extensible JSON dictionary for future graph records. Events are cumulative closed versioned envelopes: `schema_version, workflow_version, type` (nonempty text), `payload` (extensible JSON dictionary). Objects are cumulative `sha256 -> {sha256,size}`; physical object path is `.researchclaw/m1/objects/<sha256>`.
- `commit_record(root, *, expected_head, command_id, state, event, objects)` accepts logical POSIX names mapped to bytes, not source filesystem paths. It retains name-to-hash mapping in each command record. Logical payload identity covers state, event, and named object hashes; it excludes `expected_head`. A matching command in committed ancestry returns its original receipt before stale-HEAD rejection, without moving current HEAD. Changed payload is `m1_command_conflict`; a new command with stale HEAD is `m1_head_conflict`. Orphans are never receipts.
- Commit directories contain complete canonical `record.json` envelopes, content-addressed by their canonical SHA256. Fields are closed/versioned: version fields, parent, command_id, payload_sha256, state, events, objects, object_inputs. HEAD is a closed/versioned id envelope. JSON duplicate keys, nonfinite numbers, malformed versions/envelopes, inconsistent ancestry/events/object registries, and altered bytes are rejected.
- Writes use existing `project_transaction`, checked original paths, exclusive no-follow file creation, fsync, complete commit directory publication, and atomic HEAD replacement. Strict local directory fsync propagates directory-open and fsync failures rather than using the legacy helper that suppresses some errors. Initialization syncs the parent of each created ancestor/ROOT, syncs ROOT after `.researchclaw` creation, stages an entire complete store beneath owned metadata, and publishes `m1/` with one directory rename followed by `.researchclaw` fsync. Directory-creation retries sync the parent even when the directory now exists, covering a prior create that succeeded before its parent fsync failed. Identical mutation retries/reopens sync the current published store and metadata parent to re-establish durability after a previous post-rename fsync failure.
- `researchclaw-codex m1 init ROOT --topic ... --profile materials_ai --max-returns 2 [--content-origin synthetic] --json` and `m1 status ROOT --json` emit one JSON value on stdout. M1 also emits JSON without the optional flag, avoiding the legacy human-output assumptions. Failures are stderr/exit 2. Existing commands retain their behavior.

## Red/green evidence

1. Initial targeted run: **49 failed, 4 passed**, in 0.40 s. Expected behavioral failures were missing store/project APIs and absent M1 command routing; four generic malformed-argument cases already passed. No collection errors.
2. Explicit content-origin test before implementation: **1 failed**, missing project API.
3. First implemented targeted run: **54 passed**, in 0.69 s.
4. Deterministic race regression: **1 failed, 5 passed**, in 0.09 s. Failure reproduced an initializer seeing M1 absent, another initializer publishing, and the first rejecting that valid store as nonempty. The fix recognizes valid concurrent publication during preflight and compares configuration under the transaction lock. Five additional malformed HEAD envelope cases confirmed existing checks.
5. Requested combined command:

   `PATH="$PWD/.venv/bin:$PATH" .venv/bin/python -m pytest tests/codex_native/m1/test_store.py tests/codex_native/m1/test_project.py tests/codex_native/m1/test_m1_cli.py tests/codex_native/test_project.py tests/codex_native/test_state.py tests/codex_native/test_cli.py -q`

   **215 passed**, in **87.17 s**, zero failed/skipped: 60 then-current M1 tests and 155 requested legacy regressions.
6. Post-publication durability regression run: **2 failed**, in 0.09 s. Both correctly failed because a same-command retry/identical init reopen returned success while the relevant directory fsync still failed. Added directory syncing on mutation replay/reopen; no HEAD changes or read-only changes.
7. Ancestor/ROOT/metadata creation-durability audit added three regressions: **3 failed**, in 0.06 s, because retry skipped the failed parent sync for a directory that now existed. The fix re-syncs that existing directory parent before creating descendants.
8. Final focused command:

   `.venv/bin/python -m pytest tests/codex_native/m1/test_store.py tests/codex_native/m1/test_project.py tests/codex_native/m1/test_m1_cli.py -q`

   **65 passed**, in **0.73 s**, zero failed/skipped. No broad legacy repeat after the isolated M1 durability fix, per parent instruction.
9. `git diff --check` and `python -m compileall` passed. Ruff could not run: `.venv/bin/python -m ruff` reports `No module named ruff`; no dependency was installed.

## Edge cases and acceptance

Tests cover empty/nested/relative roots; preservation/rejection of legacy and nonempty roots; same/conflicting reopen; explicit synthetic origin; malformed input without writes; original root/parent symlinks including `link/../other`; metadata and object symlinks; altered HEAD/current commit/ancestor/object; cumulative event/object retention; stale writes and matching/conflicting idempotent retries; unpublished commit handling; injected failures before/after commit HEAD and whole-store initialization publication; ENOSPC at write/file-fsync/directory-fsync/directory-open boundaries; durability retry failures after HEAD/init publication; and failed parent-sync retry at a newly created ancestor, ROOT, and `.researchclaw` boundary.

Actual spawned-process tests cover simultaneous identical initializers and both same-command and different-command writers. A deterministic interleaving additionally covers the pre-lock init race. Crash tests inject exceptions at filesystem publication boundaries; they do not simulate a physical power cut.

Parent separately executed `.superpowers/sdd/2026-09-08-m1-transition/task-05-acceptance.py` and reported PASS: explicit synthetic init, a separate CLI status process with identical receipt, unchanged byte/mtime/mode snapshot, object/event registration, same-command retry using old expected HEAD, and preserved prior commit. This synthetic acceptance is not research approval or independent research-role evidence.

## Limits / next consumers

- Read validation traverses full ancestry and objects; cumulative snapshots intentionally favor simple integrity checks over large-history performance. No scale benchmark or garbage collection is introduced.
- Unpublished temporary/orphan artifacts may remain after failures; status ignores them and no automatic deletion/repair runs. Only HEAD-linked history is authoritative.
- Atomic rename/fsync guarantees rely on the local filesystem's semantics. Directory fsync errors are surfaced. Checks reject existing symlink substitutions but do not claim authentication or complete defense against a malicious owner racing filesystem operations.
- The low-level store deliberately validates JSON/envelope/storage integrity, not future NodeAttempt/approval/council semantics. Future engines own those domain contracts and may extend state; the documented receipt/event/object format is ready for them.
- A complete legacy suite was not rerun; only the three assigned legacy files were run. Ruff was unavailable as stated above.
