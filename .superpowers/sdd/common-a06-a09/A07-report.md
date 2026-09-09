# A07 implementation report

Base: 093fe68. Scope: pure `assess_gate` plus focused input supplement/tests only.
No command, prerequisite producer, CLI/UI, execution or approval authority added.

Implemented closed backed gate declarations, fixed milestone role perspectives,
actual author/reviewer separation and distinct reviewers, same frozen-input
submissions, A06 rationale/acknowledgement checks, exact source references and
current ApprovalBindings backed by prior scoped existing receipt records.
Issue state comes from native verified commit events, not mutable projections;
imported history stays unchanged and pending. Optional unresolved issues remain
listed. Accepted M1 empirical transfer passes while M2 unresolved integrity blocks.
Revise without scoped criteria requests correction.

Validation: focused RED reached 17 synthetic valid-fixture cases with missing
module failures. Native-history regression was RED before tightening. Final
`.venv/bin/python -m pytest tests/codex_native/research_graph/test_gates.py -q`:
19 passed (4.02s). `git diff --check`: clean. Tests check refusal HEAD stability,
accepted referenced bytes/snapshot preservation, no I/O after verified read,
missing/stale prerequisites, duplicate reviewers, opaque receipts, malformed
Decision, ignored forged state, and A06 missing acknowledgements. Parent requested
no broad predecessor rerun; parent owns integrated regression and independent review.

Limits: structural/sourcing policy over synthetic fixtures only; no actual
research, host independence certification, approval authentication, experiment,
or user acceptance was performed. Existing-authority receipt adapter and other
future prerequisite producers remain absent and therefore fail closed at runtime.

## Independent review correction wave

Confirmed both P2 findings with focused RED (15 failed, 20 passed): acknowledged
required opposition with no scope incorrectly passed a handoff decision; declared
null/list prerequisite collections raised AttributeError in typed-reference helpers.
Required-role opposition now requests `opposition_binding_missing` independently
of the coordinator's next_action. A scoped opposition retains the normal blocking
rule. Explicit collection-shape preflight covers prerequisite maps in current and
historical verified states; malformed maps return `gate_collection_invalid` without
blanket exception handling. Null/list regressions cover approvals/receipts,
assignments, positions/decisions, sessions and issues, and assert HEAD preservation.

Final focused GREEN: `.venv/bin/python -m pytest tests/codex_native/research_graph/test_gates.py -q`
→ 35 passed (7.97s). `git diff --check` clean. No broad tests or scope additions.
