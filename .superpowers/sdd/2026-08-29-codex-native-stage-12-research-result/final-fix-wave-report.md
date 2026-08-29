# Stage 12 Final Whole-Branch Fix Wave Report

## Status

Complete on `feature/stage12-result-registration`.

- Reviewed base: `d93d7b1`
- Main fix commit: `0d201c42b4d8c650663ed85ce383d459b8bca3f1` (`fix(codex): close stage twelve registration review`)
- Actionable-approval follow-up: `10f2f9f804d155cb87589a8d8d7cd198218040bb` (`fix(codex): make stage twelve approval rewind actionable`)
- Final code verification HEAD: `10f2f9f804d155cb87589a8d8d7cd198218040bb`
- Publication: not performed. No push or merge was attempted.
- Disposable integration only: `/tmp/researchclaw-stage12-final.2eGahC/project`

All seven review findings are closed. The final Codex-native suite passes, the
returned Stage 12 command was executed verbatim in a disposable project, and
the command and registration hash audits both matched their exact write
boundaries.

## Finding-by-finding resolution

### CRITICAL 1 — the returned command could not produce a research result

The fixed Stage 10 `experiment/code/main.py` now has two deliberately separate
paths. `--dry-run` retains the Stage 10 readiness behavior. The exact non-dry
command returned by Stage 12:

```text
python experiment/code/main.py --config experiment/code/config.json
```

runs only outside ResearchClaw and now:

- opens the current canonical execution contract and recomputes its identity;
- requires the exact command, result path, closed result template, and all
  prohibition flags;
- streams and verifies every package binding and required input, including
  size, SHA-256, uniqueness, and license status;
- checks the configured split roles and approved runtime budget;
- runs the fixed bounded package behavior; and
- uses exclusive creation for the single declared
  `experiment/results.json`, with full contract/provenance/runtime binding.

The ResearchClaw preparation and registration paths still contain no
subprocess, package installation, network, LLM, or nested-agent execution.
`prepare-run` only writes the contract and returns the command.

The public README, agent guide, research skill, computational-package and
resource-planning references, authoritative design, plan, and public-doc tests
were updated consistently.

### CRITICAL 2 — pending recovery bypassed strict validation

`_validate_research_result_against_stage_twelve_state` is now the single
side-effect-free strict core used by:

- initial `register_research_result` validation;
- committing pending recovery against the recorded Stage 12 prior state; and
- Stage 13 grounding against a reconstructed canonical Stage 12 state.

It reopens the current approval, Stage 12 artifact identities, resource plan,
contract, package files, required inputs, and result bytes. It then checks the
closed result schema, research/development flags, completion status, project and
contract references, non-empty finite metrics, exact split roles/counts,
zero leakage/overlap, complete provenance, runtime/budget, and current input
identity. Recovery also compares the strict result size/hash/counts to the
pending identity.

If any of those checks drifts after pending persistence, recovery first records
a durable abort intent, restores or retains the canonical Stage 12 state,
repairs/compensates the owned event fragment when necessary, and clears the
pending record. The forged development-only and post-pending input-drift
regressions both prove handoff cannot promote the result.

### IMPORTANT 1 — event flock was not the common mutation transaction

A new common transaction in `researchclaw/core/transactions.py` combines:

- a per-project process `RLock` for threads;
- an fsync-independent project `flock` for processes;
- reentrant ownership for nested state/event operations; and
- a stable `project_transaction_pending` `ValueError` when unrelated work sees
  a durable registration pending file.

The lock is entered before mutation and held through the corresponding event
for project creation, task preparation, stage validation, approval, execution
rechecks, development input/result validation, development execution, research
preparation/registration, durable normalization, state saves, and standard
event appends. Registration and recovery use the same lock with the explicit
pending-recovery capability. `ResearchProject.build_handoff()` may recover a
pending transaction before appending its resume event.

The final tests cover development execution, development-result validation,
direct state persistence, the CLI error boundary, simultaneous thread calls,
and the existing handoff/registration races. All rejected operations leave
state, development result, and event bytes unchanged and produce no traceback.

### IMPORTANT 2 — whole-file reads and unbounded JSON/event memory

The project file boundary now exposes a no-symlink `openat` descriptor helper,
a stable streaming size/SHA-256 identity helper, and a bounded snapshot helper.
Required inputs, approved Stage 12 artifacts, package bindings, results,
contracts, and event-log identities use those primitives as appropriate.

Caps are enforced before JSON decoding or durable writing:

