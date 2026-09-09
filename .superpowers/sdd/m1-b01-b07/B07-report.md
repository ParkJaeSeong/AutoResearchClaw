# B07 implementation report

Implemented native immutable publication/manifest, one explicit receiving M2
owner per package, exact prepared-check acceptance, and a narrow A07 native M1
profile. Publication, accepted receipt, explicit M1-owner transfer event, and
current gate readiness remain separate. Frozen B06 M1 ownership is retained and
linked to accepted M2 ownership through exact native records, not rewritten.

Work recording derives actual native councils/prepared checks and a separate
complete ledger refresh. Counts are native node replacements/declared begun
checks; no experiment or measured-cost claim is made. Unknown cost stays unknown.
No generic state producer, implicit M2 initialization, execution, automatic Issue
resolution/transfer, or approval grant was added.

RED: closed publication command returned unknown_operation (1 failed, 1.40 s).
Initial narrow GREEN: closed-payload case 1 passed, 0.12 s. Actual cached native
accounting completed, followed by native issue-free publication/assignment/
acceptance yielding accepted, gate_ready=true, no reason codes.

One pure status query initially took 20.39 s. Profiling identified 642 recursive
review_node calls and 597 reviewer_packet rebuilds in the same assessment.
Root approved a bounded per-call empty cache: the same query took 0.49 s with
identical accepted/ready output. Every public B07 call resets the cache;
historical manifests use separate caches and current issues/approval/evidence/
ledger are reassessed. No global or caller-populated ready cache exists.

Focused full B07 attempt: 5 passed / 1 failed in 228.46 s. The failure exposed
an inherited council repair blocker: shared Issue targets were automatically
traversed as current evidence after their hypothesis/review revision changed.
Root approved a bounded historical-context leaf distinction, preserving exact
Issue bodies while denying old-source promotion and inspecting embedded private
IDs/hashes. RED isolated that stale-context failure; impacted council file GREEN:
25 passed in 1.55 s. Materialized A03 foreign-target context and closed publication
guards: 2 passed in 0.49 s. The original empirical lifecycle is strengthened to
revise H1 itself while retaining the original Issue target. Its targeted assertion function passed in 101.12 s on a copied, preserved native
accounted baseline. That test actually replaces H1 while retaining the original
Issue target, checks historical context without current-source promotion,
completes native publication/receiver assignment/A05 preparation/acceptance,
rejects a wrong M1 transfer actor on a separate native branch, and reaches a
ready A07 gate only after the recorded M1 owner transfers. Original Issue/review
bytes stay unchanged and no experimental result is created.

Coverage is the union of the five earlier passing B07 cases, the closed/import
pair, and that strengthened lifecycle (eight B07 cases), plus 25 impacted council
cases. The lifecycle was invoked directly as
`test_empirical_issue_requires_exact_acceptance_then_native_owner_transfer`
with a copy of the previously native-produced cached fixture; no fixture state
or prerequisite bytes were fabricated. Root requested no duplicate full B07
restart before its final full research_graph suite. Do not interpret the union
as a final all-file pytest invocation. `git diff --check` passed.

Independent B07 review is pending at implementation commit. Root handles final actual
six-Issue acceptance/preservation and repository-wide regression. Tests use one
cached native B06 reviewed/accounted project per module; synthetic tests prove
recorded policy linkage rather than scientific truth or host authentication.

## Independent review fix: abandoned invalid council accounting

The single confirmed B07 P2 was reproduced using real registered scope revisions
and B02 councils: a wrong-author predecessor poisoned work enumeration even after
a fresh valid scope review. RED: 2 failed / 1 passed in 2.13 s, covering both
incomplete and completed abandoned setups and an active invalid setup.

Work eligibility now authenticates native council/node/session/assignment and
existing submission records before completeness or the narrow setup exclusion.
A wrong-author M1 council is excluded only when an exact native successor proves
its node was replaced and the original node is no longer current. This applies
even if its B02 phases completed. Valid completed historical councils remain
eligible; current completed invalid councils remain rejected. Excluded native
history is preserved, cannot be directly recorded as valid work, and replacement
counts are still charged. No exception blanket, history deletion, readiness grant,
or cost telemetry was introduced.

Final targeted GREEN:
`.venv/bin/python -m pytest tests/codex_native/research_graph/test_handoffs.py -k 'wrong_author_council' -q`
→ 3 passed, 8 deselected in 3.19 s. Regressions exercise native repair → current
scope ready → work enumeration → public record/refresh, unchanged historical
bytes, exact replacement count, unknown cost, direct excluded-source rejection,
and HEAD preservation. Missing object bytes and forged native preparation remain
errors even for excluded sources; active completed wrong-author record/refresh
also reject. The initial added missing-byte assertion was widened to both precise
backing-error codes because collection iteration can detect the missing object
through either reference or registered-record validation; behavior already failed
closed. `git diff --check` passed. No full B07 or broad suite was rerun, per root;
scoped independent re-review follows this fix commit.
