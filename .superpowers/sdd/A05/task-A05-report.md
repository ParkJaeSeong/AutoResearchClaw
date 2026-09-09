# A05 implementation report

## Scope delivered

- Added pure `prepare_verification(snapshot, payload)` and
  `register_verification_result(snapshot, payload)` transition planners.
- Registered `verification.prepare` and `verification.result` with the sole
  mutation dispatcher and reused A04's trusted ancestry/object context.
- Froze issue, owner, budget, input, observation, acceptance, and exact
  Verification revision bindings before accepting a result.
- Preserved `supported`, `refuted`, `inconclusive`, and `failed` separately.
  Registration never writes issue events or issue status.
- Added the closed payload and outcome rules to
  `docs/superpowers/specs/research-governance/verification-inputs.md`.

## Contract decisions

- `verification.prepare` accepts exactly `{verification: Verification}`.
  Issue IDs must be nonempty and unique; every issue has the same resolution
  condition as the nonempty acceptance rule. The active owner must have role
  `owner`, and its actor must match the producer.
- `verification.result` accepts exactly
  `{verification_ref: SnapshotRef, result: VerificationResult}`. The typed ref
  names the exact current prepared bytes. All prepared dependencies are
  revalidated at result time, including owner role/producer identity.
- Supported/refuted outcomes require referenced output and checked scope that
  includes the frozen acceptance rule. Failed/inconclusive may have no output
  and no completed scope, but require an explicit limitation.
- Existing assignments, budgets, issues, inputs, and outputs are prerequisites.
  A05 adds no producer, execution path, automatic resolution, CLI, or UI.

## TDD record

RED 1:

```text
.venv/bin/python -m pytest tests/codex_native/research_graph/test_verification.py -q
18 failed: every case reached commands.apply_command and failed with
unknown_operation because A05 handlers were absent.
```

GREEN 1:

```text
.venv/bin/python -m pytest tests/codex_native/research_graph/test_verification.py -q
18 passed in 0.85s
```

RED 2, after the exact-current dependency review:

```text
.venv/bin/python -m pytest tests/codex_native/research_graph/test_verification.py -q
2 failed, 24 passed: stale prepared input and changed owner role were accepted.
```

GREEN 2:

```text
.venv/bin/python -m pytest tests/codex_native/research_graph/test_verification.py -q
26 passed in 1.34s
```

Focused affected checks (run before the root reserved final suite):

```text
.venv/bin/python -m pytest -q \
  tests/codex_native/research_graph/test_store.py::test_commands_registry_replay_and_unknown \
  tests/codex_native/research_graph/test_store.py::test_dispatch_replay_after_new_head_does_not_invoke_handler \
  tests/codex_native/research_graph/test_issues.py::test_resolution_and_new_conflict_reopen_preserve_referenced_bytes \
  tests/codex_native/research_graph/test_issues.py::test_checking_rejects_acceptance_rule_not_bound_to_issue
4 passed in 0.24s
```

## Acceptance evidence

- Native integration: create through `issue.event`, prepare through the new API,
  enter checking through `issue.event`, register supported through the new API,
  then resolve through an independent resolver event.
- Negative outcomes: failed and inconclusive remain registered while resolution
  is rejected and the native issue remains checking.
- Mutation safety: rejected fake, foreign, stale, replacement, missing-rule,
  missing-evidence, and missing-limitation cases preserve HEAD.
- Immutability: accepted mutations preserve bytes for previously referenced
  objects. Command replay and stale-HEAD behavior use the real dispatcher.
- Pure functions reject bare snapshots and perform no filesystem I/O when given
  trusted in-memory context. Payloads cannot inject private context.

## Limitations and review boundary

The tests use synthetic content and verify graph structure, reference binding,
atomic mutation, and policy composition. They do not perform source comparison,
calculation, an experiment, human review, host authentication, or browser/runtime
acceptance. No new assignment, budget, input, or output registration API exists.
The root agent owns the independent diff review, final affected suite, and status
or acceptance-board updates.