- execution contract: 256 KiB;
- research result: 1 MiB;
- Stage 12 approval: 256 KiB;
- package manifest/resource plan: 1 MiB;
- contract-preparation journal: 4 KiB;
- registration pending record: 256 KiB; and
- individual event record: 64 KiB.

Event records are encoded incrementally and rejected before any oversized
record bytes are written. Event logs and registration prefixes are read one
bounded JSONL record at a time. Duplicate keys, non-finite constants,
incomplete lines, non-regular files, and oversized records fail closed. Stage
13 grounding uses a two-pass constant-memory event scan rather than
`read_all()`. Tests include a 32 MiB sparse input, oversized sparse result and
contract records, a 32 MiB sparse event line, package-binding streaming,
duplicate event keys, and write-side event/pending caps.

### IMPORTANT 3 — Stage 13 advertised unsupported `validate_stage`

Stage 13 grounding now chooses only implemented Stage 12 actions:

- valid result bytes but a missing/stale result reference or registration event
  -> `register_research_result`;
- a missing/stale/invalid contract or unusable result -> `prepare_run`;
- an invalid Stage 12 approval -> `approve_experiment_execution`.

It never emits `validate_stage` at the Stage 12 recovery boundary. The model
contract admits the two new explicit actions and the recovery retry state.
Handoff produces real CLI commands for preparation, registration, or approval.

The tests do more than inspect labels: a stale contract can be prepared again,
a missing result reference can be registered and remain grounded, and an
invalid approval can be renewed and the already bound result registered. The
approval recovery rechecks current resource/input readiness without rewriting
the approved resource artifact, so it does not make an otherwise valid
execution contract stale merely because live hardware observation fields
changed.

### IMPORTANT 4 — prepare-run crash orphan

Contract preparation now writes a bounded durable journal before the canonical
contract. The journal binds project ID, contract ID, contract SHA-256, and
contract size. An unreferenced canonical contract is reusable only when that
journal matches exactly; an attacker-preseeded canonical contract without the
journal remains rejected. Current approval, artifact bindings, package files,
and inputs are rebuilt and validated before any recovery.

A fault injected after contract-file commit but before `ArtifactRef`
persistence leaves the journal and file. The next `prepare-run` reuses the exact
bytes, persists the reference, clears the journal, and returns the same hash.

### MINOR — pending cap was checked only on read

`_persist_pending_registration` now incrementally canonicalizes and enforces
the 256 KiB cap before calling the atomic writer. The oversized-valid-state
regression proves no pending file or partial state transition is left behind.

## TDD evidence

### Initial RED wave

The initial review regression file was run before implementation:

```bash
pytest -q tests/codex_native/test_stage12_final_fix_wave.py
```

Initial result:

```text
15 failed
```

Representative failures matched the review report:

- the exact returned command exited in the old
  `RuntimeError('execution is deferred to stage 12')` path and created no JSON
  result;
- forged development-only and input-drift pending registrations advanced to
  Stage 13 instead of compensating to Stage 12;
- unrelated development/state mutation was not protected by one transaction
  boundary or surfaced the old runtime-only conflict;
- oversized result/contract records reached decoding paths and event/pending
  paths lacked write-side caps;
- Stage 13 rewinds returned `validate_stage`;
- an interrupted contract commit was rejected as an attacker preseed; and
- an oversized valid pending payload could be written before later rejection.

Focused RED reproductions during self-review found and fixed four additional
cross-boundary cases:

```text
test_resume_handoff_recovers_pending_before_appending_resume_event
  ValueError: project_transaction_pending

test_duplicate_key_event_is_rejected_before_registration_mutates_state
  expected current_stage 12, observed 13

test_stage_thirteen_grounding_streams_event_log_without_read_all
  AssertionError: Stage-13 grounding loaded the complete event log

test_stage_thirteen_invalid_approval_rewind_can_reapprove_and_register
  first: refreshed resource plan ... preexisting_result
  second iteration: execution_contract_stale
```

These produced one lock-capability fix, strict streaming JSON event parsing,
constant-memory Stage 13 grounding, and an actionable approval-recovery path.

### GREEN evidence

Final review regression file:

```bash
pytest -q tests/codex_native/test_stage12_final_fix_wave.py
```

```text
27 passed in 2.98s
```

Focused final approval/execution/handoff/recovery set:

```bash
pytest -q tests/codex_native/test_stage12_final_fix_wave.py \
  tests/codex_native/test_execution_gate.py \
  tests/codex_native/test_approval.py \
  tests/codex_native/test_handoff.py \
  tests/codex_native/test_research_execution.py
```

```text
246 passed in 21.97s
```

The broader computational/CLI/development/state/document group also passed:

