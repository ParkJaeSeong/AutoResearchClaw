# Task 5B implementation report

## Status

GREEN. Stage 13 Task 5B is implemented without Task 6 finalization, Stage 14
handoff, model calls, API calls, or candidate execution inside preparation.

## RED / GREEN record

The pre-change compatibility baseline was:

```text
/opt/homebrew/bin/python3.11 -m pytest tests/codex_native/test_refinement_execution.py tests/codex_native/test_execution_environment.py tests/codex_native/test_evidence_registration.py tests/codex_native/test_evidence_store.py -q
214 passed in 402.08s (0:06:42)
```

The implementation was developed test-first in bounded slices. Observed RED
states included missing `prepare_refinement_run` and
`register_refinement_result` imports, reservation idempotency incorrectly
changing counter authority, non-finite metrics escaping the result-specific
error boundary, exact-byte contract and evidence replacements surviving
reload, and two unclosed recovery windows: registration intent bytes written
before their state ref and a completed receipt written before final state
publication. Each RED was reproduced by a focused pytest node or selector
before the corresponding implementation change. The final focused selector
before the two additional state-publication cases was:

```text
/opt/homebrew/bin/python3.11 -m pytest tests/codex_native/test_refinement_execution.py -k 'prepare_refinement_run or register_refinement_result' -q
24 passed, 67 deselected in 165.39s (0:02:45)
```

The two additional recovery tests each passed after their implementations,
and the three unknown/symlink/hardlink reservation-record cases passed
together. The malformed UTC result timestamp case also passed after its RED
error-category correction.

## Implementation

- Added an exclusive, monotonic, write-ahead run reservation namespace at
  `.researchclaw/refinement-runs/<session>/`, with descriptor-anchored reads
  and writes, durable file and directory fsync, closed inventories, embedded
  filesystem identities, and exact intent-only/contract-only recovery.
- Added `prepare_refinement_run`, which fully revalidates candidate, Task 5A
  intent/preparation/report/receipt, package, environment/launcher, council,
  evidence packet, baseline, inputs, and envelope authority before reserving
  a slot. It returns an absolute verified launcher argv and candidate cwd but
  never invokes them.
- Added a closed authoritative execution contract binding project, session,
  candidate, run, producer, all candidate/package/self-test/baseline/input
  references and filesystem identities, execution environment and launcher,
  authorized change roots, exact envelope counters/deadline, and the expected
  result contract.
- Added `register_refinement_result`, with closed schema-v1 validation for
  identity, exact execution-contract reference, provenance, finite metrics,
  leakage-free split summary, completed status, and bounded runtime. Metric
  values are never interpreted as scientific selection criteria.
- Published all bound evidence sources as immutable `EvidenceStore` objects
  and the run manifest only below
  `.researchclaw/evidence/refinement-manifests/<session>/<candidate>/<run>.json`.
  Baseline manifests, `experiment/results.json`, and Stage 12 state remain
  unchanged.
- Added write-ahead result-registration intent and immutable receipt records.
  The receipt binds full result/manifest/object filesystem identities. Exact
  retry and every partial publication phase recover without another slot,
  manifest, object, or counter increment; inconsistent partial states fail
  closed.
- Added authoritative session reload reconstruction for reserved-run count and
  completed wall time. Reload re-derives each run from candidate/package/
  environment authority and validates intent, contract, result, manifest,
  every evidence object, receipt, and state references.
- Added the `register_refinement_result` state action and session status for
  pending candidate results and later independent assessment. No final choice
  or handoff behavior was added.

## Files changed

- `researchclaw/core/refinement_execution.py`
- `researchclaw/core/refinement.py`
- `researchclaw/core/models.py` (required state-action whitelist entry)
- `tests/codex_native/test_refinement_execution.py`
- `.superpowers/sdd/2026-09-01-stage13-multi-agent-refinement/task-5b-report.md`

The pre-existing untracked slice brief and progress note in the report
directory were not modified or staged.

## Final verification

```text
/opt/homebrew/bin/python3.11 -m pytest tests/codex_native/test_refinement.py tests/codex_native/test_refinement_execution.py -q
180 passed in 694.69s (0:11:34)
```

```text
/opt/homebrew/bin/python3.11 -m pytest tests/codex_native/test_refinement_execution.py tests/codex_native/test_execution_environment.py tests/codex_native/test_evidence_registration.py tests/codex_native/test_evidence_store.py -q
246 passed in 619.51s (0:10:19)
```

```text
/opt/homebrew/bin/python3.11 -m pytest tests/codex_native/test_research_execution.py tests/codex_native/test_experiment_package_contract.py tests/codex_native/test_stage12_final_fix_wave.py tests/codex_native/test_stage12_trustworthy_evidence_integration.py tests/codex_native/test_stage12_release_script.py -q
320 passed in 400.00s (0:06:40)
```

```text
/opt/homebrew/bin/python3.11 -m ruff check researchclaw/core/models.py researchclaw/core/refinement.py researchclaw/core/refinement_execution.py tests/codex_native/test_refinement_execution.py
PASS

/opt/homebrew/bin/python3.11 -m compileall -q researchclaw tests/codex_native/test_refinement_execution.py
PASS

git diff --check
PASS
```

## Self-review

- Preparation contains no subprocess, shell, model, network, or API call.
- A durable run intent is the slot authority; no code path deletes or silently
  reuses it.
- Result acceptance validates procedure, provenance, split integrity, and
  budgets only; the negative-metric happy path still advances to independent
  assessment.
- The baseline evidence manifest namespace and Stage 12 result are unchanged
  in both tests and implementation.
- Exact-byte replacement checks cover candidate/input/contract before result
  registration and result/manifest/evidence object after registration.
- Recovery accepts only internally consistent phase sets; partial or mixed
  state refs fail closed.
- Scope stops at `register_refinement_assessment`; Task 6 final selection and
  Stage 14 handoff are absent.

## Concerns

None known. `researchclaw/core/models.py` was necessarily changed even though
the slice's state-interface note named `refinement.py`, because persisted
project state rejects any next action not present in the central whitelist.
