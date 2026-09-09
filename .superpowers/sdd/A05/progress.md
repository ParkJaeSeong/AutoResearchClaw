# SDD ledger — plan: docs/superpowers/plans/research-governance/tasks/A05.md

Scope A05 only. Base7e223d6. Existing linked worktree feature/m1-research-graph clean, baseline issue tests27passed1.78s. Task brief script is non-executable and internally invokes another non-executable script; use original focused task as brief, no plugin mutations.

| Boundary | Producer / consumer | Assessment |
|---|---|---|
| A05 self | prepare/result, tests/operations | Consistent; freeze exact public payload before implementation |
| A04→A05 | immutable registered verifications/results, private ancestor context | Reuse exact reference checks; no replacement of existing IDs |
| A05→B02/A08 | assignments and budgets | Consume existing registered inputs; do not create approvals or execute work |

Todo: [ ] focused RED [ ] implementation [ ] independent review [ ] affected regression [ ] docs/commit.

Contract decision: verification.prepare closed {verification:Verification}; verification.result closed {verification_ref:SnapshotRef,result:VerificationResult}. Dispatcher alone injects A04 private verified context for those operations. Prepare requires unique issue IDs, owner active owner-role/producer binding, rule equal to linked issue resolution condition and exact current refs. Result references immutable prepared version; no issue state/events changes. New criteria use new Verification ID. Supported/refuted require output evidence and scope; failed/inconclusive can record incomplete scope/outputs without inventing completed checks. Assignment/budget/output generation beyond consumed inputs remains outside A05.
Worker /root/rg_a05 owns code/tests/supplement; root owns acceptance/status.

RED18 failed at missing operation; initial GREEN18passed. Integration acceptance added for native issue→prepare→checking→result→independent resolution and non-success preservation, replay/stale HEAD, pure-context boundaries. Root waits for focused final before single task/integration review; broad regression reserved.

Implementation f597809. Focused26passed1.34s, worker additionally ran4affected nodes0.24s. Independent task+integration review /root/rg_a05_review reviewing package7e223d6..f597809.

Review round1: P2 empty output bytes allowed supported and downstream native resolution; reviewer reproduced through real commands, no other findings. Fix requested same worker: output refs resolve nonempty bytes for supported/refuted, preserve failed/inconclusive gaps, rejection HEAD/issue unchanged.

Task A05: complete. Fix4244336, same reviewer spec/quality PASS, no remaining findings. Root affected suite207passed4.21s. Original85/imported76 files SHA256/mtime/HEAD unchanged. Task board, focused report and next A06 links updated. Whole research plan/branch integration remains pending future tasks; preserve worktree.
