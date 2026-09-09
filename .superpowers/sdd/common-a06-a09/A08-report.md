# A08 implementation report

Base: 0d1be24 (A07 approved). Scope: dependencies.py, focused test_dependencies.py,
dependency-inputs.md, and this report. No commands, shared policy files, CLI/UI,
prerequisite producers or approval authority were changed.

Implemented pure `plan_revalidation` over verified policy history/bytes. Canonical
full SnapshotRef strings are validated before grouping nodes by project/artifact/
digest. Historical analysis versions remain usable as impact seeds; later-head
references to the same immutable version remain connected. Fixed from-input to
dependent-output direction applies to all four relations. All components receive
cycle/reference checks. Result includes changed seeds and descendants, current
unaffected reuse, backed approval checks including scope-only impact, and an
explicit uncommitted needs_revalidation event descriptor. It never overwrites
old objects, approval validity, issue states or HEAD.

Typed UUID endpoints resolve their actual historical registered collection even
when immutable object aliases are namespaced. Receipt checks follow A07's closed
existing-authority adapter, using a tiny historical-scope adapter because the
gate helper intentionally refuses historical scopes/nonvalid statuses. Invalid
authority status cannot enter reusable_refs even via a generic DAG-node path.

TDD evidence:

- Initial focused RED: 24 failed (0.65s), all missing dependencies module; fixture
  creation and contract assertions succeeded.
- First focused GREEN: 24 passed (0.57s).
- Additional direct-approval and revoked-DAG-node regressions: 2 failed,
  24 passed (0.54s); fixes then gave 26 passed (0.53s).
- Final focused command:
  `.venv/bin/python -m pytest tests/codex_native/research_graph/test_dependencies.py -q`
  gave 34 passed (0.61s). Additional checks cover malformed maps, rejected/unbacked
  receipts, unknown endpoints, digest corruption and equal bytes under different
  artifact IDs. Successful and rejected calls assert snapshot, HEAD and every
  prior object byte are preserved.

No broad suite, actual research/host/CLI/UI, event producer, external side effect,
or approval authentication ran. Parent owns independent review and acceptance;
synthetic fixture validation is not actual research acceptance. `git diff --check`
is required immediately before this report's commit.