```text
367 passed in 18.94s
```

Final whole suite at final code HEAD `10f2f9f`:

```bash
pytest -q tests/codex_native
```

```text
853 passed in 42.94s
```

## Disposable exact-command integration and hash audit

Fixture:

```text
root:       /tmp/researchclaw-stage12-final.2eGahC/project
project_id: rc-bc41d4958f58
initial:    Stage 12, ready, report_resource_plan_milestone_only
```

Actual preparation command:

```bash
PYTHONPATH=. /opt/homebrew/opt/python@3.11/bin/python3.11 \
  -m researchclaw.codex.cli execution prepare-run \
  /tmp/researchclaw-stage12-final.2eGahC/project --json
```

Preparation returned:

```text
readiness:       ready_for_explicit_execution
command:         python experiment/code/main.py --config experiment/code/config.json
contract_sha256: 535d413f27ceec03c94b9addf19a63e6c3aed168bd20c86ff3625bc81d4661eb
input_count:     1
```

The returned string was compared byte-for-byte to the required command, then
executed verbatim from the project root with a disposable `python` shim pointing
to Python 3.11:

```bash
python experiment/code/main.py --config experiment/code/config.json
```

Execution result:

```text
exit:             0
stdout:           <empty>
changed paths:    ["./experiment/results.json"]
only result:      true
result size:      2204 bytes
result sha256:    347e1e032e7b65f12c7b723786e25f39e92bfef2c2e90771cb8c61ddaccf91d6
contract_id:      f4a20a3b711a161d4780a410d47ca724250d64fc7184cfd760d1932878a6c1b5
status:           completed
development_only: false
evidence_eligible: true
metric_count:     1
input_count:      1
```

Actual registration command:

```bash
PYTHONPATH=. /opt/homebrew/opt/python@3.11/bin/python3.11 \
  -m researchclaw.codex.cli execution register-result \
  /tmp/researchclaw-stage12-final.2eGahC/project \
  --result experiment/results.json --confirm-research-result --json
```

Registration returned:

```text
readiness:    research_result_registered
current_stage: 13
next_action:  prepare_stage
result_sha256: 347e1e032e7b65f12c7b723786e25f39e92bfef2c2e90771cb8c61ddaccf91d6
```

The post-registration status was Stage 13 `ready`, with stages 1–12 complete,
`execution_readiness: null`, and `approval_eligible: false`.

Registration hash audit:

```text
changed paths:
  ./.researchclaw/state.json
  ./evaluation/events.jsonl

byte-identical before/after registration:
  approvals/stage-12.json
  data/input.csv
  experiment/design.json
  experiment/package_manifest.json
  experiment/code/main.py
  experiment/code/config.json
  experiment/resources.json
  experiment/execution_contract.json
  experiment/results.json
```

Both audit predicates were `true`: the external runner changed only the
declared result, and registration changed only durable state plus the
append-only event log.

## Final static verification

```bash
git diff --name-only d93d7b1..HEAD -- '*.py' \
  | xargs /opt/homebrew/opt/python@3.11/bin/python3.11 -m py_compile
git diff --check d93d7b1..HEAD
ruff check <all changed Python files>
```

All three commands exited `0` with no output. The working tree was clean before
this report was added.

## Self-review

- Confirmed ResearchClaw itself never invokes the returned command; only the
  disposable integration and tests used `subprocess`.
- Confirmed the generated runner imports only standard-library modules and has
  no network, download, package-installation, LLM, or agent capability.
- Confirmed all result validation paths use the same strict core and recovery
  cannot promote a development-only result or an input-drifted result.
- Confirmed common-lock nesting permits only registration/handoff recovery to
  cross an existing pending marker; ordinary mutations receive the stable
  `project_transaction_pending` category before writes.
- Confirmed success, rollback, and failure records stay bounded and contain
  identities/counts rather than untrusted metrics, source data, stdout, or
  stderr.
- Confirmed Stage 13 remains an implementation boundary; no refinement
  algorithm or claim of Stage 13 completion was added.
- Confirmed no unrelated user files were changed and no push/merge occurred.

## Concerns / operational notes

No release-blocking concern remains in the tested Stage 12 scope.

The runner intentionally uses exclusive result creation. It never overwrites a
preexisting `experiment/results.json`; if an operator is explicitly rerunning
after a stale/corrupt result recovery, that unregistered file must first be
archived or removed by the operator. This preserves the requested non-
destructive ResearchClaw boundary and prevents silent evidence replacement.

The disposable integration directory was retained under `/tmp` so its hashes
and exact output can be inspected; it is not part of the repository or any user
battery project.
