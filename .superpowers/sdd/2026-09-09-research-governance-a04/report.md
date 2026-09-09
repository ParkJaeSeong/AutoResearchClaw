# A04 implementation report

Scope: issue lifecycle policy and fixed `issue.event` command registration only.
Implementation base: `12560a6`; independent review and final impacted regression
are pending the parent agent's serial review step.

Changes: pure `propose_issue_event`; immutable Issue and append-only IssueEvent
objects; exact from-status; transfer acceptance/owner/verification binding;
independent evidence-linked resolution; new contradiction reopening; successor
links; imported historical-state preservation. Trusted ancestor/object context
is built only for issue.event inside commands. Existing contract/store/import
implementations and CLI/UI were not changed.

Prerequisite shapes were sent to the parent before coding and frozen in
`docs/superpowers/specs/research-governance/issue-policy-inputs.md`. Missing A05/B02
creation workflows fail closed; fixture registration is test-only. Supported
results are recorded criterion outcomes, not scientific truth or authentication.

Validation:
- Initial RED: `.venv/bin/python -m pytest tests/codex_native/research_graph/test_issues.py -q`
  yielded 13 expected unknown_operation failures before registration existed.
- Additional RED exposed acceptance_rule mismatch and stale transfer acceptance;
  each was fixed and rerun.
- Latest focused GREEN: same command, **25 passed in 1.48s**.
- Coverage: lifecycle, exact predecessor, immutable referenced bytes, rejected
  HEAD preservation, transfer not resolved, unsupported/inconclusive results,
  independent actor, foreign/invented/wrong-issue/stale/incorrect-ancestor refs,
  prior conflict rejection, missing/unbacked/wrong acceptance, supersession,
  pure non-mutating no-I/O plan, caller context rejection, replay/stale HEAD,
  imported historical resolved plus pending-policy preservation and explicit
  assignment on checking.

All new cases are synthetic policy fixtures under temporary roots. No live M1
or imported acceptance project was read or mutated by this implementer. Parent
owns baseline preservation checks, independent review, final impacted regression,
and user acceptance documentation. No claim of whole-plan completion.

## Independent-review correction: repeated old conflict

Reviewer found that a pre-resolution refuted result could be copied with a fresh
id/event_id after resolution and reopen an issue using identical old output refs.
Added public apply_command regressions for both a cloned result with unchanged
refs and a cloned output differing only in envelope identity. Both initially
failed by accepting the transition (RED: 2 failed, 25 passed).

Reopening now requires output content absent from the immutable object set at
the latest resolution ancestor, in addition to result publication ordering.
Known common research-graph envelope metadata is excluded from JSON comparison;
UUIDs and producers alone cannot make evidence fresh. This is deterministic
content comparison, not semantic or scientific novelty detection. Reinterpretation
of old evidence without an explicit future correction contract fails closed.
The positive fixture now records a different observation for a refuted outcome.

Focused validation: `.venv/bin/python -m pytest tests/codex_native/research_graph/test_issues.py -q`
→ **27 passed in 1.81s**. Rejections assert `new_conflict_required` and unchanged
HEAD through the public mutation dispatcher. No broad regression was run here;
parent retains the final impacted-suite step.
