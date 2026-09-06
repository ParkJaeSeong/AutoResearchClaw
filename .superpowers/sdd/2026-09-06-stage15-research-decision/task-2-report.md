# Task 2 Report: Stage 15 Research Decision Records

## Outcome

Implemented the ordered Stage 15 decision-record workflow and deterministic
decision report. The local implementation validates and registers already
authored review, response, and result records; it does not make a scientific
judgment, call an external model/API, execute a follow-up, or provide rollback
or re-deliberation.

Public APIs now cover:

- `register_decision_review(project, submission_path)`
- `register_decision_rebuttals(project, submission_path)`
- `register_decision_result(project, submission_path)`
- `render_decision_report(payload)`
- CLI `decision register-review`, `register-rebuttals`, and `register-result`
  commands with `--submission PATH --json`

## TDD record

The first production boundary was added only after a focused RED run. The
four terminal-outcome cases reached a valid, fully analyzed Stage 15 project
and then failed at the intended missing API:

```text
AttributeError: module 'researchclaw.core.research_decision'
has no attribute 'register_decision_review'
4 failed
```

After the minimal registration and state-transition implementation, those
same four cases passed. Additional tests then drove closed-schema validation,
ordered role/rebuttal/result registration, claimed-consent verification,
canonical publication, deterministic reports, exact replay, historical
revalidation, and interruption recovery.

## Behavior and safety coverage

- Registers the three required roles in fixed order while enforcing the exact
  role set, distinct producers, packet digest, packet-input citations, and
  closed nested/top-level schemas.
- Registers one response per original role with exact producer and review hash
  bindings; the coordinator must be distinct from every reviewer.
- Rejects a non-null coordinator result unless every recorded final role
  recommendation matches it. No majority, score, metric threshold, or inferred
  scientific consensus is computed.
- Applies all four literal terminal outcomes: PROCEED advances to Stage 16 and
  completes Stage 15; REFINE/PIVOT stay at Stage 15 with their authored target;
  null/unresolved stays at Stage 15 and requests direction. None executes the
  requested follow-up or creates `paper/outline.md`.
- Preserves execution policy, retry budgets, Stage 10 snapshot, and every
  pre-existing registered artifact byte across decision registration.
- Publishes canonical immutable JSON and a deterministic Markdown report. The
  report preserves coordinator rationale/scope/follow-up, original independent
  role records, actual role responses, unresolved issues, Stage 14
  scope/limitations, and source context with paths linked relative to
  `analysis/decision.md`.
- Rejects unregistered partial records in status. Exact orphan retries adopt
  review, rebuttal, result, and report bytes; conflicting retries preserve and
  reject those bytes. An interrupted report publication cannot advance state.
- Exact terminal retries do not save state or append Stage 15 twice. Stage 16
  preparation is verification/exact replay only, and real post-PROCEED status
  revalidates the retained Stage 14 history.
- The Task 1 `prepare_analysis` missing-file behavior was not changed; no
  historical artifact recreation path was added.

## Verification

Development and affected-file verification used ephemeral `uv` dependencies
and four pytest workers, as requested:

```text
uv run --with pytest --with pytest-xdist pytest -n 4 \
  tests/codex_native/test_research_decision.py -q
47 passed in 37.04s

uv run --with pytest --with pytest-xdist pytest -n 4 \
  tests/codex_native/test_research_decision.py \
  tests/codex_native/test_result_analysis.py -q
80 passed in 90.49s
```

That final passing test gate used uv's CPython 3.13.14 ephemeral environment.
The repository-wide suite was intentionally not run, per the task scope.

Ruff ran with the same exact project-tooling form as Task 1:

```text
uv run --no-project --python /opt/homebrew/bin/python3.11 --with '.[dev]' \
  ruff check researchclaw/core/research_decision.py \
  researchclaw/core/decision_report.py researchclaw/core/models.py \
  researchclaw/codex/cli.py tests/codex_native/test_research_decision.py
```

Result: exit 0 with no diagnostics. `git diff --check` also exited 0 with no
diagnostics immediately before staging.

## Integration dependency and concerns

`researchclaw/core/models.py` receives only the three closed terminal
`next_action` literals required to reopen the persisted Task 2 state:
`unsupported_stage_16`, `report_research_follow_up`, and
`request_research_direction`. This is outside the primary Task 2 file list but
is an exact state-deserialization dependency, not a generic routing or schema
expansion. Task 3 remains responsible for root routing, handoff, and skill
documentation.

No Task 2 defect remains known. A separate Python 3.11 xdist repetition of the
affected tests produced one existing refinement self-test environment-
fingerprint failure after 79 passes; rerunning that exact existing node in
isolation passed (`1 passed in 23.39s`). No unrelated refinement code was
changed in response. The completed Task 2 gate above remains the fresh
all-green affected-file run.

No main-branch merge, push, installation, live-project mutation, acceptance
workspace modification, or external service call was performed.

## Commit

Requested commit subject: `feat: register agent research decisions`
